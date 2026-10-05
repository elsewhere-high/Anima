"""Save primary-source evidence and exact model inventories, without running remote code."""
import concurrent.futures, hashlib, json, sys, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/upgrade_20261001/upstream';OUT.mkdir(parents=True,exist_ok=True)
URLS={
 'emotieff_readme':'https://raw.githubusercontent.com/sb-ai-lab/EmotiEffLib/main/README.md',
 'emotieff_onnx':'https://raw.githubusercontent.com/sb-ai-lab/EmotiEffLib/main/emotiefflib/facial_analysis.py',
 'emotieff_tree':'https://api.github.com/repos/sb-ai-lab/EmotiEffLib/git/trees/main?recursive=1',
 'pyfeat_card':'https://huggingface.co/py-feat/face_multitask_v2/raw/main/README.md',
 'pyfeat_api':'https://huggingface.co/api/models/py-feat/face_multitask_v2?blobs=true',
 'libreface_license':'https://raw.githubusercontent.com/ihp-lab/LibreFace/main/LICENSE.rst',
 'sensevoice_card':'https://huggingface.co/FunAudioLLM/SenseVoiceSmall/raw/main/README.md',
 'sensevoice_license':'https://huggingface.co/FunAudioLLM/SenseVoiceSmall/raw/main/LICENSE',
 'sensevoice_onnx_api':'https://huggingface.co/api/models/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17?blobs=true',
 'emotion2vec_card':'https://huggingface.co/emotion2vec/emotion2vec_plus_base/raw/main/README.md',
 'emotion2vec_api':'https://huggingface.co/api/models/emotion2vec/emotion2vec_plus_base?blobs=true',
 'emotion2vec_license':'https://huggingface.co/emotion2vec/emotion2vec_plus_base/raw/main/LICENSE',
 'mertools':'https://raw.githubusercontent.com/zeroQiaoba/MERTools/master/README.md',
 'mmpose':'https://raw.githubusercontent.com/open-mmlab/mmpose/main/projects/rtmpose/README.md',
 'sherpa_example':'https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/master/python-api-examples/offline-sense-voice.py',
 'funasr_model_license':'https://raw.githubusercontent.com/modelscope/FunASR/main/MODEL_LICENSE',
 'sensevoice_code_license':'https://raw.githubusercontent.com/QwenAudio/SenseVoice/main/LICENSE',
 'affectgpt':'https://raw.githubusercontent.com/zeroQiaoba/AffectGPT/master/README.md',
 'emotion_llama':'https://raw.githubusercontent.com/ZebangCheng/Emotion-LLaMA/main/README.md',
 'mediapipe_license':'https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE',
}
def fetch(item):
 name,url=item
 try:
  data=urllib.request.urlopen(url,timeout=45).read();(OUT/(name+'.txt')).write_bytes(data)
  return {'name':name,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 except Exception as e:
  saved=OUT/(name+'.txt')
  return {'name':name,'url':url,'error':str(e),**({'cached_bytes':saved.stat().st_size,'cached_sha256':hashlib.sha256(saved.read_bytes()).hexdigest()} if saved.exists() else {})}
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: rows=list(pool.map(fetch,URLS.items()))
 (OUT/'sources.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
 print(json.dumps(rows,indent=2))
