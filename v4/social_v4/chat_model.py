"""Small response adapter on the same pinned Qwen base; assistant-only language loss."""
import sys,time,contextlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];V2=ROOT.parent/'v2';sys.path.insert(0,str(V2))
import torch
from torch.utils.checkpoint import checkpoint as checkpoint_function
from peft import PeftModel,LoraConfig,get_peft_model
from transformers import AutoTokenizer
from social_world_zh.model import backbone,TARGETS
from .dialogue import trim_old_context

def assistant_loss(hidden, labels, embedding, training=False, chunk_size=64):
    """Causal assistant-only CE, equivalent to full projection without its VRAM peak."""
    mask=labels[:,1:]!=-100;targets=labels[:,1:][mask];h=hidden[:,:-1][mask]
    if len(targets)==0:raise ValueError('No assistant targets')
    loss=0.
    def piece(x,y):return torch.nn.functional.cross_entropy(torch.nn.functional.linear(x.to(embedding.dtype),embedding).float(),y,reduction='sum')
    for start in range(0,len(targets),chunk_size):
        args=(h[start:start+chunk_size],targets[start:start+chunk_size])
        loss=loss+(checkpoint_function(piece,*args,use_reentrant=False) if training else piece(*args))
    return loss/len(targets),len(targets)

class DialogueModel(torch.nn.Module):
    def __init__(self,checkpoint=None,training=False):
        super().__init__();base,cfg=backbone(V2/'models/qwen35_2B','cuda');assert cfg.tie_word_embeddings
        self.backbone=PeftModel.from_pretrained(base,str(checkpoint/'adapter'),is_trainable=training) if checkpoint else get_peft_model(base,LoraConfig(r=8,lora_alpha=16,lora_dropout=.05,target_modules=TARGETS))
        if training:self.backbone.enable_input_require_grads();self.backbone.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        self.tokenizer=AutoTokenizer.from_pretrained(V2/'models/qwen35_2B',local_files_only=True);self.tokenizer.padding_side='right'
    def loss(self,input_ids,attention_mask,labels):
        with torch.autocast('cuda',dtype=torch.bfloat16):hidden=self.backbone(input_ids=input_ids,attention_mask=attention_mask,use_cache=False).last_hidden_state
        embedding=self.backbone.get_input_embeddings().weight;loss=0.
        # Checkpoint the large-vocabulary projection: keep only target states,
        # recompute 64-token projections during backward rather than retaining
        # all sequence-by-vocabulary logits in 8 GiB VRAM.
        return assistant_loss(hidden,labels,embedding,training=self.training)
    def save(self,path):path.mkdir(parents=True,exist_ok=True);self.backbone.save_pretrained(path/'adapter')

def collate_chat(rows,tokenizer):
    n=(max(len(r['input_ids']) for r in rows)+7)//8*8;pad=tokenizer.pad_token_id
    return {'input_ids':torch.tensor([r['input_ids']+[pad]*(n-len(r['input_ids'])) for r in rows],device='cuda'),
        'attention_mask':torch.tensor([[1]*len(r['input_ids'])+[0]*(n-len(r['input_ids'])) for r in rows],device='cuda'),
        'labels':torch.tensor([r['labels']+[-100]*(n-len(r['labels'])) for r in rows],device='cuda')}

def generate_text(backbone,tokenizer,messages,device='cuda',max_new_tokens=128,timeout_seconds=20,max_context_tokens=768,max_sentences=None):
    messages=[dict(m) for m in messages]
    while True:
        ids=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_tensors='pt',return_dict=False)
        if ids.shape[1]<=max_context_tokens:break
        if not trim_old_context(messages):
            return {'status':'input_too_long','reply':'这段内容有点长，请先告诉我最希望讨论的部分。','tokens':0,'action_authority':False}
    context_tokens=int(ids.shape[1]);history_messages_used=max(0,len(messages)-2)
    ids=ids.to(device);tokens=[];past=None;start=time.monotonic();stop={tokenizer.eos_token_id,tokenizer.convert_tokens_to_ids('<|im_end|>')};reason='max_tokens'
    with torch.inference_mode(),torch.autocast(device,dtype=torch.bfloat16,enabled=getattr(backbone,'autocast_enabled',True)):
        for _ in range(max_new_tokens):
            out=backbone(input_ids=ids,past_key_values=past,use_cache=True);past=out.past_key_values;embedding=backbone.get_input_embeddings().weight;scores=torch.nn.functional.linear(out.last_hidden_state[:,-1].to(embedding.dtype),embedding);token=int(scores.argmax(-1).item())
            if token in stop:reason='end_token';break
            tokens.append(token);ids=torch.tensor([[token]],device=device)
            if max_sentences:
                current=tokenizer.decode(tokens,skip_special_tokens=True)
                balanced=current.count('“')==current.count('”') and current.count('「')==current.count('」') and current.count('"')%2==0
                if balanced and len(re.findall(r'[。！？!?]',current))>=max_sentences:
                    reason='sentence_limit';break
            if time.monotonic()-start>=timeout_seconds:reason='time_limit';break
    reply=tokenizer.decode(tokens,skip_special_tokens=True).strip()
    if max_sentences and reason in {'time_limit','max_tokens'}:
        ends=list(re.finditer(r'[。！？!?][”」"]?',reply))
        if ends:reply=reply[:ends[-1].end()]
    return {'status':'local_dialogue','reply':reply,'tokens':len(tokens),'elapsed_seconds':time.monotonic()-start,'stop_reason':reason,'action_authority':False,
            'context_tokens':context_tokens,'history_messages_used':history_messages_used}
