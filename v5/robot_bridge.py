"""JSON-lines bridge for a robot host. Standard library only; no motor commands.

stdin: {"type":"speech","text":"你好"}, {"type":"poll","person_present":true},
       {"type":"reminder","id":1,"occurrence":"...","action":"ack"}
stdout: versioned output envelopes. The vendor host supplies ASR/display/TTS.
"""
import argparse,json,os,sys,time,threading,urllib.request,urllib.error,secrets,queue
from urllib.parse import urlparse,quote

class Bridge:
    def __init__(self,base,robot_id,robot_token,api_token='',member_id='',pin='',timeout=20):
        url=urlparse(base)
        if url.scheme not in {'http','https'}:raise ValueError('Only HTTP(S) is supported')
        if url.scheme=='http' and url.hostname not in {'127.0.0.1','localhost','::1'}:raise ValueError('Use HTTPS for non-loopback robot connections')
        if len(robot_token)<24:raise ValueError('Set SOCIAL_ROBOT_TOKEN to the same 24+ character key as the brain service')
        self.base=base.rstrip('/');self.robot_id=robot_id;self.robot_token=robot_token;self.api_token=api_token;self.member_id=member_id;self.pin=pin;self.timeout=timeout
        self.session_token='';self.session_expiry=0;self.session_id=secrets.token_hex(12);self.stop_event=threading.Event();self.state_lock=threading.RLock();self.auth_lock=threading.RLock();self.output_lock=threading.RLock()
        self.estop=True;self.battery=None;self.speaker=False;self.display=True;self.last_input=time.monotonic();self.thread=None;self.generation=0
    def request(self,path,body=None,member=True,timeout=None):
        if member and self.member_id:self.authenticate()
        headers={'Content-Type':'application/json','X-Robot-Token':self.robot_token}
        if self.api_token:headers['Authorization']='Bearer '+self.api_token
        if member and self.session_token:headers['X-Member-Session']=self.session_token
        req=urllib.request.Request(self.base+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=timeout or self.timeout) as response:return json.load(response)
    def authenticate(self):
        with self.auth_lock:
            if time.monotonic()<self.session_expiry:return
            result=self.request('/v1/login',{'user_id':self.member_id,'pin':self.pin},member=False)
            self.session_token=result['session_token'];self.session_expiry=time.monotonic()+result['expires_in']-60
    def emit(self,value):
        with self.output_lock:print(json.dumps(value,ensure_ascii=False),flush=True)
    def heartbeat(self):
        with self.state_lock:
            stale=time.monotonic()-self.last_input>6
            data={'robot_id':self.robot_id,'emergency_stop':self.estop or stale,'battery_percent':self.battery,'speaker_ready':self.speaker and not stale,'display_ready':self.display}
        return self.request('/v1/robot/heartbeat',data,member=False,timeout=3)
    def background(self):
        while not self.stop_event.is_set():
            try:self.heartbeat()
            except Exception:self.emit({'protocol':'home-companion/1','event':'connection_lost','motion':{'command':'HOLD','authorized':False},'outputs':{'display':'陪伴服务暂时不可用，请联系身边的人；紧急情况请使用当地急救电话。','speak':''}})
            self.stop_event.wait(2)
    def start(self):
        self.heartbeat();self.thread=threading.Thread(target=self.background,daemon=True);self.thread.start()
    def handle(self,value):
        kind=value.get('type')
        if kind=='help':value={**value,'type':'speech','text':'救命','asr_confidence':1};kind='speech'
        if kind=='hardware':
            with self.state_lock:
                self.estop=bool(value.get('emergency_stop',True));self.battery=value.get('battery_percent');self.speaker=bool(value.get('speaker_ready',False));self.display=bool(value.get('display_ready',True));self.last_input=time.monotonic()
            return {'event':'hardware_status','status':self.heartbeat()}
        if kind=='speech':
            text=value.get('text','')
            if not isinstance(text,str) or len(text)>600:raise ValueError('Speech must be <=600 characters')
            started=time.monotonic()
            result=self.request('/v1/robot/turn?robot_id='+quote(self.robot_id,safe=''),{'observation':{'speech':text,'session_id':self.session_id,'asr_confidence':value.get('asr_confidence',1)}})
            output=result['output']
            # The host must recheck this TTL and hardware state at execution time.
            with self.state_lock:
                if self.estop or time.monotonic()-self.last_input>6:output['outputs']['speak']=''
            output['transport_elapsed_ms']=round((time.monotonic()-started)*1000)
            return output
        if kind=='poll':
            if not self.member_id:return {'event':'care','reminders':[],'reason':'member_login_required'}
            return {'event':'care',**self.request('/v1/care/poll',{'person_present':bool(value.get('person_present',False)),'interaction_busy':bool(value.get('interaction_busy',True))})}
        if kind=='reminder':
            return self.request(f"/v1/care/reminders/{int(value['id'])}/resolve",{'action':value['action'],'occurrence':value['occurrence'],'minutes':value.get('minutes',10)})
        raise ValueError('Supported types: hardware, speech, poll, reminder, help')
    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=4)
        with self.state_lock:self.estop=True;self.speaker=False
        try:self.heartbeat()
        except Exception:pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:8768');parser.add_argument('--robot-id',default='home-robot');parser.add_argument('--check',action='store_true');args=parser.parse_args()
    bridge=Bridge(args.base,args.robot_id,os.getenv('SOCIAL_ROBOT_TOKEN',''),os.getenv('SOCIAL_API_TOKEN',''),os.getenv('COMPANION_MEMBER',''),os.getenv('COMPANION_PIN',''))
    if args.check:bridge.emit(bridge.request('/v1/robot/capabilities',member=False));return
    bridge.start();pending=queue.Queue(maxsize=1)
    def process(value,generation):
        try:
            output=bridge.handle(value)
            if generation==bridge.generation:bridge.emit(output)
        except urllib.error.HTTPError as e:
            if e.code==401:bridge.session_expiry=0
            bridge.emit({'event':'request_failed','http_status':e.code,'retry_automatically':False,'motion':{'command':'HOLD','authorized':False},'message':'本轮未完成。检查连接或登录后重试；提醒不要自动确认。'})
        except Exception as e:bridge.emit({'event':'request_failed','error_type':type(e).__name__,'motion':{'command':'HOLD','authorized':False},'message':'输入或连接异常，本轮未完成。'})
    def work():
        while not bridge.stop_event.is_set():
            try:value,generation=pending.get(timeout=.5)
            except queue.Empty:continue
            try:
                if generation==bridge.generation:process(value,generation)
            finally:pending.task_done()
    worker=threading.Thread(target=work,daemon=True);worker.start()
    try:
        for line in sys.stdin:
            if not line.strip():continue
            try:
                value=json.loads(line)
                if not isinstance(value,dict):raise ValueError('Expected object')
                if value.get('type') in {'hardware','help'}:
                    if value.get('type')=='help' or value.get('emergency_stop',True):bridge.generation+=1
                    process(value,bridge.generation)
                else:pending.put_nowait((value,bridge.generation))
            except queue.Full:bridge.emit({'event':'busy','retry_automatically':False,'message':'上一轮尚未结束；硬件状态和 help 求助仍可立即输入。'})
            except (ValueError,TypeError):bridge.emit({'event':'invalid_input','message':'请提供 JSON 对象。'})
        pending.join()
    finally:bridge.close()

if __name__=='__main__':main()
