import pathlib,sys,json,time,argparse,gc
ROOT=pathlib.Path(__file__).resolve().parents[1]
import torch
from safetensors import safe_open
from transformers import Qwen3_5TextConfig,Qwen3_5TextModel,AutoTokenizer
from peft import LoraConfig,get_peft_model
from accelerate import init_empty_weights
p=argparse.ArgumentParser();p.add_argument('--size',default='0.8B');p.add_argument('--batch',type=int,default=2);p.add_argument('--length',type=int,default=128);a=p.parse_args()
torch.set_num_threads(4);torch.manual_seed(42)
folder=ROOT/'models'/('qwen35_'+a.size)
config=Qwen3_5TextConfig(**json.loads((folder/'config.json').read_text())['text_config'])
config._attn_implementation='sdpa'
with init_empty_weights(include_buffers=False): model=Qwen3_5TextModel(config)
state={}
for file in folder.glob('*.safetensors'):
    with safe_open(file,framework='pt',device='cpu') as f:
        if not state: print('KEYS',list(f.keys())[:6],flush=True)
        for k in f.keys():
            if k.startswith('model.language_model.'): state[k.removeprefix('model.language_model.')]=f.get_tensor(k)
missing=model.load_state_dict(state,assign=True,strict=True);del state
model=model.to('cuda')
targets=['q_proj','k_proj','v_proj','o_proj','in_proj_qkv','in_proj_z','in_proj_a','in_proj_b','out_proj']
model=get_peft_model(model,LoraConfig(r=8,lora_alpha=16,lora_dropout=.05,target_modules=targets))
model.enable_input_require_grads();model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
head=torch.nn.Linear(config.hidden_size,19).cuda()
opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad]+list(head.parameters()),lr=2e-4)
ids=torch.randint(0,10000,(a.batch,a.length),device='cuda');mask=torch.ones_like(ids);times=[]
for i in range(3):
    opt.zero_grad(set_to_none=True);begin=time.perf_counter()
    with torch.autocast('cuda',dtype=torch.bfloat16):
        h=model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state[:,-1].float();loss=torch.nn.functional.cross_entropy(head(h),torch.zeros(a.batch,dtype=torch.long,device='cuda'))
    loss.backward();opt.step();torch.cuda.synchronize();times.append(time.perf_counter()-begin)
    print('STEP',i,times[-1],'VRAM',torch.cuda.max_memory_allocated()/2**20,flush=True)
report={'model':a.size,'batch':a.batch,'length':a.length,'step_seconds':times,'peak_vram_mib':torch.cuda.max_memory_allocated()/2**20,'trainable':sum(p.numel() for p in model.parameters() if p.requires_grad),'parameters':sum(p.numel() for p in model.parameters()),'torch':torch.__version__}
(ROOT/'reports'/f'probe_{a.size}.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
