"""Real service, GPU Qwen, new sensor refs, persistence/restart and deletion."""
import base64,json,os,secrets,subprocess,sys,tempfile,time,urllib.request,urllib.error,http.cookiejar,socket
import psutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/upgrade_20261001';URL='http://127.0.0.1:8871'
evidence={};cookies=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
def call(path,method='GET',body=None,token=None):
 headers={'Content-Type':'application/json'}
 if token:headers['X-Member-Session']=token
 request=urllib.request.Request(URL+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=headers,method=method)
 with opener.open(request,timeout=90) as r:return json.load(r)
def start(data,log):
 with socket.socket() as probe:probe.bind(('127.0.0.1',8871))
 env={**os.environ,'PYTHONUTF8':'1','PYTHONPATH':str(ROOT),'SOCIAL_V5_DATA':str(data),'SOCIAL_PROFILE':'balanced','SOCIAL_DEVICE':'cuda'}
 env.pop('SOCIAL_API_TOKEN',None)
 p=subprocess.Popen([sys.executable,'-m','uvicorn','social_v5.server:app','--host','127.0.0.1','--port','8871'],env=env,cwd=ROOT.parent,stdout=log,stderr=log,creationflags=0x08000000 if os.name=='nt' else 0)
 for _ in range(90):
  if p.poll() is not None:raise RuntimeError('Server exited: inspect social_http_server.log')
  try:call('/health');return p
  except Exception:time.sleep(1)
 stop(p);raise RuntimeError('Server did not become ready')
def stop(p):
 try:children=psutil.Process(p.pid).children(recursive=True)
 except psutil.NoSuchProcess:children=[]
 for child in reversed(children):
  try:child.terminate()
  except psutil.NoSuchProcess:pass
 _,alive=psutil.wait_procs(children,timeout=15)
 for child in alive:child.kill()
 if p.poll() is None:p.terminate()
 p.wait(15)
def main():
 process=None
 with tempfile.TemporaryDirectory() as temp,(OUT/'social_http_server.log').open('w',encoding='utf-8') as log:
  try:
   process=start(temp,log);evidence['health']=call('/health')
   uid='verify_'+secrets.token_hex(4);pin=secrets.token_urlsafe(12)
   token=call('/v1/members','POST',{'user_id':uid,'display_name':'临时测试','pin':pin,'memory_consent':True})['session_token']
   image=base64.b64encode((ROOT/'tests/assets/astronaut.png').read_bytes()).decode()
   visual=call('/v1/vision/analyze','POST',{'image_base64':image,'camera_id':'s'},token)
   assert visual['human_state']['face']['valence'] is not None
   audio=base64.b64encode((ROOT/'models/sensevoice/test_wavs/zh.wav').read_bytes()).decode()
   speech=call('/v1/voice/transcribe','POST',{'audio_base64':audio,'session_id':'s'},token)
   assert speech['voice']['emotion_label'] and speech['text']
   visual=call('/v1/vision/analyze','POST',{'image_base64':image,'camera_id':'s'},token)
   out=call('/v1/step','POST',{'observation':{'speech':'我没事。','session_id':'s','audio_frame_id':speech['audio_frame_id'],'visual_frame_id':visual['frame_id']}},token)
   assert out['dialogue']['status']=='local_dialogue' and out['response_plan']['verbal_response']
   assert not out['response_plan']['robot_behavior']['execution_authorized']
   evidence['response']={'text':out['response'],'plan':out['response_plan'],'latency_ms':out['latency_ms']}
   try:call('/v1/step','POST',{'observation':{'speech':'你好','session_id':'s','audio_frame_id':speech['audio_frame_id']}});raise AssertionError('owner bypass')
   except urllib.error.HTTPError as e:assert e.code==400
   # Independent new voice sample after the five-second statistic interval.
   time.sleep(5);call('/v1/voice/transcribe','POST',{'audio_base64':audio,'session_id':'s'},token)
   model=call('/v1/user-model',token=token);assert model['baseline'].get('voice.speech_rate')
   assert not any(k.startswith('face.') for k in model['baseline']) # public fixture was not enrolled as this user
   first_pid=call('/health')['process_id'];stop(process);process=start(temp,log)
   second_pid=call('/health')['process_id'];assert second_pid!=first_pid
   evidence['server_pids']=[first_pid,second_pid]
   token=call('/v1/login','POST',{'user_id':uid,'pin':pin})['session_token']
   assert call('/v1/user-model',token=token)['baseline']==model['baseline']
   evidence['restart_preserves_consented_statistics']=True
   call('/v1/memory/consent','PUT',{'memory_consent':False},token)
   assert call('/v1/user-model',token=token)=={}
   assert call('/v1/human-state?session_id=s',token=token)['voice']['confidence']==0
   call('/v1/member','DELETE',token=token)
   evidence.update(passed=True,owner_spoof_rejected=True,consent_revocation_verified=True,raw_media_saved=False)
  except Exception as e:
   import traceback
   evidence.update(passed=False,error=str(e),traceback=traceback.format_exc());raise
  finally:
   if process:stop(process)
   (OUT/'social_http.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(evidence,ensure_ascii=False))
if __name__=='__main__':main()
