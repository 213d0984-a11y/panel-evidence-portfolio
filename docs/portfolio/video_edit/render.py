"""Rebuild the 60-second portfolio cut from real footage and editorial captions.

Requires Python + Pillow and an FFmpeg build with libx264. No app imports.
Run: python render.py --ffmpeg <ffmpeg executable>
The original hash is mandatory. Output is separate; --force replaces edits only.
"""
import argparse
import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
NAVY='#142f43';TEAL='#147b83';MUTED='#567084';BG='#f0f5f8';BORDER='#d7e4eb'
W,H=1920,1080


@lru_cache(maxsize=64)
def font(path,size):return ImageFont.truetype(path,size)


def text(im,xy,value,size=42,color=NAVY,bold=False,max_width=None):
    draw=ImageDraw.Draw(im)
    f=font(FONTS['bold' if bold else 'regular'],size)
    bounds=draw.textbbox((0,0),value,font=f,anchor='lt')
    if max_width is not None:
        assert bounds[2]<=max_width,(value,bounds,max_width)
    assert xy[0]+bounds[2]<W-28 and xy[1]+bounds[3]<H-18,(xy,value,bounds)
    draw.text(xy,value,font=f,fill=color,anchor='lt')


def lines(im,xy,values,size=42,color=NAVY,bold=False,gap=20,max_width=None):
    for i,value in enumerate(values):text(im,(xy[0],xy[1]+i*(size+gap)),value,size,color,bold,max_width)


def roundbox(im,box,fill='white',outline=BORDER,width=2,radius=22):
    ImageDraw.Draw(im).rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=width)


def base(title,number,footer,disclaimer='実画面・自作デモ資料 / 標準抜粋モード・API不要'):
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    text(im,(64,36),'PANEL EVIDENCE',28,TEAL,True)
    text(im,(1510,40),'PORTFOLIO  /  v0.5.2',25,MUTED)
    text(im,(64,94),title,56,NAVY,True,max_width=1770)
    d.line((64,178,1856,178),fill=BORDER,width=2)
    text(im,(64,910),footer,38,NAVY,True,max_width=1780)
    text(im,(64,990),disclaimer,28,MUTED,max_width=1780)
    text(im,(1738,990),f'{number} / 4',28,TEAL,True)
    return im


