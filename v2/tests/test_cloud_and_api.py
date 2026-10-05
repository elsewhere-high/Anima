import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx,pytest
from social_world_zh.cloud import CloudReasoner
from social_world_zh.schema import Observation

def test_cloud_sends_only_current_speech(monkeypatch):
    monkeypatch.setenv('SOCIAL_CLOUD_URL','https://example.invalid/chat');monkeypatch.setenv('SOCIAL_CLOUD_PROTOCOL','chat_completions');monkeypatch.setenv('SOCIAL_CLOUD_MODEL','test')
    captured={}
    def post(url,**kw):
        captured.update(kw);return httpx.Response(200,json={'choices':[{'message':{'content':'可以先问问对方是否方便聊天。'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',post)
    o=Observation(user_id='private_identity',speech='朋友不想说话怎么办',memory_note='私人历史',cloud_consent=True).model_dump()
    assert CloudReasoner().reason(o,{})['status']=='ok'
    assert captured['json']['messages'][-1]['content']==o['speech']
    assert 'private_identity' not in str(captured) and '私人历史' not in str(captured)
def test_no_cloud_consent_means_no_request(monkeypatch):
    monkeypatch.setenv('SOCIAL_CLOUD_URL','https://example.invalid/chat')
    def forbidden(*a,**kw):raise AssertionError('unexpected external request')
    monkeypatch.setattr(httpx,'post',forbidden)
    assert CloudReasoner().reason(Observation().model_dump(),{})['status']=='consent_required'
def test_cloud_timeout_returns_honest_status(monkeypatch):
    monkeypatch.setenv('SOCIAL_CLOUD_URL','https://example.invalid/chat')
    def fail(*a,**kw):raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(httpx,'post',fail)
    assert CloudReasoner().reason(Observation(cloud_consent=True).model_dump(),{})['status']=='unavailable'
