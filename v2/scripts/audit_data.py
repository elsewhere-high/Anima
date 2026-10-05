import json,hashlib,collections,sys
import pandas as pd
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from social_world_zh.spec import HEADS
data={s:[json.loads(x) for x in (root/'data/processed'/f'{s}.jsonl').read_text(encoding='utf-8').splitlines()] for s in ['train','validation','test']}
checks={};errors=[]
for split in ['train','valid','test']:
    frame=pd.read_csv(root/'data/raw/cped'/f'{split}_split.csv').fillna('')
    groups=list(frame.groupby(['TV_ID','Dialogue_ID'],sort=False))
    unordered=sum(not g['Utterance_ID'].str.rsplit('_',n=1).str[-1].astype(int).is_monotonic_increasing for _,g in groups)
    duplicate_ids=int(frame.duplicated(['TV_ID','Dialogue_ID','Utterance_ID']).sum())
    checks[f'cped_{split}_chronology']={'unordered_dialogues':unordered,'duplicate_utterance_ids':duplicate_ids,'unknown_speaker_rows':int((frame['Speaker']=='').sum())}
    if unordered or duplicate_ids:errors.append(f'CPED chronology or identity issue: {split}')
for a,b in [('train','validation'),('train','test'),('validation','test')]:
    overlap=set(r['text'] for r in data[a])&set(r['text'] for r in data[b]);checks[f'exact_text_overlap_{a}_{b}']=len(overlap)
    if overlap:errors.append(f'text overlap {a} {b}')
    tvs=lambda rows:set(r['tv'] for r in rows if 'tv' in r)
    overlap=tvs(data[a])&tvs(data[b]);checks[f'cped_tv_overlap_{a}_{b}']=len(overlap)
    if overlap:errors.append(f'TV overlap {a} {b}')
for split,rows in data.items():
    counts=collections.Counter(r['source'] for r in rows)
    for r in rows:
        for k,label in r['labels'].items():
            if not 0<=label<len(HEADS[k]):errors.append(f'invalid label {r["id"]}')
        if r['source']=='cped_transition' and 'next_emotion' not in r['labels']:errors.append(f'missing transition target {r["id"]}')
    checks[split]={'counts':dict(counts),'unique_texts':len(set(r['text'] for r in rows)),'han_character_fraction':sum('\u4e00'<=c<='\u9fff' for r in rows for c in r['text'])/sum(len(r['text']) for r in rows)}
checks['limitations']=['Exact-text and dialogue-source audit does not prove absence of base-model pretraining contamination.','Home policy and boundary gold labels are authored synthetic cases, not independently annotated deployment observations.','CPED TV dialogue forecasts are observational and do not identify robot-action causal effects.']
checks['errors']=errors
(root/'reports/data_audit.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=True,indent=2));assert not errors
