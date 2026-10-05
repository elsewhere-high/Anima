import sys,json,time,hashlib,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch
from social_world_zh.model import SocialModel
from social_world_zh.quantized import export_cpu,QuantizedSocialModel
torch.set_num_threads(4);start=time.time()
model=SocialModel('cpu',checkpoint=ROOT/'models/social_zh/best').eval()
path=ROOT/'models/social_zh/cpu_int8.pt'
export_cpu(model,path);del model;gc.collect()
model=QuantizedSocialModel(path)
text='任务：理解当前中文对话状态。\n历史：\n\n当前用户：帮我打开客厅灯\n当前状态：'
batch=model.tokenizer([text],return_tensors='pt')
with torch.inference_mode():out=model(**batch)
report={'format':'INT8 dynamic linear weights, BF16 embedding, FP32 recurrent/state operators','bytes':path.stat().st_size,'sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),'seconds':time.time()-start,'smoke_finite':all(bool(torch.isfinite(x).all()) for x in out.values()),'not_npu_compiled':True}
(ROOT/'reports/cpu_export.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
