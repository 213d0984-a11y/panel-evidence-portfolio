"""Decode every final frame, inspect MP4 atoms and render encoded QA frames."""
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg',type=Path,required=True)
    args=parser.parse_args()
    config=json.loads((HERE/'project.json').read_text(encoding='utf-8'))
    video=ROOT/config['output'];source=ROOT/config['source']
    work=ROOT/'tmp/crowdworks-video';out=work/'encoded-frames';out.mkdir(parents=True,exist_ok=True)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(source)==config['source_sha256']
    probe=subprocess.run([str(args.ffmpeg),'-hide_banner','-i',str(video)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert 'Video: h264 (High)' in probe.stderr and 'yuv420p' in probe.stderr and '1920x1080' in probe.stderr and '25 fps' in probe.stderr
    assert 'Audio:' not in probe.stderr
    (work/'output-metadata.txt').write_text(probe.stderr,encoding='utf-8')
    decode=subprocess.run([str(args.ffmpeg),'-v','error','-i',str(video),'-map','0:v:0','-progress','pipe:1','-nostats','-f','null','-'],capture_output=True,text=True,check=True)
    assert not decode.stderr.strip(),decode.stderr
    progress=dict(line.split('=',1) for line in decode.stdout.splitlines() if '=' in line)
    duration=sum(s['duration'] for s in config['scenes'])
    expected_frames=round(duration*25)
    assert int(progress['frame'])==expected_frames and progress['progress']=='end'
    assert int(progress['out_time_us'])==round(duration*1000000),progress
    atoms=[]
    with video.open('rb') as stream:
        while stream.tell()<video.stat().st_size:
            start=stream.tell();size,kind=struct.unpack('>I4s',stream.read(8))
            if size==1:size=struct.unpack('>Q',stream.read(8))[0]
            elif size==0:size=video.stat().st_size-start
            atoms.append(kind.decode('ascii'));stream.seek(start+size)
    assert atoms.index('moov')<atoms.index('mdat')
    times=[];elapsed=0
    for scene in config['scenes']:
        times.append(elapsed+scene['duration']/2);elapsed+=scene['duration']
    phone=Image.new('RGB',(960,((len(times)+1)//2)*300),'#dce7ec');draw=ImageDraw.Draw(phone)
    for i,t in enumerate(times):
        p=out/f'{t:05.2f}.png'
        subprocess.run([str(args.ffmpeg),'-v','error','-ss',str(t),'-i',str(video),'-frames:v','1','-y',str(p)],check=True)
        image=Image.open(p);assert image.size==(1920,1080)
        image=image.resize((480,270),Image.Resampling.LANCZOS)
        x=i%2*480;y=i//2*300;phone.paste(image,(x,y+30))
        draw.text((x+10,y+4),f'{t:.2f}s / 480px display width',fill='#142f43',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19))
    phone.save(work/'phone-contact.png')
    # Boundaries before/after editorial dissolves; no seek is used for playback QA.
    boundaries=[.04,duration-.04];elapsed=0
    for scene in config['scenes'][:-1]:
        elapsed+=scene['duration'];boundaries.extend([elapsed-.04,min(duration-.04,elapsed+.28)])
    for t in sorted(set(boundaries)):
        subprocess.run([str(args.ffmpeg),'-v','error','-ss',str(t),'-i',str(video),'-frames:v','1','-y',str(out/f'boundary-{t:05.2f}.png')],check=True)
    report=dict(width=1920,height=1080,fps=25,frames=expected_frames,duration=duration,codec='H.264 High',pixel_format='yuv420p',audio_streams=0,decode_errors=[],faststart=atoms.index('moov')<atoms.index('mdat'),mp4_atoms=atoms,bytes=video.stat().st_size,sha256=digest(video),original_unchanged=digest(source)==config['source_sha256'],source_sha256=digest(source))
    (work/'output-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
