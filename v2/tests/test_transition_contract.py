import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from social_world_zh.transition import candidate_state_text,TransitionPrior

def test_candidate_speaker_perspective_is_swapped():
    text=candidate_state_text([('用户','我想休息'),('对方','需要安静吗')],'是的','那我先不打扰了')
    assert '对方：我想休息' in text and '用户：需要安静吗' in text
    assert '对方：是的' in text and '当前用户：那我先不打扰了' in text

def test_observational_candidate_effect_and_probability_contract():
    prior=TransitionPrior.__new__(TransitionPrior)
    prior.tables={'next_act':np.array([[[.9,.1],[.2,.8]],[[.4,.6],[.7,.3]]])}
    prior.config={'heads':{'next_act':{'alpha':1.,'temperature':1.}}}
    neural=np.array([[.5,.5],[.5,.5]]);current=np.array([[1.,0.],[1.,0.]]);candidate=np.eye(2)
    p=prior.combine('next_act',neural,current,candidate)
    assert np.allclose(p.sum(1),1) and np.all(p>=0)
    assert p[0].argmax()!=p[1].argmax()

def test_no_speech_does_not_invent_emotion():
    from social_world_zh.predictor import Predictor
    predictor=Predictor.__new__(Predictor)
    p=predictor.state([],' ')
    assert p['emotion']['label']=='unknown' and p['emotion']['confidence']==0
