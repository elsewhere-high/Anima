"""Optional, offline SenseVoice transcription using the published checkpoint."""
from pathlib import Path
import base64
import io
import re
import os

class LocalAsrModel:
    def __init__(self,fast=True):
        from funasr import AutoModel
        root=Path(__file__).resolve().parent/'models/sensevoice'
        self.model=AutoModel(model=str(root),device='cpu',ncpu=max(1,min(8,int(os.environ.get('ANIMA_TORCH_THREADS','3')))),disable_update=True,disable_pbar=True,
                             trust_remote_code=False,ignore_init_mismatch=False)
        import torch
        state=torch.load(root/'model.pt',map_location='cpu',weights_only=True,mmap=True)
        missing=[k for k,v in self.model.model.state_dict().items() if k not in state or state[k].shape!=v.shape]
        if missing:raise ValueError('incomplete_asr_checkpoint')
        if fast:
            from depthwise_cpu import install
            install(self.model.model)

    def infer(self,request):
        import soundfile as sf
        import numpy as np
        audio,rate=sf.read(io.BytesIO(base64.b64decode(request['audio'],validate=True)),dtype='float32')
        if rate!=16000 or audio.ndim!=1 or not 0<len(audio)<=16*16000:
            raise ValueError('invalid_asr_audio')
        if np.sqrt(np.mean(audio*audio))<.001:return {'transcript':'','model':'SenseVoiceSmall','quality':'quiet'}
        result=self.model.generate(input=audio,cache={},language='auto',use_itn=True,batch_size_s=16)
        raw=result[0].get('text','') if result else ''
        # Emotion/event tokens are not transcribed words and are deliberately
        # excluded here. They do not become social judgments automatically.
        return {'transcript':re.sub(r'<\|[^|]*\|>','',raw).strip(),'model':'SenseVoiceSmall','quality':'ok'}
