import pytest
import torch
from fastapi.testclient import TestClient
from social_v4.runtime_model import SharedModel
from social_v4.server import app


def test_adapter_restored_after_success_and_exception():
    class Fake:
        active='default'
        def set_adapter(self,name):self.active=name
    model=SharedModel.__new__(SharedModel);torch.nn.Module.__init__(model);model.backbone=Fake()
    with model.route('current_state'):assert model.backbone.active=='current_state'
    assert model.backbone.active=='default'
    with pytest.raises(RuntimeError):
        with model.route('dialogue'):
            assert model.backbone.active=='dialogue'
            raise RuntimeError('generation failure')
    assert model.backbone.active=='default'


def test_api_authorization_precedes_model_calls(monkeypatch):
    monkeypatch.setenv('SOCIAL_API_TOKEN','test-only-key')
    client=TestClient(app)
    assert client.post('/v1/step',json={'observation':{'speech':'你好'}}).status_code==401
    assert client.post('/v1/step',json={'observation':{'speech':'你好'}},headers={'Authorization':'Bearer wrong'}).status_code==401
    # Authenticated input is still strictly validated; no model is loaded here.
    response=client.post('/v1/step',json={'observation':{'speech':'你好','invented_emotion':'happy'}},headers={'Authorization':'Bearer test-only-key'})
    assert response.status_code==422
    assert client.post('/v1/imagine',json={},headers={'Authorization':'Bearer test-only-key'}).status_code==404


def test_unaccepted_sentiment_keeps_the_evaluated_original_route():
    import threading
    from social_v4.predictor import Predictor
    from social_world_zh.spec import HEADS
    class Encoded(dict):
        def to(self,*args):return self
    class Model:
        tokenizer=lambda self,*args,**kw:Encoded()
        def original_logits(self,**kwargs):
            result={k:torch.zeros(1,len(v)) for k,v in HEADS.items()}
            result['emotion'][0,0]=30.  # Original emotion: neutral.
            return result
        def state_logits(self,**kwargs):
            emotion=torch.zeros(1,13);emotion[0,7]=30.  # New emotion: happy.
            return {'emotion':emotion}
    p=Predictor.__new__(Predictor);p.device='cpu';p.lock=threading.RLock();p.model=Model();p.temperature={k:1. for k in HEADS};p.accepted_heads=['emotion'];p.state_temperature={'emotion':1.}
    result=p.state([],'测试')
    assert result['emotion']['label']=='happy'
    assert result['sentiment']['label']=='neutral'
    assert result['sentiment']['source']=='v2_retained_derived_sentiment'
