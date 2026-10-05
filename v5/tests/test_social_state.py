"""Deterministic scenario/contract tests; synthetic evidence is not model accuracy."""
import math
import numpy as np
import pytest
from social_v5.temporal import HumanStateBuffer,response_plan
from social_v5.audio_features import extract_audio_features
from social_v5.human_state import HumanState
from social_v5.memory import MemoryStore
from social_v5.scheduler import PerceptionScheduler,BusyError

def face(v):return {'source':'synthetic_scenario','confidence':.9,'valence':v,'arousal':.5}
def voice(rate=4,emotion='NEUTRAL',events=None):
    return {'source':'synthetic_scenario','confidence':.8,'speech_rate':rate,'emotion_label':emotion,'audio_events':events or [],'pause':{'ratio':.2}}
def body(movement=.3):return {'source':'synthetic_scenario','confidence':.8,'movement_intensity':movement}

def test_case1_its_fine_conflict_is_not_deception():
    b=HumanStateBuffer();s=b.update(('a','s'),face=face(-.8),voice=voice(emotion='SAD'),body=body(.01),text='我没事。',now=0)
    assert s.language.contradiction and s.cross_modal_consistency<.7
    assert response_plan(s)['response_strategy']=='gentle_check_in'
    assert not response_plan(s)['robot_behavior']['execution_authorized']

def test_case2_changes_relative_to_slow_person_not_population():
    b=HumanStateBuffer()
    for i in range(30):s=b.update(('a','s'),face=face(.2),voice=voice(2),body=body(.5),now=i*6)
    assert s.temporal.baseline['voice.speech_rate']==2
    assert abs(s.temporal.delta['voice.speech_rate'])<.001
    s=b.update(('a','s'),face=face(-.5),voice=voice(1),body=body(.01),now=180)
    assert s.temporal.delta['voice.speech_rate']<-.8 and s.event=='personal_state_change'

def test_case3_smiling_frustration_keeps_uncertainty():
    b=HumanStateBuffer();s=b.update(('a','s'),face=face(.8),voice=voice(emotion='HAPPY'),text='烦死了。',now=0)
    assert 'frustrated' in s.language.explicit_emotion and s.language.contradiction
    assert 'inconsistent_signals_do_not_infer_deception' in s.uncertainty

def test_case4_crying_without_any_text():
    b=HumanStateBuffer();s=b.update(('a','s'),voice=voice(emotion='SAD',events=['Crying']),body=body(.0),text='',now=0)
    assert s.event=='nonverbal_distress' and not s.language.explicit_emotion
    assert response_plan(s)['response_strategy']=='gentle_check_in'
    assert response_plan(s,silent=True)['response_strategy']=='respect_silence'

def test_weak_audio_event_is_not_proactive_distress():
    s=HumanStateBuffer().update(('a','s'),voice={'confidence':.1,'audio_events':['Crying']},now=0)
    assert s.event=='stable_or_insufficient_evidence'

def test_case5_robot_action_then_reaction_is_association_only():
    clock=[0.];b=HumanStateBuffer(clock=lambda:clock[0]);b.update(('a','s'),face=face(.5),body=body(.4))
    b.record_action(('a','s'),'solution_oriented');clock[0]=5
    s=b.update(('a','s'),face=face(-.5),body=body(.01))
    r=s.interaction.action_reaction
    assert r['robot_action']=='solution_oriented' and r['human_state_delta']['face.valence']<0
    assert not r['causation_proven']

def test_expiry_missing_and_stream_isolation():
    b=HumanStateBuffer();b.update(('a','s'),face=face(.5),voice=voice(),now=0)
    assert b.update(('b','s'),now=1).face.valence is None
    assert b.update(('a','s'),now=6).face.valence is None
    assert b.update(('a','s'),now=16).voice.emotion_label is None

def test_polls_dont_train_baseline_and_payload_is_compact():
    b=HumanStateBuffer();b.update(('a','s'),face=face(.5),now=0)
    for i in range(100):s=b.update(('a','s'),now=i*.001)
    assert s.temporal.sample_count==1 and not s.temporal.baseline
    s.face.facial_embedding=[1.]*1280
    assert 'facial_embedding' not in s.compact()['face']

def test_baseline_encryption_consent_restart_delete(tmp_path):
    m=MemoryStore(tmp_path/'m.db',tmp_path/'key');m.register('a','a','secret-pin',True)
    b=HumanStateBuffer(m)
    for i in range(30):b.update(('owner','s'),face=face(.25),uid='a',consent=True,now=i*6)
    saved=m.user_model('a');assert saved['baseline']['face.valence']['count']>=20
    assert saved['personality']['big_five'] is None
    other=HumanStateBuffer(m);s=other.update(('owner2','s'),face=face(-.5),uid='a',consent=True,now=190)
    assert s.temporal.delta['face.valence']<-.5
    m.consent('a',False);assert m.user_model('a')=={}
    assert m.db.execute('SELECT COUNT(*) FROM user_models').fetchone()[0]==0
    m.db.close()

def test_dsp_sine_pitch_and_silence_are_not_emotion():
    x=.1*np.sin(2*np.pi*200*np.arange(16000)/16000)
    d=extract_audio_features(x,'你好')
    assert abs(d['pitch']['median_hz']-200)<5
    assert not d['audio_events'] and 'emotion_label' not in d
    d=extract_audio_features(np.zeros(16000));assert d['pitch']['median_hz'] is None

def test_bounded_scheduler_rejects_backlog():
    import threading
    scheduler=PerceptionScheduler();gate=threading.Event()
    f=scheduler.submit('face',lambda:gate.wait(2))
    try:
        with pytest.raises(BusyError):scheduler.submit('face',lambda:1)
        assert scheduler.submit('body',lambda:2).result()==2
    finally:gate.set();f.result();scheduler.close()

def test_nonfinite_rejected():
    with pytest.raises(ValueError):HumanState(face={'valence':float('nan')})
