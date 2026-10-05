"""Evaluate the already-trained state heads for the user's revised current-state objective."""
import sys,json,time,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT.parent;V2=WORK/'v2';V3=WORK/'v3'
sys.path[:0]=[str(V2),str(V3),str(V3/'scripts')]
import torch,numpy as np
from social_world_zh.model import SocialModel,checkpoint_fingerprint
from social_world_zh.spec import HEADS
from evaluate import metrics

def main():
    started=time.time();torch.set_num_threads(4)
    folder=ROOT/'runs/state_head_candidate';folder.mkdir(parents=True,exist_ok=True);reports=ROOT/'reports';reports.mkdir(exist_ok=True)
    if (folder/'protocol.json').exists():raise RuntimeError('Existing run; do not overwrite fixed evaluation')
    protocol={'scope':'User changed priority to CURRENT state and dialogue on 2026-09-26. Future prediction is not a release gate in V4.',
        'candidate':'Already selected V3 full-state head refinement gamma=.35 epoch=5; no further weight selection on TEST.',
        'validation_gate':'Both current task accuracy >= max(archived,same-execution V2)-.005 and macro F1 >= max(...)+.005.',
        'test_gate':'Both current task accuracy >= max(archived,same-execution V2)-.005 and macro F1 >= max(...)+.005. Other current-task heads and adapter bit-identical.',
        'test_limitation':'Fixed public benchmark has previously been inspected in this project. Candidate is locked, but this is not a new untouched target-home test.',
        'max_length':256,'batch':12,'current_tasks':['emotion','dialog_act','intent','boundary','policy','task_domain'],'test_used':False,'deployment_changed':False}
    (folder/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    source=V2/'models/social_zh/best';ref=json.loads((V3/'reports/v2_state_refinement.json').read_text(encoding='utf-8'));checkpoint=torch.load(V3/'runs/v2_state_refinement/state_heads.pt',map_location='cpu',weights_only=True)
    assert checkpoint['selection']==ref['state_selection'] and checkpoint_fingerprint(source)==ref['source_checkpoint_fingerprint']
    model=SocialModel(checkpoint=source).eval();original={k:v.detach().clone() for k,v in model.heads.state_dict().items()}
    updated=dict(original);updated.update({k:v.cuda() for k,v in checkpoint['state_dict'].items()});model.heads.load_state_dict(updated)
    assert all(torch.equal(original[k],v) for k,v in model.heads.state_dict().items() if k.split('.')[0] not in ['emotion','dialog_act'])
    calibration=json.loads((V2/'reports/calibration.json').read_text(encoding='utf-8'));temps=dict(calibration['temperatures']);temps.update(ref['state_temperatures'])
    report={'protocol':protocol,'source_fingerprint':model.checkpoint_fingerprint,'state_selection':ref['state_selection'],'encoder_adapter_unchanged':True,'nonstate_heads_unchanged':True,'test_used':False,'deployment_changed':False,'temperatures':temps}
    def evaluate(split):
        path=V3/'data'/f'{split}.jsonl';sha=hashlib.sha256(path.read_bytes()).hexdigest();manifest=json.loads((V3/'data/manifest.json').read_text(encoding='utf-8'));assert sha==manifest[split]['sha256']
        rows=[r for line in path.read_text(encoding='utf-8').splitlines() if (r:=json.loads(line))['source']!='cped_transition']
        tokens=model.tokenizer([r['text'] for r in rows],truncation=True,max_length=256)['input_ids'];order=sorted(range(len(rows)),key=lambda i:len(tokens[i]));arr={mode:{k:np.zeros((len(rows),len(HEADS[k])),np.float32) for k in protocol['current_tasks']} for mode in ['candidate','v2_same_execution']}
        with torch.inference_mode():
            for pos in range(0,len(order),12):
                ix=order[pos:pos+12];inp=model.tokenizer.pad({'input_ids':[tokens[i] for i in ix]},padding=True,pad_to_multiple_of=8,return_tensors='pt').to('cuda')
                with torch.autocast('cuda',dtype=torch.bfloat16):h=model.backbone(**inp,use_cache=False).last_hidden_state
                x=h[torch.arange(len(ix),device='cuda'),inp['attention_mask'].sum(1)-1].float()
                for k in protocol['current_tasks']:
                    a=model.heads[k](x);b=torch.nn.functional.linear(x,original[k+'.weight'],original[k+'.bias'])
                    if k not in ['emotion','dialog_act']:assert torch.equal(a,b)
                    arr['candidate'][k][ix]=a.cpu().numpy();arr['v2_same_execution'][k][ix]=b.cpu().numpy()
                if pos%600==0:print(json.dumps({'stage':split,'done':min(pos+12,len(order)),'total':len(order),'seconds':time.time()-started}),flush=True)
        result={}
        for k in protocol['current_tasks']:
            ix=[i for i,r in enumerate(rows) if k in r['labels']];y=np.array([rows[i]['labels'][k] for i in ix]);result[k]={mode:metrics(y,values[k][ix]/(temps[k] if mode=='candidate' else calibration['temperatures'][k])) for mode,values in arr.items()}
        np.savez_compressed(folder/(split+'_logits.npz'),**{mode+'_'+k:v for mode,d in arr.items() for k,v in d.items()});(folder/(split+'_ids.json')).write_text(json.dumps([r['id'] for r in rows]),encoding='utf-8')
        return {'sha256':sha,'heads':result}
    validation=evaluate('validation');report['validation']=validation
    def gate(values,archive):return all(values[k]['candidate']['accuracy']>=max(values[k]['v2_same_execution']['accuracy'],archive[k]['accuracy'])-.005 and values[k]['candidate']['macro_f1']>=max(values[k]['v2_same_execution']['macro_f1'],archive[k]['macro_f1'])+.005 for k in ['emotion','dialog_act'])
    report['validation_passed']=gate(validation['heads'],{k:calibration['metrics'][k]['before'] for k in ['emotion','dialog_act']})
    if report['validation_passed']:
        test=evaluate('test');archive=json.loads((V2/'reports/evaluation.json').read_text(encoding='utf-8'))['heads'];report.update(test=test,test_used=True,test_passed=gate(test['heads'],archive))
        for k in protocol['current_tasks']:test['heads'][k]['v2_archived']=archive[k]
        if report['test_passed']:
            target=ROOT/'models/state_candidate';model.save(target);report['checkpoint']=str(target);report['candidate_fingerprint']=checkpoint_fingerprint(target)
            (target/'calibration.json').write_text(json.dumps({'checkpoint_fingerprint':report['candidate_fingerprint'],'temperatures':temps},indent=2),encoding='utf-8')
    report.update(seconds=time.time()-started,peak_vram_mib=torch.cuda.max_memory_allocated()/2**20)
    (reports/'state_candidate_evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (folder/'selection.json').write_text(json.dumps({'checkpoint':report.get('checkpoint'),'test_used':report['test_used'],'test_passed':report.get('test_passed',False),'deployment_changed':False},indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['validation_passed','test_used','seconds','peak_vram_mib']}|{'test_passed':report.get('test_passed'),'checkpoint':report.get('checkpoint'),'current_state_test':{k:report.get('test',{}).get('heads',{}).get(k) for k in ['emotion','dialog_act']}},indent=2),flush=True)

if __name__=='__main__':main()
