"""Proper probabilistic baseline, fitted exclusively on training label counts."""
import json,collections,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from social_world_zh.spec import HEADS
def enrich():
    path=ROOT/'reports/evaluation.json';report=json.loads(path.read_text(encoding='utf-8'))
    data={s:[json.loads(x) for x in (ROOT/'data/processed'/f'{s}.jsonl').read_text(encoding='utf-8').splitlines()] for s in ['train','test']}
    for k in ['next_emotion','next_act']:
        labels=[r['labels'][k] for r in data['train'] if k in r['labels']];counts=np.bincount(labels,minlength=len(HEADS[k]))+.5;p=counts/counts.sum()
        y=np.array([r['labels'][k] for r in data['test'] if k in r['labels']]);nll=float(-np.log(p[y]).mean())
        report['forecast_baselines'][k]['train_marginal']={'nll':nll,'dirichlet_pseudocount':.5,'distribution':{label:float(v) for label,v in zip(HEADS[k],p)},'model_nll_gain_nats':nll-report['heads'][k]['nll']}
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v['train_marginal']['model_nll_gain_nats'] for k,v in report['forecast_baselines'].items()}))
if __name__=='__main__':enrich()
