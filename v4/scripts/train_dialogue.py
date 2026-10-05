"""Actually train the Chinese response adapter; final assistant targets only."""
import sys,json,time,math,hashlib,collections,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch,numpy as np
from social_v4.chat_model import DialogueModel,collate_chat
from snapshot_code import snapshot

def main():
    started=time.time();seed=20260927;torch.manual_seed(seed);torch.set_num_threads(4);folder=ROOT/'runs/dialogue_sft';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'protocol.json').exists():raise RuntimeError('Do not overwrite an existing run')
    snapshot(folder,['scripts/train_dialogue.py','social_v4/chat_model.py','social_v4/dialogue.py','scripts/build_dialogue_data.py','scripts/curate_dialogue_train.py'])
    protocol={'seed':seed,'epochs':4,'min_epochs':2,'patience_epochs':2,'micro_batch':2,'gradient_accumulation':8,'learning_rate':3e-5,'weight_decay':.01,'warmup_fraction':.05,'max_length':512,'source_repeat':{'opens2s_zh':1,'oasst2_zh':3,'home_authored':8},'loss':'Only final assistant answer and end token, no user/history/padding or reasoning_content','base':'Pinned Qwen3.5-2B; fresh r8 LoRA, same runtime physical base as current-state model','selection':'Every epoch: mean per-source validation token NLL lower than base by .03, no source worse than base by .10. Select lowest mean; early stop after two non-improving epochs, at least two complete epochs. Separate fixed held-out generation/likelihood and home conversation probes before release.','test_used':False,'deployment_changed':False}
    (folder/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8');manifest=json.loads((ROOT/'data/dialogue/manifest.json').read_text(encoding='utf-8'));rows={}
    for split in ['train','validation']:
        path=ROOT/'data/dialogue'/f'{split}.jsonl';assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['files'][split]['sha256'];rows[split]=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
        for r in rows[split]:
            p=r['prompt_length'];assert r['labels'][:p]==[-100]*p and r['labels'][p:]==r['input_ids'][p:] and len(r['input_ids'])<=512
    model=DialogueModel(training=True);parameters=[p for p in model.parameters() if p.requires_grad]
    exposures=[i for i,r in enumerate(rows['train']) for _ in range(protocol['source_repeat'][r['source']])];micro_steps=math.ceil(len(exposures)/2);updates_epoch=math.ceil(micro_steps/8);total=updates_epoch*protocol['epochs'];warmup=max(1,round(total*.05))
    optimizer=torch.optim.AdamW(parameters,lr=3e-5,weight_decay=.01);scheduler=torch.optim.lr_scheduler.LambdaLR(optimizer,lambda s:min((s+1)/warmup,max(0.,(total-s)/max(1,total-warmup))))
    stream=(folder/'events.jsonl').open('w',encoding='utf-8');step=0;micro=0
    def log(r):r.update(step=step,micro_step=micro,seconds=time.time()-started);stream.write(json.dumps(r)+'\n');stream.flush();print(json.dumps(r),flush=True)
    def validate():
        model.eval();totals=collections.defaultdict(lambda:[0.,0,0]);ordered=sorted(rows['validation'],key=lambda r:(r['source'],len(r['input_ids'])))
        with torch.inference_mode():
            for source in sorted({r['source'] for r in ordered}):
                subset=[r for r in ordered if r['source']==source]
                for i in range(0,len(subset),2):
                    chunk=subset[i:i+2];loss,n=model.loss(**collate_chat(chunk,model.tokenizer));totals[source][0]+=float(loss)*n;totals[source][1]+=n;totals[source][2]+=len(chunk)
        return {s:{'token_nll':v[0]/v[1],'tokens':v[1],'examples':v[2]} for s,v in totals.items()}
    baseline=validate();log({'type':'initial_validation','metrics':baseline,'train_unique_n':len(rows['train']),'train_exposures_per_epoch':len(exposures),'sources':manifest['files']['train']['sources'],'planned_optimizer_steps':total,'trainable_parameters':sum(p.numel() for p in parameters)});best=None;losses=[]
    bad_epochs=0
    for epoch in range(1,protocol['epochs']+1):
        perm=torch.randperm(len(exposures),generator=torch.Generator().manual_seed(seed+epoch)).tolist();ordered=[]
        for pos in range(0,len(perm),128):ordered.extend(sorted([exposures[j] for j in perm[pos:pos+128]],key=lambda i:len(rows['train'][i]['input_ids'])))
        batches=[ordered[i:i+2] for i in range(0,len(ordered),2)]
        for start in range(0,len(batches),8):
            model.train();optimizer.zero_grad(set_to_none=True);group=batches[start:start+8]
            for indices in group:
                chunk=[rows['train'][i] for i in indices];loss,n=model.loss(**collate_chat(chunk,model.tokenizer));assert torch.isfinite(loss);(loss/len(group)).backward();micro+=1;losses.append(float(loss))
                if micro==1:
                    nonzero=sum(p.grad is not None and bool(torch.count_nonzero(p.grad)) for p in parameters);assert nonzero>0;log({'type':'gradient_check','nonzero_adapter_gradient_tensors':nonzero})
            torch.nn.utils.clip_grad_norm_(parameters,1.);optimizer.step();scheduler.step();step+=1
            if step%25==0:log({'type':'train','epoch':epoch,'loss':float(np.mean(losses[-200:])),'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20})
        m=validate();score=float(np.mean([v['token_nll'] for v in m.values()]));initial=float(np.mean([v['token_nll'] for v in baseline.values()]));eligible=score<initial-.03 and all(m[s]['token_nll']<=baseline[s]['token_nll']+.10 for s in m)
        if eligible and (best is None or score<best['score']):best={'epoch':epoch,'step':step,'metrics':m,'score':score};model.save(folder/'best');bad_epochs=0
        else:bad_epochs+=1
        model.save(folder/f'epoch_{epoch}');log({'type':'validation','epoch':epoch,'metrics':m,'eligible':bool(eligible),'selected_epoch':best['epoch'] if best else None})
        if epoch>=protocol['min_epochs'] and bad_epochs>=protocol['patience_epochs']:break
    result={'checkpoint':str(folder/'best') if best else None,'selected':best,'baseline_validation':baseline,'actual_steps':step,'actual_micro_steps':micro,'epochs_completed':epoch,'early_stopped':epoch<protocol['epochs'],'seconds':time.time()-started,'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20,'test_used':False,'deployment_changed':False}
    (folder/'selection.json').write_text(json.dumps(result,indent=2),encoding='utf-8');log({'type':'complete',**result});stream.close()

if __name__=='__main__':main()
