"""Portable x86 CPU PyTorch INT8 linears, BF16 embedding, FP32 state operators.

This is NOT an ONNX/NPU/BPU compilation artifact. Architecture and packed weights
are saved as a state_dict and loaded with weights_only=True.
"""
import json,gc
import torch
from transformers import Qwen3_5TextConfig,Qwen3_5TextModel,AutoTokenizer
from accelerate import init_empty_weights
from .spec import ROOT,HEADS

class FloatOutputEmbedding(torch.nn.Embedding):
    def forward(self,ids):return super().forward(ids).float()

def replace_linears(module,from_float):
    for name,child in list(module.named_children()):
        if isinstance(child,torch.nn.Linear):
            if from_float:
                child.float();child.qconfig=torch.ao.quantization.default_dynamic_qconfig
                new=torch.ao.nn.quantized.dynamic.Linear.from_float(child)
            else:new=torch.ao.nn.quantized.dynamic.Linear(child.in_features,child.out_features,bias_=child.bias is not None,dtype=torch.qint8)
            setattr(module,name,new)
        else:replace_linears(child,from_float)

class QuantizedSocialModel(torch.nn.Module):
    def __init__(self,path):
        super().__init__();self.device_name='cpu'
        state=torch.load(path,map_location='cpu',weights_only=True)
        self.checkpoint_fingerprint=state.get('checkpoint_fingerprint')
        cfg=Qwen3_5TextConfig(**state['config']);cfg._attn_implementation='sdpa'
        with init_empty_weights(include_buffers=False):self.backbone=Qwen3_5TextModel(cfg)
        self.backbone.embed_tokens.__class__=FloatOutputEmbedding
        replace_linears(self.backbone,False)
        self.heads=torch.nn.ModuleDict({k:torch.nn.Linear(cfg.hidden_size,len(v)) for k,v in HEADS.items()})
        self.backbone.load_state_dict(state['backbone'],strict=True,assign=True)
        self.heads.load_state_dict(state['heads']);del state;gc.collect()
        self.tokenizer=AutoTokenizer.from_pretrained(ROOT/'models/qwen35_2B',local_files_only=True)
        self.tokenizer.padding_side='right';self.tokenizer.truncation_side='left';self.eval()
    def forward(self,input_ids,attention_mask):
        h=self.backbone(input_ids=input_ids,attention_mask=attention_mask,use_cache=False).last_hidden_state
        h=h[torch.arange(h.shape[0]),attention_mask.sum(1)-1].float()
        return {k:v(h) for k,v in self.heads.items()}

def export_cpu(model,path):
    base=model.backbone.merge_and_unload()
    replace_linears(base,True)
    # Convert the remaining small state/normalization parameters without creating
    # a full FP32 copy of the 1.88B backbone. The 508M embedding stays BF16.
    for name,param in base.named_parameters():
        if name!='embed_tokens.weight':param.data=param.data.float()
    for module in base.modules():
        for name,buffer in module.named_buffers(recurse=False):
            if buffer.is_floating_point():setattr(module,name,buffer.float())
    base.embed_tokens.__class__=FloatOutputEmbedding
    torch.save({'format':'pytorch_dynamic_int8_linears_bf16_embedding_v1','checkpoint_fingerprint':getattr(model,'checkpoint_fingerprint',None),'config':base.config.to_dict(),'backbone':base.state_dict(),'heads':model.heads.state_dict()},path)
    return base
