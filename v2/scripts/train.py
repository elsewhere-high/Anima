import os,sys,json,time,random,math,collections,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['TOKENIZERS_PARALLELISM']='false'
import numpy as np,torch
from sklearn.metrics import accuracy_score,f1_score
from torch.utils.data import DataLoader
from transformers import get_cosine_schedule_with_warmup
from social_world_zh.model import SocialModel,collate,load_rows
from social_world_zh.spec import HEADS

class LengthBatches:
    """Shuffle pools, bucket lengths inside each pool, shuffle batches each epoch."""
    def __init__(self,rows,batch):self.rows=rows;self.batch=batch
    def __len__(self):return math.ceil(len(self.rows)/self.batch)
    def __iter__(self):
        order=torch.randperm(len(self.rows)).tolist();batches=[]
        for start in range(0,len(order),1024):
            pool=sorted(order[start:start+1024],key=lambda i:len(self.rows[i]['tokens']))
            batches.extend(pool[i:i+self.batch] for i in range(0,len(pool),self.batch))
        random.shuffle(batches);return iter(batches)

def main():
    p=argparse.ArgumentParser();p.add_argument('--epochs',type=int,default=2);p.add_argument('--batch',type=int,default=8);p.add_argument('--resume',action='store_true');args=p.parse_args()
    seed=20260925;random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed);torch.set_num_threads(4)
    start=time.time();out=ROOT/'models/social_zh';last=out/'last';best=out/'best';out.mkdir(exist_ok=True)
    model=SocialModel(training=True,checkpoint=last if args.resume else None)
    train=load_rows('train',model.tokenizer);val=load_rows('validation',model.tokenizer)
    # Five independently shuffled exposures per synthetic phrase family, reported as
    # oversampling, never counted as additional unique training observations.
    expanded=train+[r for r in train if r['source']=='home_synthetic']*4
    counts={k:collections.Counter(r['labels'][k] for r in train if k in r['labels']) for k in HEADS}
    weights={}
    for k,labels in HEADS.items():
        v=torch.tensor([max(counts[k][i],1) for i in range(len(labels))],dtype=torch.float,device='cuda')
        w=(v.sum()/v).sqrt();weights[k]=(w/w.mean()).clamp(.3,3.)
    loader=DataLoader(expanded,batch_sampler=LengthBatches(expanded,args.batch),num_workers=0,collate_fn=lambda r:collate(r,model.tokenizer,'cuda'))
    vloader=DataLoader(val,batch_size=args.batch,shuffle=False,num_workers=0,collate_fn=lambda r:collate(r,model.tokenizer,'cuda'))
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=1.5e-4,weight_decay=.01)
    scheduler=get_cosine_schedule_with_warmup(optimizer,int(len(loader)*args.epochs*.05),len(loader)*args.epochs)
    best_score=-1;first=0;step=0
    if args.resume:
        state=torch.load(last/'training_state.pt',weights_only=False,map_location='cpu')
        optimizer.load_state_dict(state['optimizer']);scheduler.load_state_dict(state['scheduler']);first=state['epoch']+1;best_score=state['best_score'];step=state['step']
        torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state_all(state['cuda_rng']);random.setstate(state['python_rng']);np.random.set_state(state['numpy_rng'])
    config={'seed':seed,'epochs':args.epochs,'batch_size':args.batch,'max_length':256,'unique_train':len(train),'epoch_exposures':len(expanded),'steps_per_epoch':len(loader),'lora_r':8,'lora_alpha':16,'lr':1.5e-4,'precision':'BF16 backbone, FP32 LoRA and heads','trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),'total_parameters':sum(p.numel() for p in model.parameters()),'label_counts':{k:dict(v) for k,v in counts.items()},'checkpoint_selection':'validation unweighted mean macro-F1 across 8 heads','loss':'mean of class-weighted cross-entropies over active heads; labels missing per source masked','gpu':torch.cuda.get_device_name(),'torch':torch.__version__}
    (ROOT/'reports/train_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8');print('CONFIG',json.dumps(config),flush=True)
    log=open(ROOT/'reports/train_events.jsonl','a' if args.resume else 'w',encoding='utf-8')
    def event(x):x.update(elapsed_seconds=time.time()-start,step=step);log.write(json.dumps(x)+'\n');log.flush();print(json.dumps(x),flush=True)
    for epoch in range(first,args.epochs):
        model.train();running=[];t0=time.time()
        for batch,y in loader:
            optimizer.zero_grad(set_to_none=True);pred=model(**batch);losses=[]
            for k in HEADS:
                valid=y[k]!=-100
                if valid.any():losses.append(torch.nn.functional.cross_entropy(pred[k][valid],y[k][valid],weight=weights[k]))
            loss=torch.stack(losses).mean()
            if not torch.isfinite(loss):raise RuntimeError(f'Nonfinite loss at {step}')
            loss.backward();torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.);optimizer.step();scheduler.step();step+=1;running.append(loss.item())
            if step%50==0:event({'type':'train','epoch':epoch+1,'loss':float(np.mean(running[-50:])),'lr':scheduler.get_last_lr()[0],'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20})
        model.eval();ys={k:[] for k in HEADS};ps={k:[] for k in HEADS}
        with torch.inference_mode():
            for batch,y in vloader:
                pred=model(**batch)
                for k in HEADS:
                    valid=y[k]!=-100;ys[k].extend(y[k][valid].cpu().tolist());ps[k].extend(pred[k][valid].argmax(-1).cpu().tolist())
        metrics={k:{'accuracy':accuracy_score(ys[k],ps[k]),'macro_f1':f1_score(ys[k],ps[k],labels=list(range(len(HEADS[k]))),average='macro',zero_division=0),'n':len(ys[k])} for k in HEADS}
        score=float(np.mean([x['macro_f1'] for x in metrics.values()]));improved=score>best_score
        if improved:best_score=score;model.save(best);(best/'selection.json').write_text(json.dumps({'epoch':epoch+1,'score':score,'validation':metrics},indent=2))
        model.save(last)
        torch.save({'optimizer':optimizer.state_dict(),'scheduler':scheduler.state_dict(),'epoch':epoch,'best_score':best_score,'step':step,'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'python_rng':random.getstate(),'numpy_rng':np.random.get_state()},last/'training_state.pt')
        event({'type':'validation','epoch':epoch+1,'metrics':metrics,'score':score,'best':improved,'epoch_seconds':time.time()-t0})
    event({'type':'complete','best_score':best_score});log.close()
if __name__=='__main__':main()