def build(scene):
    ident=scene['id'];slot=None
    if ident in ['intro','outro']:
        im=Image.new('RGB',(W,H),NAVY);d=ImageDraw.Draw(im)
        d.rectangle((64,212,76,745),fill='#56c6c9')
        text(im,(112,75),'PANEL EVIDENCE',34,'#6ad3d5',True)
        text(im,(112,164),'電気・製造業の資料確認を支援',38,'#d3e4eb')
        if ident=='intro':
            lines(im,(112,298),['技術PDFを横断検索。','仕様を、根拠から確認。'],84,'white',True,gap=38)
            text(im,(116,630),'仕様書・取説を探し、原本を確認する作業を支援。',42,'#d3e4eb')
            labels=[('型式で検索',112),('出典を確認',667),('根拠不足は回答を控える',1222)]
            for label,x in labels:
                roundbox(im,(x,788,x+520,890),'#214356','#386374',radius=16)
                text(im,(x+32,820),label,36,'white',True,max_width=470)
            text(im,(112,978),'Python製RAGアプリ / 標準抜粋モード・API不要',30,'#d3e4eb')
        else:
            lines(im,(112,298),['技術資料の検索・根拠確認を、','もっと効率的に。'],74,'white',True,gap=34)
            text(im,(116,610),'電気・製造業向け 技術文書検索支援アプリ',44,'#d3e4eb')
            text(im,(116,714),'Python  /  RAG  /  ローカル動作  /  標準モードはAPI不要',32,'#6ad3d5')
            text(im,(116,887),'複雑な表・条件・矛盾、設計判断は技術者が原本で確認。',34,'white')
            text(im,(116,979),'Panel Evidence  v0.5.2',30,'#d3e4eb')
        return im,slot
    if ident=='documents':
        im=base('複数PDFを、ひとつの検索対象に。',1,'仕様書・取説・検査要領書を、まとめて検索対象に。',
                '登録済みの自作資料を表示 / アップロード操作の映像ではありません')
        slot=(64,210,1120,650)
        text(im,(1240,246),'登録済みの自作サンプル',40,TEAL,True,max_width=610)
        text(im,(1240,346),'3冊',112,NAVY,True)
        text(im,(1492,370),'・ 7ページ',60,NAVY,True)
        lines(im,(1240,526),['資料ごとに開かずに、','横断して根拠を探す。'],46,NAVY,True,gap=26,max_width=610)
        text(im,(1240,747),'※実メーカーPDFは映していません',29,MUTED,max_width=610)
    elif ident=='question':
        im=base('型式と、確認したい仕様を質問。',2,'自然言語で、対象の型式と知りたい項目を指定。')
        slot=(64,210,1120,650)
        text(im,(1240,252),'たとえば',40,TEAL,True)
        text(im,(1240,353),'PS-24N',84,NAVY,True)
        text(im,(1240,482),'電源電圧は？',64,NAVY,True,max_width=610)
        text(im,(1240,683),'質問文と検索結果の実画面',32,MUTED,max_width=610)
    elif ident=='value':
        im=base('仕様値を、原文から確認。',2,'値の出どころを、その場で確かめる。')
        slot=(64,320,1120,400)
        text(im,(88,242),'根拠原文の拡大',34,TEAL,True)
        text(im,(1240,260),'PS-24N  /  電源電圧',40,TEAL,True,max_width=610)
        text(im,(1240,380),'DC12～24V',72,NAVY,True,max_width=610)
        text(im,(1240,485),'±10%',92,NAVY,True)
        text(im,(1240,658),'原文に記載された仕様値',36,MUTED,max_width=610)
    elif ident=='evidence':
        im=base('資料名・ページ・原文まで確認。',2,'値だけでなく、出典との関係も見える。')
        slot=(64,300,1120,470)
        text(im,(88,230),'同じ根拠ページの拡大',34,TEAL,True)
        text(im,(1240,235),'資料名',34,TEAL,True)
        lines(im,(1240,298),['photoelectric_sensor','_manual.pdf'],48,NAVY,True,gap=12,max_width=610)
        text(im,(1240,447),'PDF物理ページ',36,TEAL,True)
        text(im,(1240,510),'1',105,NAVY,True)
        text(im,(1240,675),'該当する原文を表示',40,NAVY,True,max_width=610)
        text(im,(1240,750),'※印刷ページ番号とは別の場合あり',28,MUTED,max_width=610)
    elif ident=='refusal':
        im=base('根拠が不足するときは、無理に答えない。',3,'関連する語が見つかるだけでは、回答を許可しません。')
        slot=(64,270,1120,545)
        text(im,(1240,248),'Bluetooth通信速度は？',40,TEAL,True,max_width=610)
        roundbox(im,(1210,357,1856,621),'#fff2cf','#ebcf7a',radius=18)
        lines(im,(1240,410),['登録資料からは','確認できない'],54,NAVY,True,gap=26,max_width=590)
        lines(im,(1240,700),['資料にないと断定せず、','原本確認を支援します。'],35,MUTED,gap=20,max_width=610)
    elif ident=='validation':
        im=base('実資料で、検索と回答抑制を検証。',4,'実メーカー資料を使い、検索・根拠取得・回答抑制を評価・改善。',
                '開発時の検証記録 / 実メーカーPDF12冊・固定28問 / v0.5.2')
        roundbox(im,(64,226,1856,846),'white',radius=26)
        text(im,(120,278),'v0.5.2  /  固定28問',42,TEAL,True)
        text(im,(120,390),'回答可否の判定',66,NAVY,True)
        text(im,(1110,340),'27 / 28',132,TEAL,True,max_width=680)
        text(im,(124,565),'回答する／控える、という判定が正解データと一致した件数。',39,MUTED,max_width=1650)
        roundbox(im,(112,661,1808,791),'#fef4dc','#ecd6a0',radius=16)
        text(im,(151,702),'回答本文の完全正答率ではありません。',54,NAVY,True,max_width=1600)
    else:raise ValueError(ident)
    if slot:
        x,y,w,h=slot;roundbox(im,(x-2,y-2,x+w+2,y+h+2),'white',BORDER,radius=16)
    return im,slot


def smooth(t):return t*t*(3-2*t)


def composite(base_im,slot,source,scene,progress):
    im=base_im.copy()
    if source is not None:
        u=smooth(min(1,max(0,progress)))
        b0=scene['crop'];b1=scene.get('crop_end',b0)
        box=tuple(round(a+(b-a)*u) for a,b in zip(b0,b1))
        clip=source.crop(box)
        x,y,w,h=slot;factor=min(w/clip.width,h/clip.height)
        tw,th=round(clip.width*factor),round(clip.height*factor)
        clip=clip.resize((tw,th),Image.Resampling.LANCZOS)
        px,py=x+(w-tw)//2,y+(h-th)//2;im.paste(clip,(px,py))
        d=ImageDraw.Draw(im)
        # Outlines only: no masking or replacement of the recorded UI text.
        ident=scene['id']
        if ident=='question':rect=(380,225,1360,292)
        elif ident=='value':rect=(407,614,1045,647)
        elif ident=='evidence':rect=(393,399,1085,471) if progress<.5 else (405,614,1050,647)
        elif ident=='refusal':rect=(380,646,1350,707)
        else:rect=None
        if rect:
            rx0,ry0,rx1,ry1=rect
            # Draw a highlight only if its complete source rectangle is visible.
            if box[0]<=rx0<rx1<=box[2] and box[1]<=ry0<ry1<=box[3]:
                r=(px+(rx0-box[0])*factor,py+(ry0-box[1])*factor,
                   px+(rx1-box[0])*factor,py+(ry1-box[1])*factor)
                d.rounded_rectangle(r,radius=7,outline=TEAL,width=4)
    return im


