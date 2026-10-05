import requests,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sources={
 'qwen_current_catalog':'https://huggingface.co/api/models?author=Qwen&search=Qwen3&sort=lastModified&direction=-1&limit=100',
 'socialdial_readme':'https://raw.githubusercontent.com/zhanhl316/SocialDial/main/README.md',
 'emotiontalk_card':'https://huggingface.co/datasets/BAAI/Emotiontalk/raw/main/README.md',
 'massive_repository':'https://huggingface.co/api/datasets/AmazonScience/massive',
}
ledger=[]
for name,url in sources.items():
    r=requests.get(url,timeout=60)
    if r.ok:
        path=root/'research'/f'{name}.txt';path.write_bytes(r.content)
    ledger.append({'name':name,'url':url,'status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest() if r.ok else None})
(root/'research/additional_sources.json').write_text(json.dumps(ledger,indent=2))
print('Research metadata saved')
