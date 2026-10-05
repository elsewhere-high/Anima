"""Held-out evaluation, validation-only temperatures, and transition ablations."""
import sys,json,time,collections,argparse,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np,torch
from sklearn.metrics import accuracy_score,f1_score,log_loss,classification_report
from social_world_zh.model import SocialModel,load_rows,collate
from social_world_zh.spec import HEADS,state_text,transition_text,MAX_LENGTH
from social_world_zh.transition import fit_tables,candidate_state_text,softmax,TransitionPrior

def metrics(y,logits,temperature=1):
    p=torch.tensor(logits/temperature).softmax(-1).numpy();pred=p.argmax(-1);confidence=p.max(-1)
    ece=0.
    for bin_id in range(10):
        lo=bin_id/10;hi=(bin_id+1)/10
        m=(confidence>=lo)&((confidence<=hi) if bin_id==9 else (confidence<hi))
        if m.any():ece+=float(m.mean()*abs((pred[m]==y[m]).mean()-confidence[m].mean()))
    return {'n':len(y),'accuracy':float(accuracy_score(y,pred)),'macro_f1':float(f1_score(y,pred,labels=list(range(logits.shape[1])),average='macro',zero_division=0)),'nll':float(log_loss(y,p,labels=list(range(logits.shape[1])))),'ece_10bins':ece}

def collect(model,rows,batch=8):
    arrays={k:np.zeros((len(rows),len(labels)),dtype=np.float32) for k,labels in HEADS.items()}
    order=sorted(range(len(rows)),key=lambda i:len(rows[i]['tokens']))
    with torch.inference_mode():
        for pos in range(0,len(order),batch):
            ix=order[pos:pos+batch];encoded,_=collate([rows[i] for i in ix],model.tokenizer,'cuda');pred=model(**encoded)
            for k in HEADS:arrays[k][ix]=pred[k].float().cpu().numpy()
    return arrays

def transition_inputs(model,rows):
    texts=[state_text(r['history'],r['speech']) for r in rows]+[candidate_state_text(r['history'],r['speech'],r['candidate']) for r in rows]
    tokens=model.tokenizer(texts,truncation=True,max_length=MAX_LENGTH)['input_ids']
    extra=[{'tokens':x,'labels':{}} for x in tokens];scores=collect(model,extra)
    return {k:v[:len(rows)] for k,v in scores.items()},{k:v[len(rows):] for k,v in scores.items()}

def enhance(model,rows,logits,temps,transition):
    cur,cand=transition_inputs(model,rows);result={}
    for k,state in [('next_emotion','emotion'),('next_act','dialog_act')]:
        candidate=softmax(cand[state],temps[state])
        for i,r in enumerate(rows):
            if not r['candidate']:candidate[i]=1/len(HEADS[state])
        p=transition.combine(k,softmax(logits[k],temps[k]),softmax(cur[state],temps[state]),candidate)
        result[k]=np.log(p.clip(1e-12))*temps[k]
    return result

