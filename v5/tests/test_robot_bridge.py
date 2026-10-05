import sys,time
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from robot_bridge import Bridge

def test_bridge_rejects_remote_cleartext_and_short_key():
    with pytest.raises(ValueError):Bridge('http://192.168.1.2:8768','r','x'*32)
    with pytest.raises(ValueError):Bridge('http://127.0.0.1:8768','r','short')

def test_bridge_heartbeat_loses_speaker_permission_when_hardware_stale():
    b=Bridge('http://127.0.0.1:8768','r','x'*32);sent=[]
    b.request=lambda path,body,**kwargs:sent.append(body) or body
    b.estop=False;b.speaker=True;b.last_input=time.monotonic()-7
    b.heartbeat();assert sent[-1]['emergency_stop'] and not sent[-1]['speaker_ready']

def test_bridge_rechecks_stop_after_response_and_keeps_session_stable():
    b=Bridge('http://127.0.0.1:8768','r','x'*32);b.estop=False;b.speaker=True;ids=[]
    def request(path,body,**kwargs):
        ids.append(body['observation']['session_id']);b.estop=True
        return {'output':{'outputs':{'display':'你好','speak':'你好'}}}
    b.request=request
    assert b.handle({'type':'speech','text':'你好'})['outputs']['speak']==''
    b.handle({'type':'speech','text':'继续'});assert ids[0]==ids[1]

def test_bridge_does_not_poll_private_care_as_guest():
    b=Bridge('http://127.0.0.1:8768','r','x'*32)
    b.request=lambda *a,**k:pytest.fail('Guest should not request private data')
    assert b.handle({'type':'poll'})['reason']=='member_login_required'
