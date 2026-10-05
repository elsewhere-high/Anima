"""Bounded second SFT; validation-only selection after documented first-run rejection."""
import sys,json,time,math,hashlib,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch,numpy as np
from social_v4.chat_model import DialogueModel,collate_chat,generate_text
from social_v4.dialogue import format_messages,PROMPT_VERSION
from snapshot_code import snapshot

def main():
    started=time.time();seed=20260928;torch.manual_seed(seed);torch.set_num_threads(4)
    folder=ROOT/'runs/dialogue_repair_v2';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'protocol.json').exists():raise RuntimeError('Existing run is immutable')
    protocol={'seed':seed,'epochs':3,'micro_batch':2,'gradient_accumulation':8,'learning_rate':2e-5,'max_length':768,'prompt_version':PROMPT_VERSION,'source_repeat':{'opens2s_zh':1,'oasst2_zh':2,'home_authored':2,'grounded_authored':3},'initial_checkpoint':'runs/dialogue_sft/best','selection':'Keep each public validation source NLL <= initial+.12; authored validation NLL improves by at least .10; generation validation predicate rate not below initial. Select highest generation validation rate, then lowest equally weighted source NLL. All three epochs, no test selection. Predicates are diagnostic template checks, not human conversation accuracy.','known_development_adaptation':True,'test_used':False}
    (folder/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    snapshot(folder,['scripts/train_dialogue_repair.py','scripts/build_dialogue_repair_data.py','social_v4/chat_model.py','social_v4/dialogue.py'])
    manifest=json.loads((ROOT/'data/dialogue_repair_v2/manifest.json').read_text(encoding='utf-8'));rows={}
    for split in ['train','validation']:
        path=ROOT/'data/dialogue_repair_v2'/f'{split}.jsonl';assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['files'][split]['sha256']
        rows[split]=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
        for r in rows[split]:
            p=r['prompt_length'];assert r['labels'][:p]==[-100]*p and r['labels'][p:]==r['input_ids'][p:] and len(r['input_ids'])<=768
    probes=json.loads((ROOT/'data/dialogue_repair_v2/generation_validation.json').read_text(encoding='utf-8'))
    assert all(r['id'] in {v['id'] for v in rows['validation']} for r in probes)
    model=DialogueModel(checkpoint=ROOT/protocol['initial_checkpoint'],training=True);parameters=[p for p in model.parameters() if p.requires_grad]
    exposures=[i for i,r in enumerate(rows['train']) for _ in range(protocol['source_repeat'][r['source']])]
    total=math.ceil(math.ceil(len(exposures)/2)/8)*protocol['epochs'];warmup=max(1,round(total*.05))
    optimizer=torch.optim.AdamW(parameters,lr=protocol['learning_rate'],weight_decay=.01)
    scheduler=torch.optim.lr_scheduler.LambdaLR(optimizer,lambda s:min((s+1)/warmup,max(0.,(total-s)/max(1,total-warmup))))
    stream=(folder/'events.jsonl').open('w',encoding='utf-8');step=0;micro=0
    def log(r):
        r.update(step=step,micro_step=micro,seconds=time.time()-started);stream.write(json.dumps(r,ensure_ascii=False)+'\n');stream.flush();print(json.dumps(r,ensure_ascii=False),flush=True)
    def validate(epoch):
        model.eval();totals=collections.defaultdict(lambda:[0.,0,0])
        with torch.inference_mode():
            for source in sorted({r['source'] for r in rows['validation']}):
                subset=sorted([r for r in rows['validation'] if r['source']==source],key=lambda r:len(r['input_ids']))
                for i in range(0,len(subset),2):
                    chunk=subset[i:i+2];loss,n=model.loss(**collate_chat(chunk,model.tokenizer));totals[source][0]+=float(loss)*n;totals[source][1]+=n;totals[source][2]+=len(chunk)
        responses=[]
        for r in probes:
            m=r['messages'];history=[(x['role'],x['content']) for x in m[:-2]]
            out=generate_text(model.backbone,model.tokenizer,format_messages(history,m[-2]['content']),max_new_tokens=96)
            reply=out['reply'];passed=all(x in reply for x in r['required']) and (not r['required_any'] or any(x in reply for x in r['required_any'])) and not any(x in reply for x in r['forbidden'])
            responses.append({'id':r['id'],'family':r['family'],'reply':reply,'predicate_pass':bool(passed)})
        (folder/f'validation_generation_epoch_{epoch}.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2),encoding='utf-8')
        return {s:{'token_nll':v[0]/v[1],'tokens':v[1],'examples':v[2]} for s,v in totals.items()},sum(r['predicate_pass'] for r in responses)/len(responses)
    baseline,initial_rate=validate(0);log({'type':'initial_validation','metrics':baseline,'generation_predicate_rate':initial_rate,'train_unique_n':len(rows['train']),'train_exposures_per_epoch':len(exposures),'planned_optimizer_steps':total,'trainable_parameters':sum(p.numel() for p in parameters)})
    best=None;losses=[]
    for epoch in range(1,protocol['epochs']+1):
        perm=torch.randperm(len(exposures),generator=torch.Generator().manual_seed(seed+epoch)).tolist();ordered=[]
        for pos in range(0,len(perm),128):ordered.extend(sorted([exposures[j] for j in perm[pos:pos+128]],key=lambda i:len(rows['train'][i]['input_ids'])))
        batches=[ordered[i:i+2] for i in range(0,len(ordered),2)]
        for start in range(0,len(batches),8):
            model.train();optimizer.zero_grad(set_to_none=True);group=batches[start:start+8]
            for indices in group:
                loss,n=model.loss(**collate_chat([rows['train'][i] for i in indices],model.tokenizer));assert torch.isfinite(loss);(loss/len(group)).backward();micro+=1;losses.append(float(loss))
                if micro==1:
                    nonzero=sum(p.grad is not None and bool(torch.count_nonzero(p.grad)) for p in parameters);assert nonzero>0;log({'type':'gradient_check','nonzero_adapter_gradient_tensors':nonzero})
            torch.nn.utils.clip_grad_norm_(parameters,1.);optimizer.step();scheduler.step();step+=1
            if step%25==0:log({'type':'train','epoch':epoch,'loss':float(np.mean(losses[-200:])),'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20})
        metrics,rate=validate(epoch);score=float(np.mean([v['token_nll'] for v in metrics.values()]))
        eligible=all(metrics[s]['token_nll']<=baseline[s]['token_nll']+.12 for s in ['opens2s_zh','oasst2_zh']) and metrics['grounded_authored']['token_nll']<baseline['grounded_authored']['token_nll']-.10 and rate>=initial_rate
        if eligible and (best is None or (rate,-score)>(best['generation_predicate_rate'],-best['score'])):
            best={'epoch':epoch,'step':step,'metrics':metrics,'score':score,'generation_predicate_rate':rate};model.save(folder/'best')
        model.save(folder/f'epoch_{epoch}');log({'type':'validation','epoch':epoch,'metrics':metrics,'generation_predicate_rate':rate,'eligible':bool(eligible),'selected_epoch':best['epoch'] if best else None})
    result={'checkpoint':str(folder/'best') if best else None,'selected':best,'baseline_validation':baseline,'initial_generation_predicate_rate':initial_rate,'actual_steps':step,'actual_micro_steps':micro,'epochs_completed':epoch,'seconds':time.time()-started,'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20,'test_used':False,'deployment_changed':False,'prompt_version':PROMPT_VERSION}
    (folder/'selection.json').write_text(json.dumps(result,indent=2),encoding='utf-8');log({'type':'complete',**result});stream.close()

if __name__=='__main__':main()
