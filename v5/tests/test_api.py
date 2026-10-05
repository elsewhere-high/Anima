import pytest
from fastapi.testclient import TestClient
from social_v5.server import app,Sessions
from social_v5.memory import MemoryStore
from social_v5.engine import SocialEngine

class FakePredictor:
    backend='test_fake'
    def __init__(self):self.calls=[]
    def state(self,history,speech):
        return {k:{'label':v,'confidence':.99,'distribution':{v:1.}} for k,v in {'emotion':'neutral','dialog_act':'statement-non-opinion','intent':'general_quirky','boundary':'unspecified','policy':'RESPOND','task_domain':'酒店'}.items()}
    def generate_dialogue(self,history,speech,memories,policy):
        self.calls.append((history,memories,policy));return {'reply':'你好，我在听。','status':'fake','action_authority':False}

class FakeVision:
    def __init__(self):
        import threading
        self.lock=threading.RLock();self.streams={};self.frames={}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.delenv('SOCIAL_API_TOKEN',raising=False)
    app.state.memory=MemoryStore(tmp_path/'m.db',tmp_path/'key');app.state.sessions=Sessions();app.state.vision=FakeVision();app.state.engine=SocialEngine(FakePredictor(),app.state.memory)
    c=TestClient(app);yield c;app.state.memory.db.close()

def register(c,uid='a',consent=True):
    r=c.post('/v1/members',json={'user_id':uid,'display_name':uid,'pin':'securepin','memory_consent':consent})
    assert r.status_code==200,r.text
    return {'X-Member-Session':r.json()['session_token']}

def test_cannot_spoof_user_or_consent(client):
    register(client)
    r=client.post('/v1/step',json={'observation':{'user_id':'a','identity_verified':True,'memory_consent':True,'speech':'我叫小林'}})
    assert r.status_code==200 and not r.json()['memory_persisted']
    assert app.state.memory.list('a')==[]

def test_pin_isolation_restart_context_and_revocation(client):
    a=register(client);b=register(client,'b')
    client.post('/v1/step',headers=a,json={'observation':{'speech':'我的眼镜放在卧室抽屉'}})
    r=client.post('/v1/step',headers=a,json={'observation':{'speech':'眼镜在哪里？','session_id':'another'}}).json()
    assert any('抽屉' in x for x in r['retrieved_memories'])
    assert not client.get('/v1/memory',headers=b).json()
    assert client.get('/v1/memory').status_code==401
    client.put('/v1/memory/consent',headers=a,json={'memory_consent':False})
    assert client.get('/v1/memory',headers=a).json()==[]
    assert client.post('/v1/memory',headers=a,json={'slot':'物品','text':'钥匙在门口'}).status_code==403
    client.post('/v1/logout',headers=a)
    assert client.get('/v1/memory',headers=a).status_code==401

def test_invalid_input_and_cross_site(client):
    assert client.post('/v1/step',json={'observation':{'invented':'x'}}).status_code==422
    assert client.post('/v1/members',json={'user_id':'x','display_name':'甲','pin':'securepin'},headers={'origin':'https://evil.example'}).status_code==403
    assert client.post('/v1/step',content=b'x'*5700001).status_code==413

def test_rate_limit_and_gateway_key(client,monkeypatch):
    register(client)
    for _ in range(10):assert client.post('/v1/login',json={'user_id':'a','pin':'wrongpin'}).status_code==401
    assert client.post('/v1/login',json={'user_id':'a','pin':'wrongpin'}).status_code==429
    monkeypatch.setenv('SOCIAL_API_TOKEN','gateway-test-key')
    assert client.get('/v1/members').status_code==401
    assert client.get('/v1/members',headers={'Authorization':'Bearer gateway-test-key'}).status_code==200

def test_memory_delete_clears_working_context(client):
    a=register(client)
    client.post('/v1/step',headers=a,json={'observation':{'speech':'我叫小林'}})
    rid=next(r['id'] for r in client.get('/v1/memory',headers=a).json() if r['kind']=='fact')
    assert app.state.engine.sessions
    assert client.delete('/v1/memory/'+rid,headers=a).status_code==200
    assert not app.state.engine.sessions

