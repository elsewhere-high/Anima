import hashlib,json,threading
import torch
from transformers import AutoModel,AutoTokenizer
from . import ROOT

class Embedding:
    def __init__(self):
        folder=ROOT/'models/bge-small-zh-v1.5'
        for r in json.loads((folder/'manifest.json').read_text())['files']:
            if hashlib.sha256((folder/r['file']).read_bytes()).hexdigest()!=r['sha256']:raise RuntimeError('Embedding model hash mismatch')
        self.lock=threading.RLock()
        self.tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True)
        self.model=AutoModel.from_pretrained(folder,local_files_only=True,use_safetensors=True).cpu().eval()
    def encode(self,text,query=False):
        if query:text='为这个句子生成表示以用于检索相关文章：'+text
        with self.lock,torch.inference_mode():
            inputs=self.tokenizer([text],padding=True,truncation=True,max_length=256,return_tensors='pt')
            vector=self.model(**inputs).last_hidden_state[:,0]
            return torch.nn.functional.normalize(vector,p=2,dim=1)[0].tolist()
