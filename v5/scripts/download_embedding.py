import hashlib,json
from pathlib import Path
from huggingface_hub import HfApi,snapshot_download
ROOT=Path(__file__).resolve().parents[1]
repo='BAAI/bge-small-zh-v1.5'
revision='7999e1d3359715c523056ef9478215996d62a620'
folder=ROOT/'models/bge-small-zh-v1.5'
snapshot_download(repo,revision=revision,local_dir=folder,allow_patterns=['config.json','model.safetensors','tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.txt','README.md'])
rows=[{'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in folder.iterdir() if p.is_file() and p.name!='manifest.json']
(folder/'manifest.json').write_text(json.dumps({'repository':repo,'revision':revision,'license':'MIT','files':rows},indent=2),encoding='utf-8')
print(json.dumps({'repository':repo,'revision':revision,'bytes':sum(r['bytes'] for r in rows)}))
