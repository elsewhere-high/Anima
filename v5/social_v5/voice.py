"""Bounded local speech recognition and optional online neural speech output."""
import asyncio
import base64
import binascii
import io
import threading
import time
import wave
import re
import os

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from . import ROOT

VOICES = {
    'zh-CN-XiaoxiaoNeural': '晓晓 · 温柔女声',
    'zh-CN-XiaoyiNeural': '晓伊 · 明亮女声',
    'zh-CN-YunxiNeural': '云希 · 亲切男声',
}
_model = None
_lock = threading.Lock()
_tts_slots = asyncio.Semaphore(2)

def recognition_language():
    language=os.getenv('SOCIAL_ASR_LANGUAGE','auto')
    if language not in {'auto','zh','yue'}:raise ValueError('SOCIAL_ASR_LANGUAGE 只支持 auto、zh 或 yue')
    return language


class SpeechInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    audio_base64: str = Field(min_length=44, max_length=1100000)
    session_id: str = Field(default='default',min_length=1,max_length=80,pattern=r'^[\w.-]+$')


class SpeechOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=1200)
    voice: str = 'zh-CN-XiaoxiaoNeural'
    rate: int = Field(default=-5, ge=-25, le=25)

class ActivityInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    pcm_base64:str=Field(min_length=4,max_length=43000)
    session_id:str=Field(min_length=1,max_length=80,pattern=r'^[\w.-]+$')
    stream_id:str=Field(min_length=8,max_length=80,pattern=r'^[\w.-]+$')
    sequence:int=Field(ge=0,le=100000000)
    reset:bool=False


