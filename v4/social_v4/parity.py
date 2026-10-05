"""Quantization fidelity probe on fixed validation examples, not a new accuracy test."""
import json,hashlib
import numpy as np
import torch
from .runtime_model import ROOT,V2

def run_probe(model,device):
    inputs_file=ROOT/'reports/runtime_parity_inputs.json';gpu_file=ROOT/'reports/runtime_parity_cuda.npz'
    if device=='cuda':
        current=[json.loads(line) for line in (ROOT/'data/state/validation.jsonl').read_text(encoding='utf-8').splitlines()]
        original=[json.loads(line) for line in (V2/'data/processed/validation.jsonl').read_text(encoding='utf-8').splitlines()]
        order=lambda rows:sorted(rows,key=lambda r:hashlib.sha256(r['id'].encode()).hexdigest())
        selected={}
        for source,n in [('cped_state',64),('chinese_medd',32)]:
            for row in order([r for r in current if r['source']==source])[:n]:selected['current:'+row['id']]={**row,'origin':'current'}
        for task in ['intent','policy','boundary','task_domain']:
            for row in order([r for r in original if task in r['labels']])[:24]:
                selected['original:'+row['id']]={**row,'origin':'original'}
        rows=[{'id':k,'text':r['text'],'label_keys':list(r['labels']),'origin':r['origin']} for k,r in sorted(selected.items())]
        inputs_file.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    else:rows=json.loads(inputs_file.read_text(encoding='utf-8'))
    arrays={};batch_size=4  # Identical grouping and padding on both backends.
    with torch.inference_mode():
        for start in range(0,len(rows),batch_size):
            chunk=rows[start:start+batch_size]
            inputs=model.tokenizer([r['text'] for r in chunk],padding=True,truncation=True,max_length=256,return_tensors='pt').to(device)
            scores={'original_'+k:x for k,x in model.original_logits(**inputs).items() if not k.startswith('next_')}
            if model.state_heads is not None:scores.update({'current_'+k:x for k,x in model.state_logits(**inputs).items()})
            for k,x in scores.items():arrays.setdefault(k,[]).append(x.float().cpu().numpy())
    arrays={k:np.concatenate(v) for k,v in arrays.items()};np.savez_compressed(ROOT/'reports'/('runtime_parity_'+device+'.npz'),**arrays)
    result={'n':len(rows),'split':'fixed validation probe','type':'CPU vs GPU argmax agreement, not task accuracy','input_sha256':hashlib.sha256(inputs_file.read_bytes()).hexdigest()}
    if device=='cpu':
        gpu=np.load(gpu_file);comparisons={}
        for k,x in arrays.items():
            origin,task=k.split('_',1)
            ix=[i for i,r in enumerate(rows) if r['origin']==origin and task in r['label_keys']]
            if not ix:continue
            a=gpu[k][ix];b=x[ix];comparisons[k]={'n':len(ix),'top1_agreement':float((a.argmax(-1)==b.argmax(-1)).mean()),'mean_absolute_logit_difference':float(np.abs(a-b).mean()),'max_absolute_logit_difference':float(np.abs(a-b).max())}
        result['comparison']=comparisons
    return result
