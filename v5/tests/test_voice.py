import base64
import io
import wave

import pytest
from social_v5.voice import decode_wav, transcribe


def wav(duration=1, rate=16000, channels=1):
    out=io.BytesIO()
    with wave.open(out,'wb') as f:
        f.setnchannels(channels);f.setsampwidth(2);f.setframerate(rate)
        f.writeframes(bytes(int(duration*rate)*2*channels))
    return base64.b64encode(out.getvalue()).decode()


def test_audio_limits_and_format():
    assert decode_wav(wav()).shape==(16000,)
    for audio in ['not base64',wav(.1),wav(26),wav(rate=48000),wav(channels=2)]:
        with pytest.raises(ValueError):decode_wav(audio)


def test_silence_does_not_hallucinate_or_load_model(monkeypatch):
    import social_v5.voice as voice
    monkeypatch.setattr(voice,'_model',None)
    assert transcribe(wav())['status']=='silence'
    assert voice._model is None


def test_voice_routes_validate_without_external_calls(monkeypatch):
    from fastapi.testclient import TestClient
    from social_v5.server import app
    monkeypatch.delenv('SOCIAL_API_TOKEN',raising=False)
    client=TestClient(app)
    assert client.post('/v1/voice/speak',json={'text':'你好','voice':'invented'}).status_code==400
    assert client.post('/v1/voice/speak',json={'text':'你好','rate':999}).status_code==422
    assert client.post('/v1/voice/transcribe',json={'audio_base64':wav()}).json()['status']=='silence'
    assert client.post('/v1/voice/transcribe',json={'audio_base64':wav()},headers={'origin':'https://example.com'}).status_code==403
    monkeypatch.setenv('SOCIAL_API_TOKEN','voice-test')
    assert client.get('/v1/voice/options').status_code==401
