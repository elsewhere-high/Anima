"""Fixed held-out likelihood and predeclared development responses; not a field trial."""
import sys, json, time, hashlib, contextlib, collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch
import numpy as np
from social_v4.chat_model import DialogueModel,collate_chat,generate_text
from social_v4.dialogue import format_messages


def main():
    torch.set_num_threads(4);torch.manual_seed(20260927);started=time.time()
    folder=ROOT/'runs/dialogue_repair_v2';selection=json.loads((folder/'selection.json').read_text());report_path=ROOT/'reports/dialogue_repair_evaluation.json'
    if report_path.exists():raise RuntimeError('Fixed dialogue evaluation already exists')
    if not selection['checkpoint']:
        report_path.write_text(json.dumps({'status':'no_validation_qualified_checkpoint','generation_review_required':True},indent=2),encoding='utf-8');return
    checkpoint=Path(selection['checkpoint']);model=DialogueModel(checkpoint=checkpoint).eval()
    file=ROOT/'data/dialogue_repair_v2/test.jsonl';manifest=json.loads((ROOT/'data/dialogue_repair_v2/manifest.json').read_text(encoding='utf-8'));assert hashlib.sha256(file.read_bytes()).hexdigest()==manifest['files']['test']['sha256']
    rows=[json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
    cases_file=ROOT/'data/dialogue_development_cases.json';cases=json.loads(cases_file.read_text(encoding='utf-8'))
    protocol={'test_sha256':manifest['files']['test']['sha256'],'development_cases_sha256':hashlib.sha256(cases_file.read_bytes()).hexdigest(),'generation':'Greedy, max128tokens, timeout20sec, same system/history for base and trained','generation_review':'Manual rubric on predeclared authored development probes; not independent home test or a population accuracy estimate','no_test_checkpoint_selection':True,'prompt_version':'v4-grounded-2','public_test_and_original_development_previously_seen':True,'synthetic_test_is_template_based_not_field_trial':True,'nll_release':'Each held-out source token NLL <= base+.10 and mean source NLL lower than base','generation_release':'Review responses for grounding, context, empathy and instruction-following; do not promote if critical regressions vs base'}
    (folder/'evaluation_protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    likelihood={}
    for route in ['base','trained']:
        totals=collections.defaultdict(lambda:[0.,0,0])
        with torch.inference_mode(),model.backbone.disable_adapter() if route=='base' else contextlib.nullcontext():
            for source in sorted({r['source'] for r in rows}):
                subset=sorted([r for r in rows if r['source']==source],key=lambda r:len(r['input_ids']))
                for start in range(0,len(subset),2):
                    chunk=subset[start:start+2];loss,n=model.loss(**collate_chat(chunk,model.tokenizer));totals[source][0]+=float(loss)*n;totals[source][1]+=n;totals[source][2]+=len(chunk)
        likelihood[route]={s:{'token_nll':a/n,'target_tokens':n,'examples':m} for s,(a,n,m) in totals.items()}
        print(json.dumps({'type':'test_likelihood','route':route,'metrics':likelihood[route]}),flush=True)
    results=[]
    synthetic_results=[]
    for case in [r for r in rows if r['source']=='grounded_authored']:
        row={k:case[k] for k in ['id','family','group','required','required_any','forbidden']};m=case['messages'];history=[(v['role'],v['content']) for v in m[:-2]]
        for route in ['base','trained']:
            with model.backbone.disable_adapter() if route=='base' else contextlib.nullcontext():
                out=generate_text(model.backbone,model.tokenizer,format_messages(history,m[-2]['content']))
            reply=out['reply'];out['predicate_pass']=all(x in reply for x in row['required']) and (not row['required_any'] or any(x in reply for x in row['required_any'])) and not any(x in reply for x in row['forbidden'])
            row[route]=out
        synthetic_results.append(row)
        print(json.dumps({'type':'synthetic_generation','id':row['id'],'base':row['base']['reply'],'trained':row['trained']['reply']},ensure_ascii=False),flush=True)
    (ROOT/'reports/dialogue_repair_synthetic_responses.json').write_text(json.dumps(synthetic_results,ensure_ascii=False,indent=2),encoding='utf-8')
    with (ROOT/'reports/dialogue_repair_development_responses.jsonl').open('w',encoding='utf-8') as output:
        for case in cases:
            row=dict(case)
            for route in ['base','trained']:
                with model.backbone.disable_adapter() if route=='base' else contextlib.nullcontext():
                    row[route]=generate_text(model.backbone,model.tokenizer,format_messages(case['history'],case['speech']))
                print(json.dumps({'type':'generation','id':case['id'],'route':route,**row[route]},ensure_ascii=False),flush=True)
            results.append(row);output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush()
    a=likelihood['base'];b=likelihood['trained'];nll_pass=all(b[s]['token_nll']<=a[s]['token_nll']+.10 for s in a) and np.mean([b[s]['token_nll'] for s in a])<np.mean([a[s]['token_nll'] for s in a])
    result={'status':'evaluated_manual_review_pending','checkpoint':str(checkpoint),'adapter_sha256':hashlib.sha256((checkpoint/'adapter/adapter_model.safetensors').read_bytes()).hexdigest(),'likelihood':likelihood,'nll_gate_passed':bool(nll_pass),'development_cases':len(cases),'synthetic_test_generation_count':len(synthetic_results),'synthetic_predicate_diagnostics':{r:sum(x[r]['predicate_pass'] for x in synthetic_results)/len(synthetic_results) for r in ['base','trained']},'generation_review_required':True,'protocol':protocol,'latency_seconds':{r:{'p50':float(np.median([c[r]['elapsed_seconds'] for c in results])),'p95':float(np.percentile([c[r]['elapsed_seconds'] for c in results],95))} for r in ['base','trained']},'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20,'seconds':time.time()-started,'deployment_changed':False}
    report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
