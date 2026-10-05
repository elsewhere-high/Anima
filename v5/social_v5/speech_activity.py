"""Local Silero speech detection. Scores are speech activity, never ASR accuracy.

Streaming state is isolated by authenticated/guest owner and stream ID. No PCM
is persisted; bounded sessions expire. Missing model fails explicitly.
"""
import hashlib
import threading
import time
from pathlib import Path
import numpy as np
from . import ROOT

MODEL=ROOT/'models/vad/silero_vad.onnx'
MODEL_SHA256='1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3'

class SpeechActivity:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.lock=threading.RLock();self.session=None;self.streams={}

    def _load(self):
        if self.session is not None:return
        if not MODEL.is_file():raise ValueError('语音检测模型尚未就绪，请先运行 download_speech_assets.py')
        if hashlib.sha256(MODEL.read_bytes()).hexdigest()!=MODEL_SHA256:raise ValueError('语音检测模型校验失败，请恢复已验证的模型文件')
        import onnxruntime as ort
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(MODEL),sess_options=options,providers=['CPUExecutionProvider'])

    @staticmethod
    def fresh():return {'state':np.zeros((2,1,128),np.float32),'context':np.zeros((1,64),np.float32),'tail':np.empty(0,np.float32),'seq':-1,'time':0}

    def _infer(self,audio,state,final=False):
        values=np.concatenate((state['tail'],np.asarray(audio,np.float32)))
        end=len(values)//512*512
        state['tail']=values[end:].copy()
        if final and end<len(values):values=np.pad(values,(0,512-(len(values)-end)));end=len(values);state['tail']=np.empty(0,np.float32)
        scores=[]
        for offset in range(0,end,512):
            x=np.concatenate((state['context'],values[offset:offset+512][None]),axis=1)
            output,newstate=self.session.run(None,{'input':x,'state':state['state'],'sr':np.array(16000,dtype=np.int64)})
            state['state']=newstate;state['context']=x[:,-64:].copy();scores.append(float(output.ravel()[0]))
        return scores

    def analyze(self,audio):
        with self.lock:
            self._load();return self._infer(audio,self.fresh(),True)

    def stream(self,key,seq,audio,reset=False):
        if not 1<=len(audio)<=16000:raise ValueError('语音活动分块应在一秒以内')
        with self.lock:
            self._load();now=self.clock()
            self.streams={k:v for k,v in self.streams.items() if now-v['time']<30}
            state=self.streams.get(key)
            if reset or state is None:
                if key not in self.streams and len(self.streams)>=64:raise ValueError('语音检测会话已满，请稍后重试')
                state=self.fresh();self.streams[key]=state
            if seq<=state['seq']:raise ValueError('语音分块重复或顺序错误')
            if state['seq']>=0 and seq!=state['seq']+1:state=self.fresh();self.streams[key]=state
            state.update(seq=seq,time=now)
            scores=self._infer(audio,state)
            return {'sequence':seq,'probabilities':scores,'frame_ms':32,'speech_probability':max(scores,default=0),'source':'silero_vad','calibrated_asr_confidence':None,'audio_stored':False}

activity=SpeechActivity()

def inspect_audio(samples):
    probabilities=activity.analyze(samples)
    fraction=sum(p>=.5 for p in probabilities)/max(1,len(probabilities))
    voiced_seconds=sum(p>=.5 for p in probabilities)*.032
    rms=float(np.sqrt(np.mean(np.square(samples))))
    clipping=float(np.mean(np.abs(samples)>=.995))
    reasons=[]
    if voiced_seconds<.128:reasons.append('insufficient_speech')
    if clipping>.08:reasons.append('heavy_clipping')
    return {'speech_fraction':round(fraction,4),'voiced_seconds':round(voiced_seconds,3),'rms':rms,'clipping_fraction':clipping,'requires_repeat':bool(reasons),'reasons':reasons,'asr_confidence':None,'scope':'signal_quality_not_transcription_confidence'}
