"""Learned observational transition tables conditioned on both speakers' beliefs.

Tiny transition head shares the existing text encoder. Never uses gold labels at
inference. Counts are fitted on CPED's training TV shows only.
"""
import json
import numpy as np
from .spec import ROOT,EMOTIONS,DIALOG_ACTS,state_text

def candidate_state_text(history,speech,candidate):
    # Current speaker changes from A to B: preserve perspective consistently.
    swapped=[('对方' if role=='用户' else '用户',text) for role,text in history]
    return state_text((swapped+[('对方',speech)])[-4:],candidate)

def softmax(x,temperature=1.):
    x=np.asarray(x,dtype=np.float64)/temperature;x=x-x.max(axis=-1,keepdims=True);p=np.exp(x);return p/p.sum(axis=-1,keepdims=True)

class TransitionPrior:
    def __init__(self,folder=None):
        folder=folder or ROOT/'models/social_zh'
        self.tables=dict(np.load(folder/'transition_prior.npz'))
        self.config=json.loads((folder/'transition_config.json').read_text())
    def combine(self,key,neural,current,candidate,postcalibrate=True):
        prior=np.einsum('ni,nj,ijk->nk',current,candidate,self.tables[key])
        alpha=self.config['heads'][key]['alpha'];p=(1-alpha)*neural+alpha*prior
        if postcalibrate:p=softmax(np.log(p.clip(1e-12)),self.config['heads'][key]['temperature'])
        return p

def fit_tables():
    import pandas as pd
    df=pd.read_csv(ROOT/'data/raw/cped/train_split.csv').fillna('');counts={'next_emotion':np.zeros((13,13,13)),'next_act':np.zeros((19,19,19))};n=0
    for _,group in df.groupby(['TV_ID','Dialogue_ID'],sort=False):
        rows=group.to_dict('records')
        for i in range(len(rows)-2):
            a,b,c=rows[i:i+3]
            if a['Speaker']!=c['Speaker'] or a['Speaker']==b['Speaker']:continue
            if not all(x['Emotion'] in EMOTIONS and x['DA'] in DIALOG_ACTS for x in [a,b,c]):continue
            counts['next_emotion'][EMOTIONS.index(a['Emotion']),EMOTIONS.index(b['Emotion']),EMOTIONS.index(c['Emotion'])]+=1
            counts['next_act'][DIALOG_ACTS.index(a['DA']),DIALOG_ACTS.index(b['DA']),DIALOG_ACTS.index(c['DA'])]+=1;n+=1
    tables={}
    for k,c in counts.items():
        marginal=(c.sum((0,1))+.5);marginal/=marginal.sum()
        # Hierarchical Dirichlet smoothing backs sparse candidate pairs off to
        # current-speaker transitions, then the training marginal.
        current=(c.sum(1)+5*marginal);current/=current.sum(-1,keepdims=True)
        table=c+10*current[:,None,:];table/=table.sum(-1,keepdims=True);tables[k]=table
    return tables,n
