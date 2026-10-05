import sys,time,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from social_world_zh.schema import Observation,ImagineRequest
from social_world_zh.memory import MemoryStore
from social_world_zh.engine import SocialEngine
from social_world_zh.policy import explicit_boundary
from social_world_zh.adapter import command_from_decision,Simulator

class FakePredictor:
    def state(self,history,speech):
        self.history=history
        return {k:{'label':label,'confidence':.99,'distribution':{label:1.}} for k,label in {'policy':'APPROACH','boundary':'unspecified','intent':'iot_hue_lighton','emotion':'neutral','dialog_act':'statement-non-opinion','task_domain':'酒店'}.items()}
@pytest.fixture
def engine(tmp_path):
    m=MemoryStore(tmp_path/'memory.sqlite');e=SocialEngine(FakePredictor(),m);yield e;m.db.close()
def step(e,**kw):return e.step(Observation(**kw))

def test_boundary_survives_turn_and_restart(engine):
    kw=dict(user_id='alice',identity_verified=True,memory_consent=True)
    assert step(engine,speech='请先别打扰我',**kw)['action']=='SILENCE'
    engine.sessions.clear()
    assert step(engine,speech='嗯',**kw)['action']=='SILENCE'
    assert step(engine,speech='现在可以聊天了',**kw)['boundary_state']=='open'
def test_two_users_and_sessions_are_isolated(engine):
    step(engine,user_id='a',speech='别打扰我')
    assert step(engine,user_id='b',speech='你好')['boundary_state']=='open'
    assert step(engine,user_id='a',speech='嗯')['action']=='SILENCE'
    assert step(engine,user_id='a',session_id='other',speech='你好')['boundary_state']=='open'
def test_no_consent_never_persists(engine):
    step(engine,user_id='a',identity_verified=True,memory_consent=False,speech='别打扰我',memory_note='私人信息')
    assert engine.memory.read('a')['interaction_count']==0
def test_forget_erases_disk_and_session(engine):
    step(engine,user_id='a',identity_verified=True,memory_consent=True,speech='别打扰我')
    engine.forget('a')
    assert step(engine,user_id='a',speech='你好')['boundary_state']=='open'
def test_context_is_previous_turns(engine):
    step(engine,speech='我今天回家很晚')
    r=step(engine,speech='刚才我说什么了')
    assert r['history_turns_used']==2
    assert engine.predictor.history[0]==('用户','我今天回家很晚')
def test_uncertain_asr_no_motion(engine):
    r=step(engine,speech='过来',asr_confidence=.3,motion_authorized=True)
    assert r['action']=='CLARIFY' and not r['motion']['authorized']
def test_motion_authorization_and_collision_gate(engine):
    assert command_from_decision(step(engine,speech='过来'))['kind']=='hold'
    cmd=command_from_decision(step(engine,speech='过来',motion_authorized=True));sim=Simulator()
    assert sim.submit(cmd)['status']=='collision_check_required'
    assert sim.submit(cmd,collision_free=True)['status']=='acknowledged'
    assert sim.submit(cmd,collision_free=True)['status']=='duplicate'
def test_device_requires_target_and_intent_confirmation(engine):
    assert not step(engine,speech='打开客厅灯',task_execution_authorized=True)['task']['authorized']
    r=step(engine,speech='打开客厅灯',task_execution_authorized=True,target_device='living_light',confirmed_task_intent='iot_hue_lighton')
    cmd=command_from_decision(r);sim=Simulator()
    assert sim.submit(cmd)['status']=='acknowledged'
    assert sim.devices['living_light']=='turn_on'
def test_expired_command(engine):
    cmd=command_from_decision(step(engine,speech='过来',motion_authorized=True));cmd['issued_at_unix']-=10
    assert Simulator().submit(cmd,collision_free=True)['status']=='expired'
def test_emergency_remains_assistance_request(engine):
    r=step(engine,speech='别打扰我',emergency_verified=True)
    assert r['action']=='CALL_HUMAN' and not r['motion']['authorized']
