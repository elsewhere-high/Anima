"""Real encoders + owner-bound API tests; Qwen is covered by benchmark_profiles.py."""
import base64
import pytest
from social_v5 import ROOT
from social_v5.social_runtime import SocialRuntime
from social_v5.memory import MemoryStore
from social_v5.vision import Vision
from social_v5.schema import Observation
from social_v5.engine import SocialEngine
from social_v5.temporal import HumanStateBuffer

@pytest.fixture(scope='module')
def runtime(tmp_path_factory):
    p=tmp_path_factory.mktemp('real_social');m=MemoryStore(p/'m.db',p/'key');m.register('a','a','testsecret',True)
    r=SocialRuntime(m,Vision(m));yield r;r.close();m.db.close()

def test_real_encoders_owner_expiry_and_deletion(runtime):
    r=runtime;image=base64.b64encode((ROOT/'tests/assets/astronaut.png').read_bytes()).decode()
    visual=r.visual(image,'owner','session','a');state=visual['human_state']
    assert len(state['face']['facial_embedding'])==1280
    assert state['face']['valence'] is not None and len(state['body']['pose'])==33
    assert r.visual(image,'owner','session','a')['sampling']['cached']
    sound=base64.b64encode((ROOT/'models/sensevoice/test_wavs/zh.wav').read_bytes()).decode()
    audio=r.audio(sound,'owner','session','a')
    assert audio['text'] and audio['voice']['speech_rate']>0
    with pytest.raises(ValueError):r.state('other','session',audio_ref=audio['audio_frame_id'])
    with pytest.raises(ValueError):r.state('owner','other',audio_ref=audio['audio_frame_id'])
    # ASR cold load may exceed the five-second visual TTL; refresh as the UI does.
    r.visual(image,'owner','session','a')
    state=r.state('owner','session','我没事','a',audio['audio_frame_id'])
    assert state.voice.emotion_label and state.face.valence is not None
    r.memory.consent('a',False);r.clear(uid='a')
    assert not r.memory.user_model('a')
    assert r.state('owner','session','',uid='a').face.valence is None
    with pytest.raises(ValueError):r.state('owner','session',audio_ref=audio['audio_frame_id'])

def test_real_no_face_clears_previous_evidence(runtime):
    import cv2,numpy as np,time
    blank=base64.b64encode(cv2.imencode('.png',np.zeros((320,320,3),np.uint8))[1]).decode()
    out=runtime.visual(blank,'blank','s')
    assert out['human_state']['face']['confidence']==0
    assert out['human_state']['face']['valence'] is None

def test_best_edge_real_geometry():
    import cv2,numpy as np
    from social_v5.face_geometry import FaceGeometry
    model=FaceGeometry()
    try:
        image=cv2.imdecode(np.frombuffer((ROOT/'tests/assets/astronaut.png').read_bytes(),np.uint8),1)
        result=model.analyze(image)
        assert len(result['face_mesh'])==478 and len(result['facial_blendshapes'])==52
        assert np.isfinite(result['head_pose']['yaw_degrees'])
        assert result['gaze']['gaze_to_robot_available'] is False
    finally:model.close()

def test_no_text_distress_respects_existing_controller(tmp_path):
    # Synthetic social signals deliberately test the controller, not a perception score.
    class FakePredictor:
        def state(self,history,speech):
            return {k:{'label':v,'confidence':.99,'distribution':{v:1.}} for k,v in {'emotion':'neutral','dialog_act':'statement-non-opinion','intent':'general_quirky','boundary':'unspecified','policy':'RESPOND','task_domain':'酒店'}.items()}
    m=MemoryStore(tmp_path/'m.db',tmp_path/'key');engine=SocialEngine(FakePredictor(),m)
    b=HumanStateBuffer();state=b.update(('a','s'),voice={'confidence':.8,'emotion_label':'SAD','audio_events':['Crying']})
    out=engine.step(Observation(speech=''),human_state=state)
    assert out['response'] and out['response_plan']['response_strategy']=='gentle_check_in'
    out=engine.step(Observation(speech='',boundary='do_not_disturb'),human_state=state)
    assert not out['response'] and out['response_plan']['response_strategy']=='respect_silence'
    assert not out['motion']['authorized']
    m.db.close()
