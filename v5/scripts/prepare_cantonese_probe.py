"""CC0 Cantonese external probe. One storyteller: never claim population coverage."""
import hashlib,io,json,random
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
from scipy.signal import resample_poly
from prepare_speech_training import get,ROOT,REPORT

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--training',action='store_true');args=parser.parse_args()
    folder=ROOT/'data/cantonese_probe';repo='CanCLID/zoengjyutgaai'
    revision='829b30725811cabe9b8e2fd0513966470b304f12'
    meta=json.loads(get('https://huggingface.co/api/datasets/'+repo+'/revision/'+revision,folder/'repository.json'))
    assert meta['sha']==revision, 'Unexpected cached Cantonese revision'
    source='data/mouzaakdung-00000-of-00001.parquet'
    path=folder/'source.parquet';get(f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{source}',path)
    data=pq.read_table(path).to_pylist();random.Random(20261005).shuffle(data);result=[]
    if args.training:
        episodes=sorted({r['episode_id'] for r in data});random.Random(20261005).shuffle(episodes)
        mapping={e:('validation' if i<max(1,len(episodes)//10) else 'test' if i<max(2,len(episodes)//5) else 'train') for i,e in enumerate(episodes)}
        counts={'train':0,'validation':0,'test':0};limits={'train':640,'validation':48,'test':48}
    for row in data:
        if not 1<=row['audio_duration']<=12:continue
        if args.training:
            split=mapping[row['episode_id']]
            if counts[split]>=limits[split]:continue
        audio,sr=sf.read(io.BytesIO(row['audio']['bytes']),dtype='float32')
        if audio.ndim>1:audio=audio.mean(1)
        from math import gcd
        g=gcd(sr,16000);audio=resample_poly(audio,16000//g,sr//g) if sr!=16000 else audio
        name=row['id'];dest=folder/'audio'/f'{name}.wav';dest.parent.mkdir(parents=True,exist_ok=True);sf.write(dest,audio,16000)
        result.append({'id':name,'path':str(dest.resolve()),'text':row['transcription'],'episode':row['episode_id'],'speaker':'zoeng_jyut_gaai','language':'yue','accent':'cantonese_single_narrator','license':'CC0-1.0','dataset':repo,'revision':revision,'duration':len(audio)/16000,**({'split':split} if args.training else {})})
        if args.training:
            counts[split]+=1
            if counts==limits:break
        elif len(result)>=48:break
    if args.training:
        for split in counts:(folder/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in result if r['split']==split),encoding='utf-8')
        (REPORT/'cantonese_training_data.json').write_text(json.dumps({'counts':counts,'episode_split':mapping,'scope':'single speaker with disjoint episodes; no claim of speaker-generalization; overlaps prior diagnostic probe possible; not a blind population evaluation'},indent=2),encoding='utf-8');print('Cantonese training ready',counts,flush=True);return
    (folder/'probe.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in result),encoding='utf-8')
    (REPORT/'cantonese_data.json').write_text(json.dumps({'n':len(result),'hours':sum(r['duration'] for r in result)/3600,'license':'CC0-1.0','source':f'https://huggingface.co/datasets/{repo}','revision':revision,'archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scope':'single professional storyteller, external evaluation only; not broad household dialect acceptance'},indent=2),encoding='utf-8');print('Cantonese probe ready:',len(result),flush=True)

if __name__=='__main__':main()
