import time
import pytest
from social_v4.engine import SocialEngine
from social_world_zh.schema import Observation
from social_world_zh.memory import MemoryStore
from social_world_zh.adapter import command_from_decision

class FakePredictor:
    action='RESPOND'
    confidence=.99
    def __init__(self):self.calls=[]
    def state(self,history,speech):
        self.state_history=list(history)
        return {k:{'label':v,'confidence':self.confidence if k=='policy' else .99,'distribution':{v:1.}} for k,v in {'emotion':'neutral','dialog_act':'statement-non-opinion','intent':'iot_hue_lighton','boundary':'unspecified','policy':self.action,'task_domain':'酒店'}.items()}
    def generate_dialogue(self,history,speech,memories,policy):
        self.calls.append((list(history),speech,memories,policy))
        return {'reply':'这是结合前文的回答。','action_authority':False,'status':'local_dialogue'}

@pytest.fixture
def engine(tmp_path):
    memory=MemoryStore(tmp_path/'memory.sqlite');e=SocialEngine(FakePredictor(),memory)
    yield e
    memory.db.close()

def step(e,**kw):return e.step(Observation(**kw))

def test_generated_reply_replaces_history_and_keeps_context(engine):
    for i in range(7):step(engine,speech=f'第{i}次聊天')
    assert len(engine.predictor.calls[-1][0])==12
    assert len(engine.predictor.state_history)==4
    assert all(t=='这是结合前文的回答。' for role,t in engine.sessions[('default','anonymous')]['history'] if role=='对方')
    assert len(engine.sessions[('default','anonymous')]['history'])==12

@pytest.mark.parametrize('kwargs',[
    {'speech':'请不要打扰我'}, {'speech':'你好','person_present':False},
    {'speech':'听不清','asr_confidence':.2}, {'speech':'安静','preferred_style':'silent'},
    {'speech':'救命','emergency_verified':True}, {'speech':'不用了，谢谢'},
    {'speech':'打开客厅灯','task_execution_authorized':True,'target_device':'living_light','confirmed_task_intent':'iot_hue_lighton'}])
def test_controller_events_do_not_trigger_free_generation(engine,kwargs):
    result=step(engine,**kwargs)
    assert engine.predictor.calls==[]
    assert result['dialogue']['action_authority'] is False

def test_uncertain_social_policy_allows_contextual_clarification_only(engine):
    engine.predictor.confidence=.3
    result=step(engine,speech='这个我还是有点在意')
    assert result['action']=='CLARIFY'
    assert engine.predictor.calls
    assert command_from_decision(result)['kind']=='hold'

def test_confident_clarification_and_unconfirmed_device_keep_context_but_hold(engine):
    engine.predictor.action='CLARIFY'
    result=step(engine,speech='刚才说的位置是哪里？')
    assert engine.predictor.calls and command_from_decision(result)['kind']=='hold'
    engine.predictor.action='TASK_REQUEST'
    result=step(engine,speech='把那个关掉')
    assert result['dialogue']['status']=='local_dialogue'
    assert not result['task']['authorized'] and command_from_decision(result)['kind']=='hold'

def test_model_human_help_suggestion_does_not_contact_anyone(engine):
    engine.predictor.action='CALL_HUMAN'
    result=step(engine,speech='快递放错地方，真烦')
    assert engine.predictor.calls and not result['human_request']
    assert result['human_assistance']['authorized'] is False

def test_generated_clarification_never_requests_a_password():
    from social_v4.response_guard import guard_reply
    result=guard_reply('你可以重新告诉我。','你还记得我的银行卡密码吗？')
    assert result['reason']=='do_not_request_authentication_secret'
    assert guard_reply('请不要把密码告诉我。','你记得我的密码吗？')['accepted']

def test_context_user_isolation_forget_and_expiration(engine):
    step(engine,user_id='a',speech='甲的事情')
    step(engine,user_id='b',speech='乙的事情')
    assert engine.predictor.calls[-1][0]==[]
    engine.forget('a');step(engine,user_id='a',speech='重新开始')
    assert engine.predictor.calls[-1][0]==[]
    engine.sessions[('default','a')]['time']=time.monotonic()-301
    step(engine,user_id='a',speech='又一次开始')
    assert engine.predictor.calls[-1][0]==[]

def test_memory_only_retrieved_with_consent(engine):
    step(engine,user_id='a',speech='我喜欢种花',memory_note='喜欢种花',identity_verified=True,memory_consent=True)
    step(engine,user_id='a',speech='种花',identity_verified=True,memory_consent=False)
    assert engine.predictor.calls[-1][2]==[]

def test_generated_words_never_authorize_hardware(engine):
    engine.predictor.generate_dialogue=lambda *args,**kw:{'reply':'我已经打开灯了。','action_authority':False}
    result=step(engine,speech='聊聊灯光设计')
    assert not result['task']['authorized'] and not result['motion']['authorized']
    assert command_from_decision(result)['kind']=='hold'
    assert result['response']=='我还没有执行设备操作，需要先确认设备和指令，再由控制器处理。'
    assert result['dialogue']['grounding_guard']=='unsupported_device_completion'
    assert result['dialogue']['reply']==result['response']

def test_truthful_no_execution_statement_is_retained():
    from social_v4.response_guard import guard_reply
    assert guard_reply('没有控制器结果，不能说我已经打开了灯。')['accepted']

def test_visual_capability_boundary_does_not_guess_pixels(engine):
    result=step(engine,speech='看着窗外的花，你觉得外观怎么样？')
    assert not engine.predictor.calls
    assert result['dialogue']['status']=='capability_boundary'
    assert '没有收到图像' in result['response']
    result=step(engine,speech='刚才我用文字说帽子是紫色的，它是什么颜色？')
    assert engine.predictor.calls

def test_bereavement_guard_preserves_user_choice_and_negation():
    from social_v4.response_guard import guard_reply
    speech='养了十年的狗去世了，我很想它。'
    bad='失去宠物很难过，但你可以用新伙伴填补空缺。'
    assert guard_reply(bad,speech)['reason']=='bereavement_replacement_advice'
    assert guard_reply('不必用新伙伴填补空缺，我可以听你说。',speech)['accepted']
    assert guard_reply(bad,speech+'我在考虑领养新的宠物。')['accepted']
    assert guard_reply('失去它很难受，我愿意听你说。',speech)['accepted']