def decode_wav(encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
                raise ValueError('需要 16kHz 单声道 PCM WAV 音频')
            count = wav.getnframes()
            if not 3200 <= count <= 400000:
                raise ValueError('每段语音应为 0.2–25 秒')
            pcm = wav.readframes(count)
            if len(pcm) != count * 2:
                raise ValueError('音频不完整，请重新说一次')
        return np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
    except (binascii.Error, wave.Error, EOFError) as exc:
        raise ValueError('音频格式无效，请重新说一次') from exc


def transcribe(encoded):
    global _model
    samples = decode_wav(encoded)
    from .audio_features import extract_audio_features
    from .profiles import select_profile
    backend=select_profile().audio_backend
    signal=extract_audio_features(samples)
    if float(np.sqrt(np.mean(samples ** 2))) < .00001:
        return {'text': '', 'status': 'silence', 'audio_stored': False,'voice':signal}
    from .speech_activity import inspect_audio
    quality=inspect_audio(samples)
    if quality['requires_repeat']:
        return {'text':'','status':'repeat_required','audio_stored':False,'voice':signal,'quality':quality}
    # Bounded gain after neural speech detection; gain is not denoising or dereverberation.
    gain=min(8.0,.06/max(quality['rms'],1e-8),.95/max(float(np.max(np.abs(samples))),1e-8))
    samples=samples*max(1.0,gain) if gain>=1 else samples
    if not _lock.acquire(blocking=False):
        raise HTTPException(429, '正在识别上一段语音，请稍候')
    try:
        started = time.monotonic()
        if _model is None:
            if backend=='sensevoice':
                import sherpa_onnx
                from .assets import checked_asset
                _model=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(checked_asset('sensevoice/model.int8.onnx')),tokens=str(checked_asset('sensevoice/tokens.txt')),num_threads=select_profile().threads,language=recognition_language(),use_itn=True)
            else:
                from faster_whisper import WhisperModel
                _model = WhisperModel(str(ROOT / 'models/whisper-base'), device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
        emotion=language=None;events=[]
        if backend=='sensevoice':
            stream=_model.create_stream();stream.accept_waveform(16000,samples);_model.decode_stream(stream)
            result=stream.result;text=result.text.strip()
            emotion=re.sub(r'[<>|]','',result.emotion) or None
            language=re.sub(r'[<>|]','',result.lang) or None
            events=[{'Cry':'Crying','BGM':'BackgroundMusic'}.get(x,x) for x in re.findall(r'<\|([^|]+)\|>',result.event) if not x.startswith('/')]
        else:
            segments, _ = _model.transcribe(samples, language='zh', beam_size=3, vad_filter=True,
                condition_on_previous_text=False, initial_prompt='以下是普通话日常对话，请用简体中文转写。')
            text = ''.join(s.text for s in segments if s.no_speech_prob < .7).strip()
        signal=extract_audio_features(samples,text)
        signal.update(source=backend+'_int8_and_dsp',emotion_label=emotion,language=language,audio_events=events)
        # sherpa exposes categorical tokens, not calibrated emotion probabilities.
        return {'text': text, 'status': 'ok' if text or events else 'silence', 'voice':signal,
            'latency_ms': round((time.monotonic()-started)*1000), 'audio_stored': False,'backend':backend,'quality':quality}
    finally:
        _lock.release()


def router(guard):
    api = APIRouter(prefix='/v1/voice', dependencies=[Depends(guard)])

    @api.post('/activity')
    def detect_activity(body:ActivityInput,request:Request,x_member_session:str=Header(default='')):
        from .speech_activity import activity
        if x_member_session:
            request.app.state.sessions.resolve(x_member_session)
            owner=x_member_session
        else:owner='guest:'+request.state.guest_id
        try:
            raw=base64.b64decode(body.pcm_base64,validate=True)
            if len(raw)%2 or not 2<=len(raw)<=32000:raise ValueError('需要16kHz单声道PCM16，且每块不超过一秒')
            return activity.stream((owner,body.session_id,body.stream_id),body.sequence,np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768,body.reset)
        except (ValueError,binascii.Error) as exc:raise HTTPException(400,str(exc)) from exc

    @api.get('/options')
    def options():
        from .profiles import select_profile
        backend=select_profile().audio_backend
        return {'voices': [{'id': key, 'name': name} for key, name in VOICES.items()],
            'recognition': 'local_'+backend+'_int8', 'recognition_ready': (ROOT/('models/sensevoice/model.int8.onnx' if backend=='sensevoice' else 'models/whisper-base/model.bin')).is_file(),
            'synthesis': 'online_microsoft_edge', 'audio_stored': False,'speech_activity':'silero_vad','activity_ready':(ROOT/'models/vad/silero_vad.onnx').is_file(),'recognition_language':recognition_language() if backend=='sensevoice' else 'zh','turn_pause_seconds':2.0,'barge_in':'browser_aec_and_vad_requires_device_validation'}

    @api.post('/transcribe')
    def recognize(body: SpeechInput,request:Request,x_member_session:str=Header(default='')):
        try:
            social=getattr(request.app.state,'social',None)
            if social:
                uid=request.app.state.sessions.resolve(x_member_session) if x_member_session else None
                owner=x_member_session or 'guest:'+request.state.guest_id
                return social.audio(body.audio_base64,owner,body.session_id,uid)
            return transcribe(body.audio_base64)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post('/speak')
    async def speak(body: SpeechOutput):
        if body.voice not in VOICES:
            raise HTTPException(400, '请选择列表中的声音')
        import edge_tts
        async def render():
            chunks = []
            async with _tts_slots:
                async for chunk in edge_tts.Communicate(body.text, body.voice, rate=f'{body.rate:+d}%').stream():
                    if chunk['type'] == 'audio':
                        chunks.append(chunk['data'])
            return b''.join(chunks)
        try:
            audio = await asyncio.wait_for(render(), timeout=25)
            if not audio:
                raise RuntimeError('empty audio')
            return Response(audio, media_type='audio/mpeg', headers={'Cache-Control': 'no-store'})
        except Exception as exc:
            raise HTTPException(503, '自然语音暂时不可用，可切换到设备声音或稍后重试') from exc

    return api
