"""Pinned public text corpora; no audio, accounts, or remote code."""
from pathlib import Path
import json,urllib.request,hashlib,time
ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
 ('CASIA-LM/OpenS2S_Datasets','31ac20ccf035cb76ffb7984801180be729cfbdc1','apache-2.0',['README.md','manifest_zh.jsonl']),
 ('Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset','f3854f9489071a4dc0bb69f2366d95095837ce68','mit',['README.md','data.csv']),
 ('OpenAssistant/oasst2','179dd21fc55192153d94adb0e0ce8f69e222bf75','apache-2.0',['README.md','data/train-00000-of-00001-88ba0162028a73fc.parquet','data/validation-00000-of-00001-1deeef95c3248fe0.parquet']),
 ('shibing624/sharegpt_gpt4','3fb53354e02a931777556fb1da37e931d73af48a','cc-by-4.0',['README.md','sharegpt_zh_38K_format.jsonl'])]

def main():
    root=ROOT/'data/raw';root.mkdir(parents=True,exist_ok=True);records=[]
    for repo,rev,license,files in SOURCES:
        info=json.load(urllib.request.urlopen('https://huggingface.co/api/datasets/'+repo+'/revision/'+rev+'?blobs=true',timeout=30));assert info['sha']==rev
        metadata={r['rfilename']:r for r in info['siblings']};folder=root/repo.split('/')[-1];folder.mkdir(exist_ok=True)
        for filename in files:
            url='https://huggingface.co/datasets/'+repo+'/resolve/'+rev+'/'+filename;target=folder/Path(filename).name;expected=metadata[filename]
            if not target.exists():
                partial=target.with_suffix(target.suffix+'.part')
                with urllib.request.urlopen(url,timeout=60) as response,partial.open('wb') as out:
                    while block:=response.read(2**20):out.write(block)
                assert partial.stat().st_size==expected['size'];partial.replace(target)
            with target.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
            if expected.get('lfs'):assert sha==expected['lfs']['sha256']
            record={'repo':repo,'revision':rev,'declared_license':license,'url':url,'file':str(target.relative_to(ROOT)),'bytes':target.stat().st_size,'sha256':sha,'upstream_lfs_verified':bool(expected.get('lfs'))};records.append(record);print(json.dumps(record),flush=True)
    (ROOT/'data/source_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
