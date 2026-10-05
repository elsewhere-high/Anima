"""Download an attributed, speaker-disjoint AISHELL-3 pilot. Never use private audio."""
import concurrent.futures, hashlib, io, json, random, re, time
from pathlib import Path
import requests
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/speech_pilot'
REPORT=ROOT/'reports/speech_20261005'

def get(url, path):
    if path.exists(): return path.read_bytes()
    for attempt in range(4):
        try:
            r=requests.get(url,timeout=(20,120));r.raise_for_status()
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix(path.suffix+'.part');tmp.write_bytes(r.content);tmp.replace(path)
            return r.content
        except Exception as exc:
            if isinstance(exc,requests.HTTPError) and exc.response.status_code==404:raise
            if attempt==3: raise
            time.sleep(2**attempt)

def main():
    global OUT,REPORT
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--expanded',action='store_true');args=parser.parse_args()
    cache=OUT
    if args.expanded:
        OUT=ROOT/'data/speech_expanded';REPORT=ROOT/'reports/speech_20261005/expanded'
    OUT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    repo='AISHELL/AISHELL-3'
    revision='f20d5db4a31fe779ef07bb1af4ea92da5c786622'
    meta=json.loads(get('https://huggingface.co/api/datasets/'+repo+'/revision/'+revision,cache/'repository.json'))
    assert meta['sha']==revision, 'Unexpected cached AISHELL revision'
    base=f'https://huggingface.co/datasets/{repo}/resolve/{revision}/'
    info=get(base+'spk-info.txt',cache/'spk-info.txt').decode('utf-8')
    transcripts=get(base+'train/content.txt',cache/'content.txt').decode('utf-8')
    speakers={}
    for line in info.splitlines():
        parts=line.split()
        if len(parts)==4 and parts[0].startswith('SSB'):speakers[parts[0]]=dict(age_group=parts[1],gender=parts[2],accent=parts[3])
    groups={}
    for line in transcripts.splitlines():
        name,words=line.split('\t',1)
        text=''.join(words.split()[::2]);speaker=name[:7]
        if speaker in speakers and 4<=len(text)<=55:groups.setdefault(speaker,[]).append((name,text))
    rng=random.Random(20261005)
    dirs=json.loads(get(f'https://huggingface.co/api/datasets/{repo}/tree/{revision}/train/wav?limit=1000',cache/'speaker_directories.json'))
    published={Path(item['path']).name for item in dirs if item['type']=='directory'}
    groups={k:v for k,v in groups.items() if k in published}
    # Stratify north/south/other and age-group D where available before splitting by speaker.
    strata={}
    for speaker in sorted(groups):
        p=speakers[speaker];strata.setdefault((p['accent'],p['age_group']=='D'),[]).append(speaker)
    buckets={'train':[],'validation':[],'test':[]}
    for key,ids in sorted(strata.items()):
        rng.shuffle(ids)
        if len(ids)>=4:
            buckets['validation'].append(ids.pop());buckets['test'].append(ids.pop())
        buckets['train'].extend(ids[:8])
    jobs=[]
    for split,ids in buckets.items():
        for speaker in ids:
            listing=json.loads(get(f'https://huggingface.co/api/datasets/{repo}/tree/{revision}/train/wav/{speaker}?limit=1000',cache/'listings'/f'{speaker}.json'))
            available={Path(item['path']).name for item in listing if item['type']=='file'}
            clips=[x for x in groups[speaker] if x[0] in available];rng.shuffle(clips)
            count=(100 if split=='train' else 32) if args.expanded else (32 if split=='train' else 12)
            for name,text in clips[:count]:
                jobs.append(dict(id=name[:-4],speaker=speaker,split=split,text=text,**speakers[speaker],source=f'train/wav/{speaker}/{name}'))
    def download(row):
        raw=get(base+row['source'],cache/'source_audio'/f"{row['id']}.wav")
        audio,sr=sf.read(io.BytesIO(raw),dtype='float32');audio=audio.mean(1) if audio.ndim>1 else audio
        if sr!=16000:
            from math import gcd
            g=gcd(sr,16000);audio=resample_poly(audio,16000//g,sr//g)
        if not .4<=len(audio)/16000<=18: return None
        dest=OUT/'audio'/f"{row['id']}.wav";dest.parent.mkdir(exist_ok=True)
        sf.write(dest,audio,16000,subtype='PCM_16')
        return {**row,'path':str(dest.resolve()),'duration':len(audio)/16000,'source_sha256':hashlib.sha256(raw).hexdigest(),'dataset':repo,'revision':revision,'license':'Apache-2.0'}
    rows=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(download,row):row for row in jobs}
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            try:
                row=f.result()
                if row:rows.append(row)
            except Exception as exc:errors.append({'id':futures[f]['id'],'error':str(exc)})
            if i%50==0:print(f'downloaded {i}/{len(jobs)}, retained {len(rows)}',flush=True)
    for split in buckets:
        part=sorted((r for r in rows if r['split']==split),key=lambda r:r['id'])
        (OUT/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in part),encoding='utf-8')
    summary={'seed':20261005,'revision':revision,'source':'https://www.openslr.org/93/','license':'Apache-2.0','scope':'Pilot read Mandarin, north/south accent labels. Not a dialect/elderly/dysarthria or real far-field benchmark. D means >41, NOT elderly. Pretraining overlap unknown.', 'splits':{s:{'utterances':sum(r['split']==s for r in rows),'speakers':len({r['speaker'] for r in rows if r['split']==s}),'hours':sum(r['duration'] for r in rows if r['split']==s)/3600} for s in buckets},'errors':errors}
    (REPORT/'data.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
