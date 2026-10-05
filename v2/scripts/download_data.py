import pathlib,requests,json,hashlib,concurrent.futures
ROOT=pathlib.Path(__file__).resolve().parents[1]
entries=[]
for ds,repo,rev,files in [
 ('cped','scutcyr/CPED','1e4b81c28a123f22387e06664f37e5dc9322380f',['LICENSE','README.md','data/CPED/train_split.csv','data/CPED/valid_split.csv','data/CPED/test_split.csv']),
 ('crosswoz','thu-coai/CrossWOZ','df82c9fdff91b9b130f2d6b89110d3870ba6260e',['LICENSE','README.md','data/crosswoz/train.json.zip','data/crosswoz/val.json.zip','data/crosswoz/test.json.zip'])]:
    for file in files: entries.append((ds,pathlib.Path(file).name,f'https://raw.githubusercontent.com/{repo}/{rev}/{file}',rev))
rev='ed58ac423a2f4121720918bf5301577edce4ffd3'
for split in ['train','validation','test']:
    entries.append(('massive',split+'.parquet',f'https://huggingface.co/datasets/AmazonScience/massive/resolve/{rev}/zh-CN/{split}/0000.parquet',rev))
entries += [('massive','LICENSE','https://huggingface.co/datasets/AmazonScience/massive/raw/main/LICENSE','main')]
def get(item):
    ds,name,url,rev=item; r=requests.get(url,timeout=180);r.raise_for_status()
    p=ROOT/'data/raw'/ds/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(r.content)
    return dict(dataset=ds,file=str(p.relative_to(ROOT)),url=url,revision=rev,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest())
rows=list(concurrent.futures.ThreadPoolExecutor(5).map(get,entries))
(ROOT/'data/provenance.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2),flush=True)
