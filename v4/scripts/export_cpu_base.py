"""Quantize the unadapted base once; task adapters remain separate and switchable."""
import sys,json,time,hashlib,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch
from social_v4.runtime_model import V2
from social_world_zh.model import backbone
from social_world_zh.quantized import replace_linears,FloatOutputEmbedding

def main():
    torch.set_num_threads(4);start=time.time();path=ROOT/'models/cpu_base_int8.pt';path.parent.mkdir(exist_ok=True)
    if path.exists():raise RuntimeError('CPU base already exported')
    base,cfg=backbone(V2/'models/qwen35_2B','cpu');base.requires_grad_(False).eval();replace_linears(base,True)
    for name,param in base.named_parameters():
        if name!='embed_tokens.weight':param.data=param.data.float()
    for module in base.modules():
        for name,buffer in module.named_buffers(recurse=False):
            if buffer.is_floating_point():setattr(module,name,buffer.float())
    base.embed_tokens.__class__=FloatOutputEmbedding
    torch.save({'format':'v4_unadapted_shared_int8_base','base_revision':'15852e8c16360a2fea060d615a32b45270f8a8fc','config':cfg.to_dict(),'backbone':base.state_dict()},path)
    del base;gc.collect()
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    report={'file':str(path),'sha256':sha,'bytes':path.stat().st_size,'seconds':time.time()-start,'adapter_merged':False,'not_npu_or_bpu_compiled':True,'runtime_test_pending':True}
    (ROOT/'reports/cpu_export.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
