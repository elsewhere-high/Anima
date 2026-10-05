"""Download fixed candidate artifacts; never load both ASR backends in production."""
import concurrent.futures, hashlib, json, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
UP=ROOT/'reports/upgrade_20261001/upstream'
def artifacts():
 e=json.loads((UP/'emotieff_tree.txt').read_text())['sha']
 s=json.loads((UP/'sensevoice_onnx_api.txt').read_text())['sha']
 for f in ['model.int8.onnx','tokens.txt','LICENSE','test_wavs/zh.wav','test_wavs/en.wav']:
  yield 'sensevoice/'+f,f'https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/{s}/{f}'
 yield 'social/emotieff_va.onnx',f'https://raw.githubusercontent.com/sb-ai-lab/EmotiEffLib/{e}/models/affectnet_emotions/onnx/enet_b0_8_va_mtl.onnx'
 yield 'social/pose_landmarker_lite.task','https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task'
 yield 'social/face_landmarker.task','https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
def download(item):
 name,url=item;path=ROOT/'models'/name;path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists():
  temp=path.with_suffix(path.suffix+'.partial')
  with urllib.request.urlopen(url,timeout=120) as source,temp.open('wb') as out:
   while chunk:=source.read(1024*1024):out.write(chunk)
  temp.replace(path)
 row=dict(file=name,url=url,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 print(name,row['bytes'],flush=True);return row
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(download,artifacts()))
 dest=ROOT/'models/social/manifest.json'
 old=json.loads(dest.read_text()) if dest.exists() else []
 rows.extend(r for r in old if r['file'] not in {x['file'] for x in rows})
 dest.write_text(json.dumps(rows,indent=2),encoding='utf-8')
