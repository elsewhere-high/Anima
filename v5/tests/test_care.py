import threading,time
import pytest
from fastapi.testclient import TestClient
from social_v5.care import triage,reminder_request,CareService
from social_v5.server import app
from social_v5.robot import RobotGateway
from test_api import client

def login(c,name='care',consent=True):
    r=c.post('/v1/members',json={'user_id':name,'display_name':name,'pin':'testing-pin','memory_consent':consent})
    assert r.status_code==200
    return {'X-Member-Session':r.json()['session_token']}

@pytest.mark.parametrize('text',['我喘不过气了','我胸口痛','妈妈摔倒了起不来','我不想活了','着火了','救命','以前没事，但是现在我胸口痛','我现在胸痛，昨天还没事'])
def test_urgent_current_reports(text):assert triage(text)['priority']=='urgent'

@pytest.mark.parametrize('text',['电影里有人喊救命','如果我摔倒了怎么办','昨天胸口痛，今天没有','我没有胸痛','我没有呼吸困难','我不想活了这句话怎么翻译','我现在想喝茶'])
def test_report_negation_education_is_not_verified_urgent(text):assert triage(text) is None

def test_uncertain_asr_checks_in_without_asserting_emergency():assert triage('救命',.3)['kind']=='clarify_safety'

@pytest.mark.parametrize('text',['这个药能吃几片？','我能把药加量吗','药忘吃了，现在补吃吗'])
def test_medication_changes_do_not_reach_generator(client,text):
    r=client.post('/v1/step',json={'observation':{'speech':text}}).json()
    assert r['care']['kind']=='medication_boundary' and not app.state.engine.predictor.calls

@pytest.mark.parametrize('text,seconds',[('五分钟后提醒我给花浇水',300),('提醒我两小时后喝茶',7200),('请半小时后提醒我读书',1800),('帮我十五分钟后提醒我休息',900)])
def test_relative_reminder_parse(text,seconds):assert reminder_request(text)['delay_seconds']==seconds

def test_ambiguous_reminder_never_guesses():
    assert reminder_request('明天提醒我去医院')['clarify']
    assert reminder_request('不要提醒我了') is None

def test_emergency_does_not_wait_for_model_lock(client):
    entered=threading.Event();release=threading.Event()
    def busy():
        with app.state.engine.lock:entered.set();release.wait(3)
    t=threading.Thread(target=busy);t.start();entered.wait(1)
    try:
        start=time.monotonic();r=client.post('/v1/step',json={'observation':{'speech':'我喘不过气了'}})
        assert time.monotonic()-start<1
        assert r.json()['care']['priority']=='urgent'
        assert not r.json()['care']['human_contact_sent'] and not r.json()['motion']['authorized']
        assert not app.state.engine.predictor.calls
    finally:release.set();t.join()

def test_untrusted_json_cannot_authorize_hardware(client):
    r=client.post('/v1/step',json={'observation':{'speech':'打开客厅灯','emergency_verified':True,'motion_authorized':True,'task_execution_authorized':True,'target_device':'light','confirmed_task_intent':'iot_hue_lighton'}}).json()
    assert not r['motion']['authorized'] and not r['task']['authorized'] and not r['human_request']

def test_reminder_api_idempotency_encryption_isolation(client):
    a=login(client);b=login(client,'care-b')
    body={'text':'给兰花浇水','delay_seconds':30,'request_id':'test-request-0001'}
    r=client.post('/v1/care/reminders',headers=a,json=body);assert r.status_code==200
    item=r.json();assert client.post('/v1/care/reminders',headers=a,json=body).json()['id']==item['id']
    assert client.get('/v1/care/reminders',headers=b).json()==[]
    assert '兰花' not in app.state.memory.db.execute('SELECT text FROM reminders').fetchone()[0]
    assert client.post(f"/v1/care/reminders/{item['id']}/resolve",headers=b,json={'action':'ack','occurrence':item['occurrence']}).status_code==404
    response=client.post(f"/v1/care/reminders/{item['id']}/resolve",headers=a,json={'action':'snooze','occurrence':item['occurrence'],'minutes':10})
    assert response.status_code==200
    assert client.post(f"/v1/care/reminders/{item['id']}/resolve",headers=a,json={'action':'ack','occurrence':item['occurrence']}).status_code==409