@pytest.mark.parametrize('text',['他说别打扰我','我不是让你保持安静','电影里有人说不要靠近','昨天不想聊天','“别出声”是什么意思'])
def test_quotes_and_negation_do_not_set_explicit_boundary(text):assert explicit_boundary(text) is None
def test_memory_delete_includes_reminders(engine):
    engine.memory.remind('a',1,'喝水');engine.memory.forget('a')
    assert engine.memory.db.execute('SELECT count(*) FROM reminders').fetchone()[0]==0
def test_nonfinite_input_rejected():
    with pytest.raises(ValueError):Observation(distance=float('nan'))
    with pytest.raises(ValueError):ImagineRequest(speech='你好',candidates=['']*7)

def test_reopen_conversation_does_not_cancel_distance(engine):
    step(engine,speech='别打扰我，也别靠近我')
    r=step(engine,speech='现在可以聊天了')
    assert r['boundary_state']=='keep_distance'
    assert not r['explicit_boundary_flags']['do_not_disturb']
    assert r['explicit_boundary_flags']['keep_distance']
    assert step(engine,speech='你好',boundary='open')['boundary_state']=='open'
@pytest.mark.parametrize('text',['妈妈说别打扰我','我爷爷不想聊天','我朋友需要独处'])
def test_third_person_statement_does_not_set_my_boundary(text):assert explicit_boundary(text) is None
def test_polite_refusal_does_not_push_or_move(engine):
    r=step(engine,speech='不用不用，麻烦你了',motion_authorized=True)
    assert r['action']=='WAIT' and not r['motion']['authorized']

def test_distance_boundary_allows_conversation(engine):
    step(engine,speech='别靠近我')
    original=engine.predictor.state
    def converse(history,speech):
        p=original(history,speech);p['policy']['label']='COMFORT';return p
    engine.predictor.state=converse
    r=step(engine,speech='今天工作不顺心')
    assert r['action']=='COMFORT' and r['boundary_state']=='keep_distance'
    assert not r['motion']['authorized']

def test_polite_refusal_cancels_existing_task_request(engine):
    r=step(engine,speech='不用了，谢谢',current_task='cleaning',target_device='cleaner',confirmed_task_intent='cancel_current_task',task_execution_authorized=True)
    assert r['action']=='CANCEL_TASK'
    assert command_from_decision(r)['operation']=='cancel'

def test_reported_refusal_cannot_bypass_boundary_guard_through_policy(engine):
    original=engine.predictor.state
    def quoted(history,speech):
        p=original(history,speech);p['policy']['label']='SILENCE';p['boundary']['label']='do_not_disturb';return p
    engine.predictor.state=quoted
    r=step(engine,speech='电视里那个人说别打扰我')
    assert r['action']=='CLARIFY' and r['boundary_state']=='open'
    step(engine,speech='别打扰我')
    assert step(engine,speech='电视里那个人说别打扰我')['action']=='SILENCE'

def test_task_no_longer_needed_is_still_cancellation(engine):
    original=engine.predictor.state
    def cancel(history,speech):
        p=original(history,speech);p['policy']['label']='CANCEL_TASK';return p
    engine.predictor.state=cancel
    assert step(engine,speech='刚才安排的事情不用做了')['action']=='CANCEL_TASK'

def test_confirmed_whitelisted_device_intent_overrides_wrong_neural_intent(engine):
    original=engine.predictor.state
    def wrong(history,speech):
        p=original(history,speech);p['intent']['label']='iot_hue_lightoff';return p
    engine.predictor.state=wrong
    args=dict(speech='打开客厅灯',task_execution_authorized=True,target_device='living_light',confirmed_task_intent='iot_hue_lighton')
    r=step(engine,**args)
    assert r['neural']['intent']['label']=='iot_hue_lightoff'
    assert r['task']['intent']=='iot_hue_lighton'
    assert command_from_decision(r)['operation']=='turn_on'
    assert 'explicit_confirmed_device_intent' in r['overrides']
    assert command_from_decision(step(engine,**dict(args,asr_confidence=.3)))['kind']=='hold'
    assert command_from_decision(step(engine,**dict(args,confirmed_task_intent='unmapped')))['kind']=='hold'
    step(engine,speech='别打扰我')
    assert command_from_decision(step(engine,**args))['kind']=='hold'