def main():
    torch.set_num_threads(4);torch.manual_seed(20260925);started=time.time()
    model=SocialModel(checkpoint=ROOT/'models/social_zh/best').eval()
    val=load_rows('validation',model.tokenizer);test=load_rows('test',model.tokenizer)
    val_logits=collect(model,val);print('Validation logits ready',flush=True)
    temps={};cal={}
    for k in HEADS:
        mask=np.array([k in r['labels'] for r in val]);y=np.array([r['labels'][k] for r in val if k in r['labels']]);x=val_logits[k][mask]
        grid=np.exp(np.linspace(np.log(.3),np.log(5.),80))
        losses=[torch.nn.functional.cross_entropy(torch.tensor(x/t),torch.tensor(y)).item() for t in grid]
        temps[k]=float(grid[np.argmin(losses)]);cal[k]={'before':metrics(y,x),'after':metrics(y,x,temps[k])}
    (ROOT/'reports/calibration.json').write_text(json.dumps({'method':'scalar temperature grid, validation only','checkpoint_fingerprint':model.checkpoint_fingerprint,'temperatures':temps,'metrics':cal},indent=2))
    # A validation-identified weak neural transition head is regularized by a
    # smoothed transition table learned from the official TRAIN partition only.
    # No test labels are used for counts, blend weights, or calibration.
    tables,triples=fit_tables();vix=[i for i,r in enumerate(val) if r['source']=='cped_transition'];vrows=[val[i] for i in vix]
    current,candidate=transition_inputs(model,vrows)
    fit={'checkpoint_fingerprint':model.checkpoint_fingerprint,'training_triplet_occurrences':triples,'training_source':'full official CPED train partition; same 6384 eligible transition observations as neural transition subset','smoothing':{'marginal_pseudocount':.5,'current_backoff':5,'pair_backoff':10},'selection':'validation macro-F1 blend; validation NLL temperature','heads':{}}
    for k,state in [('next_emotion','emotion'),('next_act','dialog_act')]:
        y=np.array([r['labels'][k] for r in vrows]);neural=softmax(val_logits[k][vix],temps[k])
        prior=np.einsum('ni,nj,ijk->nk',softmax(current[state],temps[state]),softmax(candidate[state],temps[state]),tables[k])
        alphas=np.linspace(0,1,21);scores=[f1_score(y,((1-a)*neural+a*prior).argmax(-1),labels=list(range(len(HEADS[k]))),average='macro',zero_division=0) for a in alphas]
        alpha=float(alphas[np.argmax(scores)]);blend=(1-alpha)*neural+alpha*prior;logblend=np.log(blend.clip(1e-12))
        grid=np.exp(np.linspace(np.log(.3),np.log(5.),80));losses=[torch.nn.functional.cross_entropy(torch.tensor(logblend/t),torch.tensor(y)).item() for t in grid];temperature=float(grid[np.argmin(losses)])
        fit['heads'][k]={'alpha':alpha,'temperature':temperature,'neural_validation':metrics(y,val_logits[k][vix],temps[k]),'blended_validation':metrics(y,logblend,temperature)}
    np.savez_compressed(ROOT/'models/social_zh/transition_prior.npz',**tables)
    (ROOT/'models/social_zh/transition_config.json').write_text(json.dumps(fit,indent=2));(ROOT/'reports/transition_fit.json').write_text(json.dumps(fit,indent=2));transition=TransitionPrior()
    print('Validation transition fit',json.dumps(fit),flush=True)
    logits=collect(model,test);print('Test logits ready',flush=True)
    result={'test_manifest_sha256':hashlib.sha256((ROOT/'data/processed/test.jsonl').read_bytes()).hexdigest(),'heads':{},'cped_home_slice':{},'forecast_baselines':{},'ablations':{}}
    np.savez_compressed(ROOT/'reports/test_logits.npz',**logits)
    tix=[i for i,r in enumerate(test) if r['source']=='cped_transition'];trows=[test[i] for i in tix]
    result['raw_neural_transition_heads']={k:metrics(np.array([r['labels'][k] for r in trows]),logits[k][tix],temps[k]) for k in ['next_emotion','next_act']}
    improved=enhance(model,trows,{k:v[tix] for k,v in logits.items()},temps,transition)
    for k,v in improved.items():logits[k][tix]=v
    train=[json.loads(x) for x in (ROOT/'data/processed/train.jsonl').read_text(encoding='utf-8').splitlines()]
    for k in HEADS:
        mask=np.array([k in r['labels'] for r in test]);y=np.array([r['labels'][k] for r in test if k in r['labels']]);x=logits[k][mask]
        result['heads'][k]=metrics(y,x,temps[k])
        result['heads'][k]['per_class']=classification_report(y,x.argmax(-1),labels=list(range(len(HEADS[k]))),target_names=HEADS[k],output_dict=True,zero_division=0)
        home=np.array([k in r['labels'] and r.get('home',False) for r in test])
        if home.any():result['cped_home_slice'][k]=metrics(np.array([r['labels'][k] for r in test if k in r['labels'] and r.get('home')]),logits[k][home],temps[k])
        if k.startswith('next_'):
            majority=collections.Counter(r['labels'][k] for r in train if k in r['labels']).most_common(1)[0][0]
            current_key='current_emotion' if k=='next_emotion' else 'current_act'
            persistent=np.array([r[current_key] for r in test if k in r['labels']]);pred=x.argmax(-1)
            def baseline(p):return {'accuracy':float(accuracy_score(y,p)),'macro_f1':float(f1_score(y,p,labels=list(range(len(HEADS[k]))),average='macro',zero_division=0))}
            result['forecast_baselines'][k]={'train_majority':baseline(np.full_like(y,majority)),'oracle_current_label_persistence':baseline(persistent)}
            rng=np.random.default_rng(20260925);delta=(pred==y).astype(float)-(persistent==y).astype(float)
            # Dialogue-level bootstrap respects correlation within public scenes.
            dialogues=np.array([r['dialogue'] for r in test if k in r['labels']]);groups=[delta[dialogues==d] for d in np.unique(dialogues)]
            boots=[]
            for _ in range(1000):boots.append(float(np.concatenate([groups[i] for i in rng.integers(0,len(groups),len(groups))]).mean()))
            result['forecast_baselines'][k]['accuracy_delta_vs_oracle_persistence_95ci']=[float(v) for v in np.percentile(boots,[2.5,97.5])]
    # Same predetermined held-out transition rows for every intervention. These
    # are input ablations, not causally identified real robot interventions.
    forecast=[r for r in test if r['source']=='cped_transition'];rng=np.random.default_rng(914);ix=rng.choice(len(forecast),min(500,len(forecast)),replace=False);subset=[forecast[i] for i in ix]
    candidates=[r['candidate'] for r in subset];shuffled=np.roll(candidates,1)
    for mode in ['full','no_history','no_candidate','shuffled_candidate']:
        rows=[]
        for i,r in enumerate(subset):
            h=[] if mode=='no_history' else r['history'];c='' if mode=='no_candidate' else shuffled[i] if mode=='shuffled_candidate' else r['candidate']
            text=transition_text(h,r['speech'],c);rows.append({**r,'history':h,'candidate':c,'text':text,'tokens':model.tokenizer(text,truncation=True,max_length=MAX_LENGTH)['input_ids']})
        x=collect(model,rows);x.update(enhance(model,rows,x,temps,transition));result['ablations'][mode]={k:metrics(np.array([r['labels'][k] for r in rows]),x[k],temps[k]) for k in ['next_emotion','next_act']}
        print('Ablation',mode,flush=True)
    result['elapsed_seconds']=time.time()-started
    (ROOT/'reports/evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    from enrich_evaluation import enrich
    enrich()
    print(json.dumps({k:{m:v for m,v in x.items() if m!='per_class'} for k,x in result['heads'].items()},indent=2),flush=True)
if __name__=='__main__':main()
