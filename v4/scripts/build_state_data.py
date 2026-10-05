"""Current-state supervision, with original CPED sentiment and explicit external-label mapping."""
import sys,json,hashlib,re,unicodedata,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT.parent;sys.path.insert(0,str(WORK/'v2'))
import pandas as pd
from social_world_zh.spec import EMOTIONS,DIALOG_ACTS,state_text

def normalize(text):return re.sub(r'\W+','',unicodedata.normalize('NFKC',text)).lower()

def main():
    out=ROOT/'data/state';out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise RuntimeError('Existing immutable dataset')
    sentiment=['negative','neutral','positive'];records={};report={'sentiment_labels':sentiment,'sources':{},'external_label_map':{'平淡語氣':'neutral','開心語調':'happy','憤怒語調':'anger','驚奇語調':'astonished','悲傷語調':'sadness','厭惡語調':'disgust'},'excluded_external_labels':['關切語調','疑問語調'],'reason':'Concern and questioning tone are not unambiguous members of CPED emotion ontology. Actual file has no fear category despite README claims.','external_split':'Normalized text group SHA256 salted v4-current-20260926; 80/10/10; conflicting duplicate labels excluded.','test_policy':'Source fixed CPED state IDs/text/fine labels unchanged. External test newly reserved; no test used for training or selection.'}
    heldout_texts=set()
    for split,rawname in [('train','train_split.csv'),('validation','valid_split.csv'),('test','test_split.csv')]:
        raw=WORK/'v2/data/raw/cped'/rawname;df=pd.read_csv(raw).fillna('');groups={f'{tv}:{did}':g.to_dict('records') for (tv,did),g in df.groupby(['TV_ID','Dialogue_ID'],sort=False)}
        source=WORK/'v3/data'/f'{split}.jsonl';result=[]
        for line in source.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row['source']!='cped_state':continue
            original=groups[row['dialogue']][int(row['id'].split(':')[-1])]
            assert row['labels']['emotion']==EMOTIONS.index(original['Emotion']) and row['labels']['dialog_act']==DIALOG_ACTS.index(original['DA'])
            row['labels']['sentiment']=sentiment.index(original['Sentiment']);result.append(row)
            if split!='train':heldout_texts.add(normalize(str(original['Utterance'])))
        records[split]=result;report['sources'][split]={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'cped_state_n':len(result)}
    path=ROOT/'data/raw/Chinese_Multi-Emotion_Dialogue_Dataset/data.csv';df=pd.read_csv(path);groups=collections.defaultdict(list);dropped=collections.Counter()
    for ix,row in df.iterrows():
        text=str(row['text']).strip();label=str(row['emotion']);norm=normalize(text)
        if label not in report['external_label_map']:dropped[label]+=1;continue
        if not norm:dropped['empty']+=1;continue
        groups[norm].append((ix,text,label))
    external={s:[] for s in records}
    for norm,group in groups.items():
        if len({r[2] for r in group})!=1:dropped['conflicting_duplicate_rows']+=len(group);continue
        if norm in heldout_texts:dropped['overlap_with_cped_heldout_utterance']+=len(group);continue
        ix,text,label=group[0];digest=hashlib.sha256(('v4-current-20260926:'+norm).encode()).hexdigest();bucket=int(digest[:8],16)%100;split='train' if bucket<80 else 'validation' if bucket<90 else 'test';emotion=report['external_label_map'][label]
        labels={'emotion':EMOTIONS.index(emotion)}
        # No derived sentiment for surprise; it may be positive or negative.
        if emotion!='astonished':labels['sentiment']=1 if emotion=='neutral' else 2 if emotion=='happy' else 0
        external[split].append({'id':'medd:'+str(ix),'source':'chinese_medd','group':digest,'text':state_text([],text),'labels':labels,'original_label':label,'sentiment_label_provenance':'project mapping of unambiguous original emotion; absent for surprise'})
        dropped['duplicate_rows']+=len(group)-1
    report['external']={'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'actual_raw_label_counts':dict(collections.Counter(df['emotion'])),'excluded':dict(dropped),'splits':{s:len(rows) for s,rows in external.items()}}
    report['files']={}
    for split in records:
        rows=records[split]+external[split];file=out/(split+'.jsonl');file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8');report['files'][split]={'n':len(rows),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'source_counts':dict(collections.Counter(r['source'] for r in rows))}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
