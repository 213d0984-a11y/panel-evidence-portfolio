// Continuous browser playback of a local source or final file. No app processes.
const {chromium}=require('playwright');
const fs=require('fs');const path=require('path');const http=require('http');
const file=path.resolve(process.argv[2]);const output=path.resolve(process.argv[3]);
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const server=http.createServer((req,res)=>{
  if(req.url==='/'){res.setHeader('Content-Type','text/html');return res.end('<body style="margin:0;background:#101820"><video muted controls style="width:100vw;height:100vh;object-fit:contain" src="/video"></video></body>');}
  if(req.url!=='/video'){res.writeHead(404);return res.end();}
  const size=fs.statSync(file).size;const range=/bytes=(\d+)-(\d*)/.exec(req.headers.range||'');
  const type=file.endsWith('.mp4')?'video/mp4':'video/webm';
  if(range){const start=Number(range[1]);const end=range[2]?Number(range[2]):size-1;res.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${size}`,'Accept-Ranges':'bytes','Content-Length':end-start+1,'Content-Type':type});fs.createReadStream(file,{start,end}).pipe(res);}
  else{res.writeHead(200,{'Content-Type':type,'Content-Length':size,'Accept-Ranges':'bytes'});fs.createReadStream(file).pipe(res);}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 let sample;
 try {
  const page=await browser.newPage({viewport:{width:1920,height:1080}});
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const started=Date.now();
  await page.evaluate(async()=>{
   const v=document.querySelector('video');window.audit={seeks:0,errors:[],progress:[],waiting:0};
   v.addEventListener('seeking',()=>audit.seeks++);v.addEventListener('error',()=>audit.errors.push(v.error?.message));v.addEventListener('waiting',()=>audit.waiting++);
   v.addEventListener('timeupdate',()=>{if(!audit.progress.length||v.currentTime-audit.progress.at(-1)>2)audit.progress.push(v.currentTime)});
   window.ended=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Playback timeout')),160000);v.addEventListener('ended',()=>{clearTimeout(timer);resolve({...audit,duration:v.duration,currentTime:v.currentTime,ended:v.ended,playbackRate:v.playbackRate,videoWidth:v.videoWidth,videoHeight:v.videoHeight})},{once:true});});
   v.playbackRate=1;await v.play();
  });
  let last=-1;
  sample=setInterval(async()=>{try{const t=await page.locator('video').evaluate(v=>v.currentTime);const bucket=Math.floor(t/5);if(bucket!==last){last=bucket;await page.screenshot({path:path.join(output,`play-${String(bucket).padStart(2,'0')}.png`)});}}catch{}},750);
  const ended=await page.evaluate(()=>window.ended);
  clearInterval(sample);ended.wall_seconds=(Date.now()-started)/1000;
  if(!ended.ended||ended.seeks||ended.errors.length)throw Error(JSON.stringify(ended));
  fs.writeFileSync(path.join(output,'playback.json'),JSON.stringify(ended,null,2));
  console.log(JSON.stringify(ended));
 } finally {clearInterval(sample);await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exit(1)});