def read_frame(pipe,n):
    chunks=[];remaining=n
    while remaining:
        b=pipe.read(remaining)
        if not b:raise RuntimeError('Source decoder ended before requested clip')
        chunks.append(b);remaining-=len(b)
    return b''.join(chunks)


def srt_time(t):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg',type=Path,required=True)
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--preview-only',action='store_true')
    args=parser.parse_args()
    config=json.loads((HERE/'project.json').read_text(encoding='utf-8'))
    global FONTS;FONTS=config['fonts']
    source=ROOT/config['source'];output=ROOT/config['output']
    assert source.resolve()!=output.resolve()
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(source)==config['source_sha256'],'Original source differs: review before editing'
    assert (config['width'],config['height'],config['fps'])==(1920,1080,25)
    assert all(s['duration']>0 and s['duration']*25==round(s['duration']*25) for s in config['scenes'])
    duration=sum(s['duration'] for s in config['scenes'])
    total_frames=round(duration*25)
    work=ROOT/'tmp/crowdworks-video';work.mkdir(parents=True,exist_ok=True)
    previews=work/'previews';previews.mkdir(exist_ok=True)
    # Verify every caption fits before starting an expensive render.
    for scene in config['scenes']:
        im,slot=build(scene)
        if scene['source_start'] is not None:
            p=subprocess.run([str(args.ffmpeg),'-v','error','-ss',str(scene['source_start']+scene['duration']/2),'-i',str(source),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,stdout=subprocess.PIPE)
            image=Image.frombytes('RGB',(1440,1000),p.stdout)
            im=composite(im,slot,image,scene,.5)
        im.save(previews/f"{scene['id']}.png")
    if args.preview_only:
        print('Preview frames rendered; no video output touched');return
    if output.exists() and not args.force:raise FileExistsError('Use --force to replace the edited output only')
    temporary=work/'edited-render.mp4';log=work/'encode.log'
    cmd=[str(args.ffmpeg),'-hide_banner','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','25','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-profile:v','high','-level:v','4.0','-movflags','+faststart','-metadata','title=Panel Evidence - Technical document search','-metadata','comment=Real recorded footage; self-authored demo documents; app v0.5.2; editorial captions; no generated app operations',str(temporary)]
    count=0;previous=None
    with log.open('wb') as logging:
        encoder=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=logging)
        try:
            for scene in config['scenes']:
                print('Render',scene['id'],flush=True)
                base_im,slot=build(scene);total=round(scene['duration']*25);decoder=None
                if scene['source_start'] is not None:
                    decoder=subprocess.Popen([str(args.ffmpeg),'-v','error','-ss',str(scene['source_start']),'-i',str(source),'-t',str(scene['duration']),'-vf','fps=25','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=logging)
                last=None
                try:
                    for i in range(total):
                        frame=None if decoder is None else Image.frombytes('RGB',(1440,1000),read_frame(decoder.stdout,1440*1000*3))
                        im=composite(base_im,slot,frame,scene,i/max(1,total-1))
                        if previous is not None and i<6:im=Image.blend(previous,im,(i+1)/6)
                        # Thin editorial progress line, outside all recorded evidence.
                        ImageDraw.Draw(im).rectangle((64,1047,64+int(1792*(count+1)/total_frames),1052),fill=TEAL)
                        encoder.stdin.write(im.tobytes());last=im;count+=1
                finally:
                    if decoder:
                        decoder.stdout.close()
                        result=decoder.wait(timeout=30)
                        if result:raise RuntimeError(f'Source decode failed: {result}')
                previous=last
            encoder.stdin.close();status=encoder.wait(timeout=180)
            if status:raise RuntimeError(f'Encoder failed: {status}; see {log}')
        except BaseException:
            if encoder.poll() is None:encoder.terminate();encoder.wait(timeout=30)
            raise
    assert count==total_frames and digest(source)==config['source_sha256']
    temporary.replace(output)
    captions=[];elapsed=0
    for n,scene in enumerate(config['scenes'],1):
        captions.append(f"{n}\n{srt_time(elapsed)} --> {srt_time(elapsed+scene['duration'])}\n{scene['caption']}\n")
        elapsed+=scene['duration']
    output.with_suffix('.srt').write_text('\n'.join(captions),encoding='utf-8')
    (work/'render.json').write_text(json.dumps({'frames':count,'fps':25,'duration':duration,'width':W,'height':H,'codec':'H.264','pixel_format':'yuv420p','audio':False,'source_sha256':digest(source),'output_sha256':digest(output),'output_bytes':output.stat().st_size},indent=2),encoding='utf-8')
    print(json.dumps({'frames':count,'output':str(output),'bytes':output.stat().st_size}),flush=True)


if __name__=='__main__':main()
