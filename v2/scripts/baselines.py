import os,sys,json,time
os.environ['OMP_NUM_THREADS']='2';os.environ['MKL_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.metrics import accuracy_score,f1_score
from social_world_zh.spec import HEADS
started=time.time()
data={s:[json.loads(x) for x in (ROOT/'data/processed'/f'{s}.jsonl').read_text(encoding='utf-8').splitlines()] for s in ['train','test']}
vector=TfidfVectorizer(analyzer='char',ngram_range=(2,4),min_df=3,max_features=60000,sublinear_tf=True,dtype=np.float32)
x=vector.fit_transform([r['text'] for r in data['train']]);xt=vector.transform([r['text'] for r in data['test']]);report={}
for k in HEADS:
    it=[i for i,r in enumerate(data['train']) if k in r['labels']];ie=[i for i,r in enumerate(data['test']) if k in r['labels']]
    y=[data['train'][i]['labels'][k] for i in it];ye=[data['test'][i]['labels'][k] for i in ie]
    clf=LinearSVC(C=.5,class_weight='balanced',random_state=20260925,max_iter=3000).fit(x[it],y);p=clf.predict(xt[ie])
    report[k]={'accuracy':float(accuracy_score(ye,p)),'macro_f1':float(f1_score(ye,p,labels=list(range(len(HEADS[k]))),average='macro',zero_division=0)),'n':len(ye)};print(k,report[k],flush=True)
(ROOT/'reports/tfidf_baselines.json').write_text(json.dumps({'method':'char TF-IDF 2-4 gram 60000 features + balanced LinearSVC C=0.5, training partition only','heads':report,'elapsed_seconds':time.time()-started},indent=2))