def test_face_cues_never_override_user_emotion_or_authorize_actions(client):
    from social_v5.schema import Observation
    visual={'faces':[{'identity':{'candidate_user_id':None},'expression':{'status':'expression_hypothesis','label_zh':'开心表情'}}]}
    r=app.state.engine.step(Observation(speech='看看我的表情'),visual)
    assert r['dialogue']['status']=='grounded_face_observation'
    assert '不一定' in r['response']
    assert r['state']['emotion_source']=='text' and not r['task']['authorized']
    r=app.state.engine.step(Observation(speech='看看我的表情'),{'faces':visual['faces']*2})
    assert '多个人' in r['response']

def test_low_asr_boundary_and_secrets(client):
    a=register(client)
    r=client.post('/v1/step',headers=a,json={'observation':{'speech':'我叫小林','asr_confidence':.2}}).json()
    assert not app.state.memory.list('a')
    r=client.post('/v1/step',headers=a,json={'observation':{'speech':'请不要打扰我'}}).json()
    assert r['dialogue']['status']=='controller_template'
    client.post('/v1/step',headers=a,json={'observation':{'speech':'密码是testsecret'}})
    assert not any('testsecret' in str(s['history']) for s in app.state.engine.sessions.values())

def test_natural_language_forget(client):
    a=register(client)
    client.post('/v1/step',headers=a,json={'observation':{'speech':'我的眼镜放在卧室抽屉'}})
    r=client.post('/v1/step',headers=a,json={'observation':{'speech':'请忘记我的眼镜位置'}}).json()
    assert r['dialogue']['status']=='memory_deletion_receipt'
    assert not any('眼镜' in x['text'] for x in client.get('/v1/memory',headers=a).json())
    assert all(not s['history'] for s in app.state.engine.sessions.values())

def test_guest_browsers_do_not_share_default_session(client):
    client.post('/v1/step',json={'observation':{'speech':'我今天去了公园'}})
    stranger=TestClient(app)
    stranger.post('/v1/step',json={'observation':{'speech':'刚才说了什么'}})
    assert app.state.engine.predictor.calls[-1][0]==[]
    client.post('/v1/step',json={'observation':{'speech':'继续刚才的话题'}})
    assert app.state.engine.predictor.calls[-1][0]

def test_forget_receipt_wins_over_wrong_task_class_but_never_moves(client):
    from social_v5.schema import Observation
    original=app.state.engine.predictor.state
    def mistaken(history,speech):
        result=original(history,speech);result['policy']['label']='CANCEL_TASK';return result
    app.state.engine.predictor.state=mistaken
    app.state.memory.put('a','fact','眼镜位置','眼镜在抽屉')
    out=app.state.engine.step(Observation(user_id='a',identity_verified=True,memory_consent=True,speech='请忘记我的眼镜位置'))
    assert out['dialogue']['status']=='memory_deletion_receipt' and '已删除' in out['response']
    assert not out['task']['requested'] and out['motion']['command']=='HOLD'

def test_user_name_is_not_the_assistants_name():
    from social_v5.engine import guard_name_echo
    assert guard_name_echo('我叫小林。你的眼镜在书桌。','我叫小林。',[])=='你好，小林。你的眼镜在书桌。'
    assert guard_name_echo('我是小林。','你好',['[time] 我叫小林'])=='你好，小林。'
    assert guard_name_echo('我是陪伴助手。','我叫小林。',[])=='我是陪伴助手。'

def test_memory_question_is_not_a_new_reminder_request(client):
    from social_v5.schema import Observation
    original=app.state.engine.predictor.state
    def mistaken(history,speech):
        result=original(history,speech);result['policy']['label']='REMIND';return result
    app.state.engine.predictor.state=mistaken
    out=app.state.engine.step(Observation(speech='我每周几去公园散步？'))
    assert out['dialogue']['status']=='fake' and out['action']=='RESPOND'
    assert not out['task']['authorized']
    out=app.state.engine.step(Observation(speech='提醒我周三去公园',reminder_after_seconds=100,reminder_text='去公园'))
    assert out['dialogue']['status']=='controller_template'
