"""Prepare only the received public clip prefix for a local-model probe."""
from pathlib import Path
import json
import subprocess
import sys
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
clip = sys.argv[1] if len(sys.argv)>1 else 'elon-musk-wef'
duration = int(sys.argv[2]) if len(sys.argv)>2 else 3
if clip not in ['yann-lecun-wef','steve-jobs-interview','elon-musk-wef','pep-guardiola-press','mark-zuckerberg-interview'] or not 1<=duration<=6:
    raise ValueError('Only bounded prefixes of the five public reference videos')
out = ROOT/'research/minicpm-probe'/clip
out.mkdir(parents=True, exist_ok=True)
ff = imageio_ffmpeg.get_ffmpeg_exe()
source = ROOT/'public/assets'/f'{clip}.mp4'
chunks = []
for i in range(duration):
    wav,jpg = out/f'{i}.wav',out/f'{i}.jpg'
    subprocess.run([ff,'-v','error','-y','-ss',str(i),'-i',str(source),'-t','1','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],check=True)
    subprocess.run([ff,'-v','error','-y','-ss',str(i+.5),'-i',str(source),'-frames:v','1','-vf','scale=640:-2',str(jpg)],check=True)
    chunks.append({'audio':str(wav),'image':str(jpg),'end':i+1})
(out/'manifest.json').write_text(json.dumps({'clip':clip,'duration':duration,'chunks':chunks},indent=2))
print(str(out/'manifest.json'))
