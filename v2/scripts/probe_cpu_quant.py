import sys,time,json,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch
from peft import LoraConfig,get_peft_model
from types import SimpleNamespace
from social_world_zh.model import backbone,TARGETS
from social_world_zh.quantized import export_cpu,QuantizedSocialModel
from social_world_zh.spec import HEADS,state_text
torch.set_num_threads(2);started=time.time()
base,cfg=backbone(ROOT/'models/qwen35_0.8B','cpu')
model=SimpleNamespace(backbone=get_peft_model(base,LoraConfig(r=8,lora_alpha=16,target_modules=TARGETS)),heads=torch.nn.ModuleDict({k:torch.nn.Linear(cfg.hidden_size,len(v)) for k,v in HEADS.items()}))
path=ROOT/'tools/quant_probe_08.pt'
export_cpu(model,path);del model,base;gc.collect()
model=QuantizedSocialModel(path)
encoded=model.tokenizer([state_text([],'请帮我打开客厅灯')],return_tensors='pt')
with torch.inference_mode():
    times=[]
    for _ in range(3):
        t=time.time();result=model(**encoded);times.append(time.time()-t)
report={'finite':all(bool(torch.isfinite(x).all()) for x in result.values()),'latency_seconds':times,'seconds':time.time()-started,'bytes':path.stat().st_size,'purpose':'untrained 0.8B operator and serialization smoke only, not delivered model quality'}
(ROOT/'reports/quant_probe.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
