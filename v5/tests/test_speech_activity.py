import base64
import numpy as np
import pytest
from social_v5.speech_activity import SpeechActivity,MODEL,inspect_audio

@pytest.mark.skipif(not MODEL.is_file(),reason='download pinned VAD first')
def test_real_silence_and_random_noise_not_speech():
    assert inspect_audio(np.zeros(16000,np.float32))['requires_repeat']
    result=inspect_audio(np.random.default_rng(123).normal(0,.01,16000).astype(np.float32))
    assert result['requires_repeat']
    assert result['asr_confidence'] is None

@pytest.mark.skipif(not MODEL.is_file(),reason='download pinned VAD first')
def test_stream_isolation_replay_and_expiry():
    now=[0];engine=SpeechActivity(clock=lambda:now[0]);audio=np.zeros(4096,np.float32)
    engine.stream(('alice','room','one'),0,audio)
    engine.stream(('bob','room','one'),0,audio)
    assert len(engine.streams)==2
    with pytest.raises(ValueError,match='顺序'):engine.stream(('alice','room','one'),0,audio)
    engine.stream(('alice','room','one'),2,audio) # gap resets state
    assert engine.streams[('bob','room','one')]['seq']==0
    now[0]=31;engine.stream(('alice','room','two'),0,audio)
    assert len(engine.streams)==1

def test_activity_http_format_and_origin(monkeypatch):
    from fastapi.testclient import TestClient
    from social_v5.server import app
    monkeypatch.delenv('SOCIAL_API_TOKEN',raising=False);client=TestClient(app)
    payload={'pcm_base64':base64.b64encode(bytes(8192)).decode(),'session_id':'test','stream_id':'test-stream','sequence':0}
    assert client.post('/v1/voice/activity',json=payload,headers={'origin':'https://other.example'}).status_code==403
    assert client.post('/v1/voice/activity',json={**payload,'pcm_base64':'!!!!'}).status_code==400
    assert client.post('/v1/voice/activity',json={**payload,'pcm_base64':'AQID'}).status_code==400
    if MODEL.is_file():
        first=client.post('/v1/voice/activity',json=payload)
        assert first.status_code==200
        assert first.json()['audio_stored'] is False
        assert client.post('/v1/voice/activity',json=payload).status_code==400
        assert TestClient(app).post('/v1/voice/activity',json=payload).status_code==200

def test_whole_audio_rejection_does_not_invoke_asr(monkeypatch):
    import social_v5.voice as voice
    from social_v5 import speech_activity
    from test_voice import wav
    monkeypatch.setattr(voice,'decode_wav',lambda _:np.ones(16000,np.float32)*.1)
    monkeypatch.setattr(voice,'_model',None)
    monkeypatch.setattr(speech_activity,'inspect_audio',lambda _:dict(requires_repeat=True,reasons=['insufficient_speech']))
    assert voice.transcribe(wav())['status']=='repeat_required'
    assert voice._model is None

def test_language_is_explicit_and_validated(monkeypatch):
    from social_v5.voice import recognition_language
    monkeypatch.delenv('SOCIAL_ASR_LANGUAGE',raising=False)
    assert recognition_language()=='auto'
    for language in ['zh','yue']:
        monkeypatch.setenv('SOCIAL_ASR_LANGUAGE',language);assert recognition_language()==language
    monkeypatch.setenv('SOCIAL_ASR_LANGUAGE','invented')
    with pytest.raises(ValueError):recognition_language()