def test_restart_overdue_recurrence_and_idempotent_ack(client):
    a=login(client);svc=app.state.engine.care;now=time.time();svc.clock=lambda:now
    item=svc.add('care','按既定计划核对用药',now+1,'repeat-test',86400,'medication')
    restarted=CareService(app.state.memory,lambda:now+3*86400)
    due=restarted.poll('care')['reminders'];assert len(due)==1 and due[0]['overdue_seconds']>0
    result=restarted.resolve('care',item['id'],'ack',item['occurrence']);assert result['item']['due_unix']>now+3*86400
    assert restarted.resolve('care',item['id'],'ack',item['occurrence'])['status']=='stale_occurrence'
    assert not restarted.reminders('care',True)

def test_relative_reminder_is_grounded_and_deduped(client):
    a=login(client)
    body={'observation':{'speech':'五分钟后提醒我给花浇水'}}
    one=client.post('/v1/step',headers=a,json=body).json();two=client.post('/v1/step',headers=a,json=body).json()
    assert one['care']['kind']=='reminder_saved' and one['care']['reminder']['id']==two['care']['reminder']['id']
    assert not app.state.engine.predictor.calls

def test_guest_and_withdrawal(client):
    r=client.post('/v1/step',json={'observation':{'speech':'五分钟后提醒我喝茶'}}).json()
    assert r['care']['kind']=='reminder_needs_consent'
    a=login(client);svc=app.state.engine.care
    svc.settings('care',{'proactive_enabled':True});svc.add('care','浇花',time.time()+1,'delete-test')
    client.put('/v1/memory/consent',headers=a,json={'memory_consent':False})
    assert client.get('/v1/care/reminders',headers=a).json()==[]
    assert not client.get('/v1/care/settings',headers=a).json()['proactive_enabled']
    assert client.post('/v1/care/reminders',headers=a,json={'text':'浇花','delay_seconds':1,'request_id':'no-consent'}).status_code==400

def test_proactive_requires_opt_in_presence_idle_and_obeys_quiet(client):
    login(client);svc=app.state.engine.care
    now=1770004800.;svc.clock=lambda:now
    assert svc.poll('care',True)['reason']=='not_enabled'
    svc.settings('care',{'proactive_enabled':True,'interval_minutes':30,'quiet_start':0,'quiet_end':0,'utc_offset_minutes':480})
    now+=1801
    assert svc.poll('care',False)['reason']=='no_confirmed_presence'
    assert svc.poll('care',True,True)['reason']=='busy'
    assert svc.poll('care',True)['check_in']
    assert not svc.poll('care',True)['check_in']
    svc.note_speech('care','请不要打扰我');now+=3600
    assert svc.poll('care',True)['reason']=='user_requested_quiet'
    restarted=CareService(app.state.memory,lambda:now+3600)
    assert restarted.poll('care',True)['reason']=='user_requested_quiet'
    svc.note_speech('care','现在可以聊天了');now+=1801
    assert svc.poll('care',True)['check_in']

def test_quiet_hours_overnight(client):
    login(client);svc=app.state.engine.care
    from datetime import datetime,timezone
    now=datetime(2026,10,1,15,tzinfo=timezone.utc).timestamp();svc.clock=lambda:now
    svc.settings('care',{'proactive_enabled':True});now+=60
    assert svc.poll('care',True)['reason']=='quiet_hours'

def test_robot_watchdog_and_separate_auth(client,monkeypatch):
    assert client.post('/v1/robot/heartbeat',json={'robot_id':'r'}).status_code==503
    monkeypatch.setenv('SOCIAL_ROBOT_TOKEN','r'*32)
    assert client.post('/v1/robot/heartbeat',json={'robot_id':'r'}).status_code==401
    headers={'X-Robot-Token':'r'*32}
    assert client.post('/v1/robot/heartbeat',headers=headers,json={'robot_id':'r','emergency_stop':False,'speaker_ready':True}).status_code==200
    r=client.post('/v1/robot/turn?robot_id=r',headers=headers,json={'observation':{'speech':'你好'}})
    assert r.status_code==200 and r.json()['output']['motion']['command']=='HOLD'
    now=1.;robot=RobotGateway(lambda:now);robot.heartbeat({'robot_id':'r','emergency_stop':False,'speaker_ready':True,'display_ready':True,'battery_percent':80})
    assert robot.envelope('r',{'response':'你好'})['outputs']['speak']=='你好'
    now=8.;out=robot.envelope('r',{'response':'你好'});assert out['outputs']['speak']=='' and out['robot']['hold_required']
