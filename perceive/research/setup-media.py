"""Recreate public research media, not private recordings or reference labels."""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path
import imageio_ffmpeg

root = Path(__file__).resolve().parents[1]
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
selection = json.loads((root / 'research/cremad/neutral-selection.json').read_text())
folder = root / 'public/research-assets/cremad'
folder.mkdir(parents=True, exist_ok=True)
for row in selection['rows']:
    source = folder / (row['FileName'] + '.flv')
    if not source.exists():
        urllib.request.urlretrieve(row['sourceUrl'], source)
    with source.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sourceSha256']:
            raise RuntimeError(f'Source hash mismatch: {source.name}')
    output = folder / (row['FileName'] + '.mp4')
    if not output.exists():
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(source), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(output)], check=True)
    print(f'{output.name}: ready')
source = root / 'public/assets/yann-lecun-wef.mp4'
if not source.exists():
    raise RuntimeError('Run npm run setup first to prepare the five reference clips.')
output = root / 'public/research-assets/yann-continuous.mp4'
if not output.exists():
    subprocess.run([ffmpeg, '-v', 'error', '-stream_loop', '-1', '-i', str(source), '-t', '602', '-c', 'copy', '-movflags', '+faststart', str(output)], check=True)
print('Long repeated public clip: ready; not an accuracy dataset.')
