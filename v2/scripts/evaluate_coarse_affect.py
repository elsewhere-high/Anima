import json,sys
from pathlib import Path
import numpy as np
from sklearn.metrics import accuracy_score,f1_score,confusion_matrix,log_loss
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from social_world_zh.spec import EMOTIONS
from social_world_zh.affect import GROUPS
data=[json.loads(x) for x in (ROOT/'data/processed/test.jsonl').read_text(encoding='utf-8').splitlines()]
ix=[i for i,r in enumerate(data) if 'emotion' in r['labels']];raw=np.load(ROOT/'reports/test_logits.npz')['emotion'][ix]
temp=json.loads((ROOT/'reports/calibration.json').read_text())['temperatures']['emotion'];x=raw.astype(float)/temp;x-=x.max(1,keepdims=True);p=np.exp(x);p/=p.sum(1,keepdims=True)
names=list(GROUPS);q=np.stack([p[:,[EMOTIONS.index(e) for e in GROUPS[k]]].sum(1) for k in names],axis=1)
mapping={EMOTIONS.index(e):i for i,k in enumerate(names) for e in GROUPS[k]};y=np.array([mapping[data[i]['labels']['emotion']] for i in ix]);pred=q.argmax(1)
report={'method':'Sum calibrated 13-emotion probabilities using the deterministic CPED Emotion-to-Sentiment mapping; no additional trained head','labels':names,'n':len(y),'accuracy':float(accuracy_score(y,pred)),'macro_f1':float(f1_score(y,pred,labels=[0,1,2],average='macro',zero_division=0)),'nll':float(log_loss(y,q,labels=[0,1,2])),'confusion_matrix':confusion_matrix(y,pred,labels=[0,1,2]).tolist(),'groups':GROUPS,'limitation':'CPED categorizes astonished as negative; this is a dataset convention, not a universal psychological definition.'}
(ROOT/'reports/coarse_affect.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=True,indent=2))
