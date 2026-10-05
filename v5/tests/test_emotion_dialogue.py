"""Regression scenarios use synthetic signals; they do not measure emotion accuracy."""
import pytest
from social_v5.conversation import build_messages,turn_plan
from social_v5.human_state import HumanState
from social_v5.temporal import HumanStateBuffer,language_signal
from social_v5.personality import dialogue_policy
from social_v5.expression_actions import action_scores
from test_api import client
from social_v5.server import app

@pytest.mark.parametrize('text', ['我不是难过','我没有感到伤心','她很开心','如果我难过怎么办','电影里的人很伤心','“我好开心”这句话怎么翻译'])
def test_negated_or_other_emotions_are_not_self_reports(text):
    assert not language_signal(text,0).explicit_emotion

def test_current_feeling_after_correction():
    assert language_signal('以前很伤心，但是现在我很开心',0).explicit_emotion==['happy']
    assert language_signal('特别开心',0).explicit_emotion==['happy']
    assert language_signal('我不是说难过',0).explicit_emotion==[]

def test_actions_need_repeated_frames_and_clear_on_loss_or_switch():
    b=HumanStateBuffer();face={'confidence':.8,'facial_blendshapes':{'mouthSmileLeft':.9,'mouthSmileRight':.8}}
    assert not b.update(('o','s'),face=face,now=0).face.stable_actions
    b.update(('o','s'),face=face,now=1)
    assert b.update(('o','s'),face=face,now=2).face.stable_actions==['嘴角上扬']
    assert not b.update(('o','s'),face={**face,'_tracking_continuous':False},now=3).face.stable_actions
    assert not b.update(('o','s'),face={'confidence':0},now=4).face.stable_actions
    assert not b.update(('o','s'),face=face,now=5).face.stable_actions
    assert not b.update(('o','s'),now=11).face.stable_actions
    assert not b.update(('stranger','s'),face=face,now=12).face.stable_actions

def test_movement_scores_not_emotional_or_nan():
    assert action_scores({'jawOpen':float('nan'),'mouthSmileLeft':1,'mouthSmileRight':0})=={'mouth_corners_up':0}

def plan(text,history=()):
    return turn_plan(text,history,HumanState(language=language_signal(text,0)),dialogue_policy({},text,history))

def test_listening_continues_until_new_request():
    h=[('用户','先别给我建议'),('对方','你说。')]
    assert plan('他连尝都没尝',h)['support']=='listen'
    assert plan('现在帮我想一句可以对他说的话',h)['mode']=='one_concrete_step'

def test_correction_and_question_fatigue():
    assert plan('我不是难过，我是惊喜')['mode']=='accept_correction'
    assert plan('你一直问问题让我很累')['question_budget']==0
    assert plan('三朵',[('对方','什么颜色？'),('用户','白色'),('对方','几朵？')])['question_budget']==0

def test_compact_prompt_keeps_twenty_four_messages_without_biometric_vectors():
    history=[('用户' if i%2==0 else '对方',str(i)) for i in range(30)]
    messages=build_messages(history,'继续',[],{'visual_evidence':{'status':'single_visible_face','expression':{'distribution':{'a':.8},'facial_embedding':[1]*1280}}})
    assert len(messages)==26 and messages[1]['content']=='6'
    assert 'facial_embedding' not in messages[0]['content'] and 'distribution' not in messages[0]['content']
    assert len(messages[0]['content'])<1500

def test_engine_preserves_longer_conversation_and_passes_strategy(client):
    for i in range(9):
        response=client.post('/v1/step',json={'observation':{'speech':f'我今天看到第{i}朵花'}})
        assert response.status_code==200
    history,_,policy=app.state.engine.predictor.calls[-1]
    assert len(history)==16 and '第0朵花' in history[0][1]
    assert 'conversation' in policy and not response.json()['motion']['authorized']

def test_smiling_does_not_override_explicit_sadness():
    state=HumanStateBuffer().update(('a','s'),face={'confidence':.9,'valence':.8},text='我很难过',now=0)
    p=turn_plan('我很难过',[],state,dialogue_policy({},'我很难过',[]))
    assert p['mode']=='acknowledge_specific_feeling' and p['self_report_priority']
    assert p['nonverbal_tone']['style']=='gentle'

def test_reliable_nonverbal_evidence_changes_tone_and_expires():
    buffer=HumanStateBuffer()
    state=buffer.update(('a','s'),face={'confidence':.9,'valence':-.8},text='嗯',now=0)
    assert turn_plan('嗯',[],state,{})['nonverbal_tone']['style']=='gentle'
    state=buffer.update(('a','s'),text='嗯',now=6)
    assert 'nonverbal_tone' not in turn_plan('嗯',[],state,{})

def test_generation_stops_at_complete_sentences():
    import torch
    from types import SimpleNamespace
    from social_v4.chat_model import generate_text
    class Tokenizer:
        eos_token_id=5
        def convert_tokens_to_ids(self,_):return 5
        def apply_chat_template(self,*args,**kwargs):return torch.tensor([[5]])
        def decode(self,ids,**kwargs):return ''.join(['好','。','继续','。','多余',''][i] for i in ids)
    class Backbone:
        autocast_enabled=False
        def __init__(self):self.index=0
        def __call__(self,**kwargs):
            hidden=torch.zeros(1,1,6);hidden[0,0,self.index]=1;self.index+=1
            return SimpleNamespace(last_hidden_state=hidden,past_key_values=None)
        def get_input_embeddings(self):return SimpleNamespace(weight=torch.eye(6))
    result=generate_text(Backbone(),Tokenizer(),[{'role':'system','content':'s'},{'role':'user','content':'u'}],device='cpu',max_sentences=2)
    assert result['reply']=='好。继续。' and result['stop_reason']=='sentence_limit'

def test_remove_already_answered_question_but_keep_quoted_suggestion():
    from social_v5.conversation import remove_repeated_questions
    history=[('对方','你最在意的是什么？')]
    assert remove_repeated_questions('是你的心意。你最在意的是什么？',history,{},'心意')=='是你的心意。'
    assert remove_repeated_questions('你可以说：“愿意尝一口吗？”',[],{'question_budget':0},'帮我想一句')=='你可以说：“愿意尝一口吗？”'

def test_composition_uses_source_facts_not_assistant_inventions():
    p={'conversation':{'compose_utterance':True,'recent_assistant_openings':['他离开了']}}
    messages=build_messages([('用户','我做了饭'),('对方','他离开了'),('用户','你一直问问题让我像在做访谈')],'帮我想一句话',[],p)
    assert len(messages)==2 and '我做了饭' in messages[1]['content'] and '他离开了' not in str(messages)
    assert '访谈' not in str(messages)

def test_wording_can_preserve_users_own_feeling_without_role_inversion():
    from social_v5.conversation import grounded_wording
    h=[('用户','对，我就是觉得自己忙活了半天，心意没人看见。'),('用户','你一直问问题让我很累')]
    assert grounded_wording(h)=='可以先这样说：“我觉得自己忙活了半天，心意没人看见。”'
    assert grounded_wording([('对方','我觉得是这样')]) is None
