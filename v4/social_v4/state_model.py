import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];V2=ROOT.parent/'v2';sys.path.insert(0,str(V2))
import torch
from peft import PeftModel
from transformers import AutoTokenizer
from social_world_zh.model import backbone
from social_world_zh.spec import HEADS

class StateModel(torch.nn.Module):
    def __init__(self,checkpoint=None,training=False):
        super().__init__();checkpoint=checkpoint or V2/'models/social_zh/best'
        base,cfg=backbone(V2/'models/qwen35_2B','cuda');self.backbone=PeftModel.from_pretrained(base,str(checkpoint/'adapter'),is_trainable=training)
        self.heads=torch.nn.ModuleDict({k:torch.nn.Linear(cfg.hidden_size,len(labels)) for k,labels in {**HEADS,'sentiment':['negative','neutral','positive']}.items()}).cuda()
        missing,unexpected=self.heads.load_state_dict(torch.load(checkpoint/'heads.pt',map_location='cuda',weights_only=True),strict=False)
        assert not unexpected and set(missing).issubset({'sentiment.weight','sentiment.bias'})
        for k,head in self.heads.items():
            for p in head.parameters():p.requires_grad_(training and k in ['emotion','dialog_act','sentiment'])
        if training:self.backbone.enable_input_require_grads();self.backbone.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        self.tokenizer=AutoTokenizer.from_pretrained(V2/'models/qwen35_2B',local_files_only=True);self.tokenizer.padding_side='right';self.tokenizer.truncation_side='left'
    def forward(self,**inputs):
        with torch.autocast('cuda',dtype=torch.bfloat16):h=self.backbone(**inputs,use_cache=False).last_hidden_state
        h=h[torch.arange(len(h),device='cuda'),inputs['attention_mask'].sum(1)-1].float()
        return {k:self.heads[k](h) for k in ['emotion','dialog_act','sentiment']}
    def save(self,path):
        path.mkdir(parents=True,exist_ok=True);self.backbone.save_pretrained(path/'adapter');torch.save(self.heads.state_dict(),path/'heads.pt')
        (path/'spec.json').write_text(json.dumps({'format_version':4,'base':'Qwen/Qwen3.5-2B','base_revision':'15852e8c16360a2fea060d615a32b45270f8a8fc','max_length':256,'trained_tasks':['emotion','dialog_act','sentiment'],'sentiment_labels':['negative','neutral','positive'],'runtime_note':'Use this adapter only for current emotion/dialogue-act/sentiment. Intent/policy retain original V2 adapter; shared physical backbone.'},indent=2),encoding='utf-8')
