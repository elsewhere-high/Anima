import json,gc,contextlib,hashlib
import torch
from safetensors import safe_open
from transformers import Qwen3_5TextConfig,Qwen3_5TextModel,AutoTokenizer
from peft import LoraConfig,get_peft_model,PeftModel
from accelerate import init_empty_weights
from .spec import ROOT,HEADS,MAX_LENGTH

TARGETS=['q_proj','k_proj','v_proj','o_proj','in_proj_qkv','in_proj_z','in_proj_a','in_proj_b','out_proj']
def checkpoint_fingerprint(path):
    digest=hashlib.sha256()
    for file in [path/'heads.pt',path/'adapter/adapter_model.safetensors']:
        with file.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()
def backbone(folder,device):
    cfg=Qwen3_5TextConfig(**json.loads((folder/'config.json').read_text())['text_config'])
    cfg._attn_implementation='sdpa'
    with init_empty_weights(include_buffers=False):model=Qwen3_5TextModel(cfg)
    weights={}
    for path in folder.glob('*.safetensors'):
        with safe_open(path,framework='pt',device='cpu') as f:
            for k in f.keys():
                if k.startswith('model.language_model.'):weights[k.removeprefix('model.language_model.')]=f.get_tensor(k)
    model.load_state_dict(weights,strict=True,assign=True);del weights
    # Keep the non-persistent RoPE buffers in FP32.
    return model.to(device),cfg

class SocialModel(torch.nn.Module):
    def __init__(self,device='cuda',checkpoint=None,training=False):
        super().__init__();self.device_name=device
        self.checkpoint_fingerprint=checkpoint_fingerprint(checkpoint) if checkpoint else None
        base=ROOT/'models/qwen35_2B'
        self.backbone,cfg=backbone(base,device)
        if checkpoint:
            self.backbone=PeftModel.from_pretrained(self.backbone,str(checkpoint/'adapter'),is_trainable=training)
        else:
            self.backbone=get_peft_model(self.backbone,LoraConfig(r=8,lora_alpha=16,lora_dropout=.05,target_modules=TARGETS))
        self.heads=torch.nn.ModuleDict({k:torch.nn.Linear(cfg.hidden_size,len(labels)) for k,labels in HEADS.items()}).to(device)
        if checkpoint:self.heads.load_state_dict(torch.load(checkpoint/'heads.pt',map_location=device,weights_only=True))
        if training:
            self.backbone.enable_input_require_grads()
            self.backbone.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        self.tokenizer=AutoTokenizer.from_pretrained(base,local_files_only=True)
        self.tokenizer.padding_side='right';self.tokenizer.truncation_side='left'
    def forward(self,input_ids,attention_mask):
        with torch.autocast(self.device_name,dtype=torch.bfloat16):
            hidden=self.backbone(input_ids=input_ids,attention_mask=attention_mask,use_cache=False).last_hidden_state
            pooled=hidden[torch.arange(hidden.shape[0],device=hidden.device),attention_mask.sum(1)-1].float()
        return {k:h(pooled) for k,h in self.heads.items()}
    def save(self,path):
        path.mkdir(parents=True,exist_ok=True)
        self.backbone.save_pretrained(path/'adapter')
        torch.save(self.heads.state_dict(),path/'heads.pt')
        (path/'spec.json').write_text(json.dumps({'heads':HEADS,'max_length':MAX_LENGTH,'base':'Qwen/Qwen3.5-2B','base_revision':'15852e8c16360a2fea060d615a32b45270f8a8fc','pooling':'last_nonpad','format_version':2},ensure_ascii=False,indent=2),encoding='utf-8')

def collate(rows,tokenizer,device):
    batch=tokenizer.pad({'input_ids':[r['tokens'] for r in rows]},padding=True,pad_to_multiple_of=8,return_tensors='pt')
    batch={k:v.to(device) for k,v in batch.items()}
    labels={k:torch.tensor([r['labels'].get(k,-100) for r in rows],device=device) for k in HEADS}
    return batch,labels

def load_rows(split,tokenizer):
    path=ROOT/'data/processed'/f'{split}.jsonl'
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    tokens=tokenizer([r['text'] for r in rows],truncation=True,max_length=MAX_LENGTH,add_special_tokens=True)['input_ids']
    for r,ids in zip(rows,tokens):r['tokens']=ids
    return rows
