"""Full current-state LoRA training; no future loss and no TEST loading."""
import sys,json,time,math,hashlib,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent/'v3/scripts')]
import numpy as np,torch
from social_v4.state_model import StateModel,V2
from evaluate import metrics

def main():
    started=time.time();seed=20260926;torch.manual_seed(seed);torch.set_num_threads(4);folder=ROOT/'runs/current_state_lora';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'protocol.json').exists():raise RuntimeError('Run already exists')
    cfg={'seed':seed,'epochs':2,'batch':16,'max_length':256,'adapter_lr':1e-5,'head_lr':5e-5,'weight_decay':.03,'warmup_fraction':.03,'class_weight_exponent':{'emotion':.25,'dialog_act':.10,'sentiment':.15},'loss_weight':{'emotion':1.,'dialog_act':.5,'sentiment':.25},'external_train_repeats':4,'validation_interval':1000,'min_complete_epochs_before_early_stop':1,'patience_validation_checks':3,
        'selection':'CPED emotion accuracy>=max(initial,archive)-.005 and macro F1>=max(...)+.01; dialogue-act accuracy/macro F1 >= max(initial,archive)-.005; external emotion accuracy>=initial-.01. Max weighted CPED emotion accuracy .3/F1 .5, act accuracy/F1 .1 each. Sentiment separately reported, not substituted for 13-class accuracy.',
        'architecture':'One 2B base. This adapter handles emotion/act/sentiment; original adapter retained separately for intent/policy on the same physical backbone. Dialogue SFT adapter is a separate task route, not an extra base model.',
        'future_prediction_trained':False,'test_used':False,'deployment_changed':False}
    (folder/'protocol.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    manifest=json.loads((ROOT/'data/state/manifest.json').read_text(encoding='utf-8'));data={}
    for split in ['train','validation']:
        path=ROOT/'data/state'/f'{split}.jsonl';assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['files'][split]['sha256'];data[split]=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
    model=StateModel(training=True);params=[p for p in model.parameters() if p.requires_grad];backbone_params=[p for p in model.backbone.parameters() if p.requires_grad];head_params=[p for p in model.heads.parameters() if p.requires_grad]
    for rows in data.values():
        tokens=model.tokenizer([r['text'] for r in rows],truncation=True,max_length=256)['input_ids']
        for r,t in zip(rows,tokens):r['tokens']=t
    tasks={'emotion':13,'dialog_act':19,'sentiment':3};counts={k:collections.Counter(r['labels'][k] for r in data['train'] if k in r['labels']) for k in tasks};weights={}
    for k,n in tasks.items():
        count=torch.tensor([counts[k][i] for i in range(n)],device='cuda',dtype=torch.float32);w=(count.sum()/count.clamp_min(1)).pow(cfg['class_weight_exponent'][k]);weights[k]=w/((w*count).sum()/count.sum())
    indices=list(range(len(data['train'])))+[i for i,r in enumerate(data['train']) if r['source']=='chinese_medd']*(cfg['external_train_repeats']-1)
    steps_epoch=math.ceil(len(indices)/cfg['batch']);total=steps_epoch*cfg['epochs'];warmup=max(1,int(total*cfg['warmup_fraction']))
    optimizer=torch.optim.AdamW([{'params':backbone_params,'lr':cfg['adapter_lr']},{'params':head_params,'lr':cfg['head_lr']}],weight_decay=.03)
    scheduler=torch.optim.lr_scheduler.LambdaLR(optimizer,lambda step:min((step+1)/warmup,max(0.,(total-step)/max(1,total-warmup))))
    stream=(folder/'events.jsonl').open('w',encoding='utf-8');step=0;best=None;bad=0
    def log(r):r.update(step=step,seconds=time.time()-started);stream.write(json.dumps(r)+'\n');stream.flush();print(json.dumps(r),flush=True)
    def batch(rows):
        inp=model.tokenizer.pad({'input_ids':[r['tokens'] for r in rows]},padding=True,pad_to_multiple_of=8,return_tensors='pt').to('cuda');y={k:torch.tensor([r['labels'].get(k,-100) for r in rows],device='cuda') for k in tasks};return inp,y
    def evaluate():
        model.eval();rows=data['validation'];arrays={k:np.zeros((len(rows),n),np.float32) for k,n in tasks.items()};order=sorted(range(len(rows)),key=lambda i:len(rows[i]['tokens']))
        with torch.inference_mode():
            for start in range(0,len(order),16):
                ix=order[start:start+16];x,_=batch([rows[i] for i in ix]);out=model(**x)
                for k in tasks:arrays[k][ix]=out[k].cpu().numpy()
        result={}
        for source in ['cped_state','chinese_medd']:
            result[source]={}
            for k in tasks:
                ix=[i for i,r in enumerate(rows) if r['source']==source and k in r['labels']]
                if ix:result[source][k]=metrics(np.array([rows[i]['labels'][k] for i in ix]),arrays[k][ix])
        return result
    baseline=evaluate();archive=json.loads((V2/'reports/calibration.json').read_text(encoding='utf-8'))['metrics']
    log({'type':'initial_validation','metrics':baseline,'train_unique_n':len(data['train']),'train_exposures_per_epoch':len(indices),'planned_steps':total,'trainable_parameters':sum(p.numel() for p in params),'manifest':manifest['files']})
    stop=False;losses=[]
    for epoch in range(1,cfg['epochs']+1):
        generator=torch.Generator().manual_seed(seed+epoch);permutation=torch.randperm(len(indices),generator=generator).tolist()
        # Shuffle length-bucketed pools, not globally sorted class/source blocks.
        ordered=[]
        for pos in range(0,len(permutation),512):ordered.extend(sorted([indices[j] for j in permutation[pos:pos+512]],key=lambda i:len(data['train'][i]['tokens'])))
        for pos in range(0,len(ordered),16):
            model.train();rows=[data['train'][i] for i in ordered[pos:pos+16]];x,y=batch(rows);out=model(**x);parts=[];denom=0.
            for k in tasks:
                mask=y[k]!=-100
                if mask.any():parts.append(cfg['loss_weight'][k]*(torch.nn.functional.cross_entropy(out[k][mask],y[k][mask],reduction='none')*weights[k][y[k][mask]]).mean());denom+=cfg['loss_weight'][k]
            loss=sum(parts)/denom;assert torch.isfinite(loss);optimizer.zero_grad(set_to_none=True);loss.backward()
            if step==0:
                nonzero=sum(p.grad is not None and bool(torch.count_nonzero(p.grad)) for p in backbone_params);assert nonzero>0;log({'type':'gradient_check','nonzero_adapter_gradient_tensors':nonzero})
            torch.nn.utils.clip_grad_norm_(params,1.);optimizer.step();scheduler.step();step+=1;losses.append(float(loss))
            if step%100==0:log({'type':'train','epoch':epoch,'loss':float(np.mean(losses[-100:])),'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20})
            end_epoch=pos+16>=len(ordered)
            if step%1000==0 or end_epoch:
                m=evaluate();c=m['cped_state'];b=baseline['cped_state'];eligible=c['emotion']['accuracy']>=max(b['emotion']['accuracy'],archive['emotion']['before']['accuracy'])-.005 and c['emotion']['macro_f1']>=max(b['emotion']['macro_f1'],archive['emotion']['before']['macro_f1'])+.01
                eligible=eligible and all(c['dialog_act'][metric]>=max(b['dialog_act'][metric],archive['dialog_act']['before'][metric])-.005 for metric in ['accuracy','macro_f1']) and m['chinese_medd']['emotion']['accuracy']>=baseline['chinese_medd']['emotion']['accuracy']-.01
                score=.3*c['emotion']['accuracy']+.5*c['emotion']['macro_f1']+.1*c['dialog_act']['accuracy']+.1*c['dialog_act']['macro_f1']
                chosen=bool(eligible and (best is None or score>best['score']))
                if chosen:best={'epoch':epoch,'step':step,'score':score,'metrics':m};model.save(folder/'best');bad=0
                else:bad+=1
                log({'type':'validation','epoch':epoch,'metrics':m,'eligible':bool(eligible),'selected':chosen,'score':score})
                if (epoch>1 or end_epoch) and bad>=3:stop=True;break
        if stop:break
    selection={'checkpoint':str(folder/'best') if best else None,'selected':best,'actual_steps':step,'epochs_completed':epoch if end_epoch else epoch-1,'early_stopped':step<total,'seconds':time.time()-started,'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20,'test_used':False,'deployment_changed':False}
    (folder/'selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8');log({'type':'complete',**selection});stream.close()

if __name__=='__main__':main()
