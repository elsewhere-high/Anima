"""Shared INT8 CPU base with small FP32 task LoRA routes; no model duplication."""
import json,gc,contextlib
from pathlib import Path
import torch
from safetensors.torch import load_file
from transformers import Qwen3_5TextModel,Qwen3_5TextConfig,AutoTokenizer
from accelerate import init_empty_weights
from .runtime_model import ROOT,V2,STATE_LABELS
from social_world_zh.model import checkpoint_fingerprint
from social_world_zh.spec import HEADS
from social_world_zh.quantized import replace_linears,FloatOutputEmbedding


class RoutedLinear(torch.nn.Module):
    def __init__(self,base):
        super().__init__();self.base=base;self.active='default';self.scales={}
    def add(self,name,a,b,scale):
        self.register_buffer(name+'_a',a.float());self.register_buffer(name+'_b',b.float());self.scales[name]=scale
    def forward(self,x):
        out=self.base(x.float())
        if self.active in self.scales:
            a=getattr(self,self.active+'_a');b=getattr(self,self.active+'_b')
            out=out+torch.nn.functional.linear(torch.nn.functional.linear(x.float(),a),b)*self.scales[self.active]
        return out


class RoutedBackbone(torch.nn.Module):
    autocast_enabled=False
    def __init__(self,model):
        super().__init__();self.model=model;self.active_adapter='default';self.routes=[]
    def get_input_embeddings(self):return self.model.get_input_embeddings()
    def forward(self,**kwargs):return self.model(**kwargs)
    def set_adapter(self,name):
        self.active_adapter=name
        for layer in self.routes:layer.active=name
    @contextlib.contextmanager
    def disable_adapter(self):
        previous=self.active_adapter;self.set_adapter('base')
        try:yield
        finally:self.set_adapter(previous)
    def load_adapter(self,path,name):
        path=Path(path);cfg=json.loads((path/'adapter_config.json').read_text());weights=load_file(str(path/'adapter_model.safetensors'))
        if cfg.get('use_dora') or cfg.get('use_rslora') or cfg.get('rank_pattern') or cfg.get('alpha_pattern') or cfg.get('bias')!='none':raise ValueError('Unsupported CPU LoRA configuration')
        consumed=set()
        for key,a in weights.items():
            if not key.endswith('.lora_A.weight'):continue
            name_path=key.removeprefix('base_model.model.').removesuffix('.lora_A.weight')
            module=self.model.get_submodule(name_path)
            if not isinstance(module,RoutedLinear):
                if not isinstance(module,torch.ao.nn.quantized.dynamic.Linear):raise TypeError(name_path)
                parent,child=name_path.rsplit('.',1);module=RoutedLinear(module);setattr(self.model.get_submodule(parent),child,module);self.routes.append(module)
            bkey=key.replace('.lora_A.weight','.lora_B.weight');b=weights[bkey]
            assert a.shape[0]==cfg['r'] and b.shape[1]==cfg['r']
            module.add(name,a,b,cfg['lora_alpha']/cfg['r']);consumed.update([key,bkey])
        if consumed!=set(weights):raise ValueError('Unconsumed CPU adapter parameters')


class SharedCPUModel(torch.nn.Module):
    def __init__(self,state_checkpoint=None,dialogue_checkpoint=None):
        super().__init__();self.device_name='cpu';self.checkpoint_fingerprint=checkpoint_fingerprint(V2/'models/social_zh/best')
        path=ROOT/'models/cpu_base_int8.pt';saved=torch.load(path,map_location='cpu',weights_only=True)
        if saved['format']!='v4_unadapted_shared_int8_base' or saved['base_revision']!='15852e8c16360a2fea060d615a32b45270f8a8fc':raise ValueError('Unexpected CPU base')
        cfg=Qwen3_5TextConfig(**saved['config']);cfg._attn_implementation='sdpa'
        with init_empty_weights(include_buffers=False):base=Qwen3_5TextModel(cfg)
        base.embed_tokens.__class__=FloatOutputEmbedding;replace_linears(base,False)
        base.load_state_dict(saved['backbone'],strict=True,assign=True);del saved;gc.collect()
        self.backbone=RoutedBackbone(base);self.backbone.load_adapter(V2/'models/social_zh/best/adapter','default')
        self.heads=torch.nn.ModuleDict({k:torch.nn.Linear(cfg.hidden_size,len(v)) for k,v in HEADS.items()})
        self.heads.load_state_dict(torch.load(V2/'models/social_zh/best/heads.pt',map_location='cpu',weights_only=True))
        self.state_heads=None
        if state_checkpoint:
            state_checkpoint=Path(state_checkpoint);self.backbone.load_adapter(state_checkpoint/'adapter','current_state')
            self.state_heads=torch.nn.ModuleDict({k:torch.nn.Linear(cfg.hidden_size,len(v)) for k,v in STATE_LABELS.items()})
            weights=torch.load(state_checkpoint/'heads.pt',map_location='cpu',weights_only=True);self.state_heads.load_state_dict({k:v for k,v in weights.items() if k.split('.')[0] in STATE_LABELS})
        self.dialogue_loaded=bool(dialogue_checkpoint)
        if dialogue_checkpoint:self.backbone.load_adapter(Path(dialogue_checkpoint)/'adapter','dialogue')
        self.tokenizer=AutoTokenizer.from_pretrained(V2/'models/qwen35_2B',local_files_only=True);self.tokenizer.padding_side='right';self.tokenizer.truncation_side='left'
        self.requires_grad_(False);self.eval()
    @contextlib.contextmanager
    def route(self,name):
        try:
            self.backbone.set_adapter(name);yield
        finally:self.backbone.set_adapter('default')
    def _forward(self,route,heads,inputs):
        with self.route(route):h=self.backbone(**inputs,use_cache=False).last_hidden_state
        h=h[torch.arange(len(h)),inputs['attention_mask'].sum(1)-1].float()
        return {k:head(h) for k,head in heads.items()}
    def original_logits(self,**inputs):return self._forward('default',self.heads,inputs)
    def state_logits(self,**inputs):return self._forward('current_state',self.state_heads,inputs)
