import hashlib,os,secrets,time,threading
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,Depends,Request,Header
from fastapi.responses import FileResponse
from . import ROOT
from .schema import StepRequest,Frame,Enrollment,Register,Login,Consent,MemoryWrite,DialoguePreferences
from .personality import catalog
from .memory import MemoryStore,safe_text
from .engine import SocialEngine
from .vision import Vision

class Sessions:
    def __init__(self):self.tokens={};self.attempts={};self.lock=threading.RLock()
    def issue(self,uid):
        with self.lock:
            now=time.monotonic();self.tokens={k:v for k,v in self.tokens.items() if v[1]>now}
            if len(self.tokens)>=512:raise HTTPException(429,'会话过多，请稍后重试')
            token=secrets.token_urlsafe(32);self.tokens[token]=(uid,now+3600);return token
    def resolve(self,token):
        with self.lock:
            pair=self.tokens.get(token)
            if not pair or pair[1]<time.monotonic():
                self.tokens.pop(token,None);raise HTTPException(401,'请先登录，或重新登录已过期的会话')
            return pair[0]
    def revoke(self,uid):
        with self.lock:self.tokens={k:v for k,v in self.tokens.items() if v[0]!=uid}
    def attempt(self,uid):
        with self.lock:
            now=time.monotonic();self.attempts={k:v for k,v in self.attempts.items() if now-v[0]<300}
            start,count=self.attempts.get(uid,(now,0))
            if count>=10 or len(self.attempts)>1024:raise HTTPException(429,'尝试次数过多，请五分钟后重试')
            self.attempts[uid]=(start,count+1)

def guard(request:Request):
    if request.method in {'POST','DELETE','PUT','PATCH'}:
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):raise HTTPException(403,'跨站请求已拒绝')
    token=os.getenv('SOCIAL_API_TOKEN','')
    if token and not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+token):raise HTTPException(401,'需要机器人网关授权令牌')

def member(request:Request,x_member_session:str=Header(default='')):
    uid=request.app.state.sessions.resolve(x_member_session)
    if not request.app.state.memory.profile(uid):raise HTTPException(401,'成员已删除')
    return uid

@asynccontextmanager
async def lifespan(app):
    from .predictor import Predictor
    from .embedding import Embedding
    data=Path(os.getenv('SOCIAL_V5_DATA',str(ROOT/'data/private')));data.mkdir(parents=True,exist_ok=True)
    memory=MemoryStore(data/'companion.sqlite',data/'key.protected',Embedding())
    try:
        app.state.memory=memory;app.state.sessions=Sessions();app.state.vision=Vision(memory)
        from .social_runtime import SocialRuntime
        app.state.social=SocialRuntime(memory,app.state.vision)
        device=os.getenv('SOCIAL_DEVICE','auto')
        if device=='auto':
            import torch
            device='cuda' if torch.cuda.is_available() else 'cpu'
        app.state.engine=SocialEngine(Predictor(device),memory)
        yield
    finally:
        from .camera import bridge
        bridge.stop()
        if hasattr(app.state,'social'):app.state.social.close()
        memory.db.close()

app=FastAPI(title='居家陪伴 · 人脸与记忆',version='5.2.0',lifespan=lifespan)
from .voice import router as voice_router
app.include_router(voice_router(guard))
from .camera import router as camera_router
app.include_router(camera_router(guard))
from .care_api import router as care_router
from .robot import router as robot_router
app.include_router(care_router(guard,member))
app.include_router(robot_router(guard))

@app.middleware('http')
async def size_limit(request,call_next):
    guest=request.cookies.get('companion_guest','')
    if len(guest)!=32 or not all(c in '0123456789abcdef' for c in guest):guest=secrets.token_hex(16)
    request.state.guest_id=guest
    # Enforce actual streamed body size as well as Content-Length (no chunked bypass).
    if request.method in {'POST','PUT','PATCH'}:
        limit=34000000 if request.url.path=='/v1/faces/enroll' else 5700000
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>limit:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'请求内容过大'},status_code=413)
        request._body=bytes(body)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    if not request.cookies.get('companion_guest'):
        response.set_cookie('companion_guest',guest,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=3600)
    return response

@app.get('/')
def home():return FileResponse(ROOT/'web/index.html')

@app.get('/voice.js')
def voice_script():return FileResponse(ROOT/'web/voice.js',media_type='text/javascript')

@app.get('/turn_detector.js')
def turn_detector_script():return FileResponse(ROOT/'web/turn_detector.js',media_type='text/javascript')

@app.get('/camera.js')
def camera_script():return FileResponse(ROOT/'web/camera.js',media_type='text/javascript')

@app.get('/setup.js')
def setup_script():return FileResponse(ROOT/'web/setup.js',media_type='text/javascript')

@app.get('/personality.js')
def personality_script():return FileResponse(ROOT/'web/personality.js',media_type='text/javascript')

@app.get('/care.js')
def care_script():return FileResponse(ROOT/'web/care.js',media_type='text/javascript')

@app.get('/v1/dialogue/styles',dependencies=[Depends(guard)])
def dialogue_styles():return catalog()

@app.get('/v1/dialogue/preferences',dependencies=[Depends(guard)])
def dialogue_preferences(uid=Depends(member)):
    return app.state.memory.dialogue_preferences(uid)

@app.put('/v1/dialogue/preferences',dependencies=[Depends(guard)])
def save_dialogue_preferences(body:DialoguePreferences,uid=Depends(member)):
    with app.state.engine.lock:
        try:return app.state.memory.dialogue_preferences(uid,body.model_dump())
        except ValueError as e:raise HTTPException(403,str(e))

@app.get('/health',dependencies=[Depends(guard)])
def health():
    p=app.state.engine.predictor
    from dataclasses import asdict
    social=getattr(app.state,'social',None)
    return {'status':'ready','version':'5.2.0','process_id':os.getpid(),'profile':asdict(social.profile) if social else None,'dialogue_revision':'emotion-continuity-1','face_geometry_enabled':bool(social and social.geometry),'base':'Qwen3.5-2B','backend':p.backend,'trained_dialogue_adapter':p.model.dialogue_loaded,'vision':'YuNet + SFace + EmotiEffNet-B0 multi-task / CPU','body':'MediaPipe Pose Lite','memory':['working','episodic','semantic','extractive_summary','personal_baseline'],'memory_encrypted':True,'face_recognition_unlocks_private_memory':False,'physical_actuation':False,'field_validated':False,'vision_finetuned_here':False,'care':{'reminders':True,'proactive_opt_in':True,'urgent_text_fast_path':True,'automatic_emergency_calls':False,'clinical_validation':False},'robot_protocol':'home-companion/1'}

@app.get('/v1/members',dependencies=[Depends(guard)])
def members():return app.state.memory.profiles()

@app.post('/v1/members',dependencies=[Depends(guard)])
def register(body:Register):
    try:app.state.memory.register(body.user_id,body.display_name,body.pin,body.memory_consent)
    except ValueError as e:raise HTTPException(400,str(e))
    return {'user_id':body.user_id,'session_token':app.state.sessions.issue(body.user_id),'expires_in':3600}

@app.post('/v1/login',dependencies=[Depends(guard)])
def login(body:Login):
    app.state.sessions.attempt(body.user_id)
    if not app.state.memory.login(body.user_id,body.pin):raise HTTPException(401,'成员 ID 或 PIN 不正确')
    return {'user_id':body.user_id,'session_token':app.state.sessions.issue(body.user_id),'expires_in':3600,'memory_consent':app.state.memory.profile(body.user_id)['memory_consent']}

@app.post('/v1/logout',dependencies=[Depends(guard)])
def logout(uid=Depends(member)):
    if hasattr(app.state,'social'):app.state.social.clear(uid=uid)
    app.state.sessions.revoke(uid)
    with app.state.engine.lock:app.state.engine.sessions={k:v for k,v in app.state.engine.sessions.items() if k[1]!=uid}
    return {'logged_out':True}

@app.put('/v1/memory/consent',dependencies=[Depends(guard)])
def consent(body:Consent,uid=Depends(member)):
    with app.state.engine.lock:
        app.state.memory.consent(uid,body.memory_consent)
        if hasattr(app.state,'social'):app.state.social.clear(uid=uid)
        app.state.engine.sessions={k:v for k,v in app.state.engine.sessions.items() if k[1]!=uid}
    return {'memory_consent':body.memory_consent,'stored_memory_deleted':not body.memory_consent}

@app.get('/v1/memory',dependencies=[Depends(guard)])
def memories(q:str='',include_history:bool=False,uid=Depends(member)):
    if len(q)>600:raise HTTPException(400,'查询过长')
    return app.state.memory.search(uid,q,10) if q else app.state.memory.list(uid,include_history)

@app.post('/v1/memory',dependencies=[Depends(guard)])
def save(body:MemoryWrite,uid=Depends(member)):
    with app.state.engine.lock:
        profile=app.state.memory.profile(uid)
        if not profile or not profile['memory_consent']:raise HTTPException(403,'请先允许长期记忆')
        try:rid=app.state.memory.put(uid,**body.model_dump())
        except ValueError as e:raise HTTPException(400,str(e))
        # Corrections must not compete with stale working history.
        app.state.engine.sessions={k:v for k,v in app.state.engine.sessions.items() if k[1]!=uid}
    return {'id':rid,'saved':True}

@app.delete('/v1/memory/{record_id}',dependencies=[Depends(guard)])
def delete_memory(record_id:str,uid=Depends(member)):
    with app.state.engine.lock:
        if not app.state.memory.delete_record(uid,record_id):raise HTTPException(404,'未找到记忆')
        app.state.engine.sessions={k:v for k,v in app.state.engine.sessions.items() if k[1]!=uid}
    return {'deleted':True,'working_context_cleared':True}

@app.delete('/v1/memory',dependencies=[Depends(guard)])
def forget(uid=Depends(member)):
    if hasattr(app.state,'social'):app.state.social.clear(uid=uid)
    app.state.engine.forget(uid);return {'deleted':True,'face_registration_retained':True}

@app.delete('/v1/member',dependencies=[Depends(guard)])
def delete_member(uid=Depends(member)):
    with app.state.engine.lock:
        app.state.engine.forget(uid);app.state.memory.delete_profile(uid);app.state.sessions.revoke(uid)
        if hasattr(app.state,'social'):app.state.social.clear(uid=uid)
        with app.state.vision.lock:app.state.vision.streams.clear();app.state.vision.frames.clear()
    return {'deleted':True,'face_and_memory_deleted':True}

@app.post('/v1/vision/analyze',dependencies=[Depends(guard)])
def analyze(body:Frame,request:Request,x_member_session:str=Header(default='')):
    uid=app.state.sessions.resolve(x_member_session) if x_member_session else None
    owner=x_member_session or 'guest:'+request.state.guest_id
    try:
        if hasattr(app.state,'social'):return app.state.social.visual(body.image_base64,owner,body.camera_id,uid)
        return app.state.vision.analyze(body.image_base64,(owner,body.camera_id),owner)
    except ValueError as e:raise HTTPException(400,str(e))

@app.get('/v1/human-state',dependencies=[Depends(guard)])
def human_state(request:Request,session_id:str='default',x_member_session:str=Header(default='')):
    if len(session_id)>80:raise HTTPException(400,'会话名称过长')
    uid=app.state.sessions.resolve(x_member_session) if x_member_session else None
    owner=x_member_session or 'guest:'+request.state.guest_id
    return app.state.social.state(owner,session_id,None,uid).model_dump()

@app.get('/v1/user-model',dependencies=[Depends(guard)])
def user_model(uid=Depends(member)):return app.state.memory.user_model(uid)

@app.post('/v1/faces/enroll',dependencies=[Depends(guard)])
def enroll(body:Enrollment,uid=Depends(member)):
    with app.state.engine.lock:
        if not app.state.memory.profile(uid):raise HTTPException(401,'成员已删除')
        try:return app.state.vision.enroll(uid,body.images_base64)
        except ValueError as e:raise HTTPException(400,str(e))

@app.delete('/v1/faces',dependencies=[Depends(guard)])
def remove_face(uid=Depends(member)):
    with app.state.vision.lock:
        app.state.memory.delete_face(uid);app.state.vision.streams.clear();app.state.vision.frames.clear()
    return {'deleted':True}

@app.post('/v1/step',dependencies=[Depends(guard)])
def step(body:StepRequest,request:Request,x_member_session:str=Header(default='')):
    from .care import triage,fast_result
    # Explicit distress gets a local response even while another model turn is busy
    # or the member session expired. It does not expose any personal information.
    urgent=triage(body.observation.speech,body.observation.asr_confidence)
    if urgent:return fast_result(urgent)
    # Public conversation JSON can never confer controller authority.
    body=body.model_copy(update={'observation':body.observation.model_copy(update={
        'emergency_verified':False,'motion_authorized':False,'task_execution_authorized':False,
        'target_device':None,'confirmed_task_intent':None,'cloud_consent':False})})
    uid=app.state.sessions.resolve(x_member_session) if x_member_session else 'anonymous'
    profile=app.state.memory.profile(uid) if uid!='anonymous' else None
    trusted=body.observation.model_copy(update={'user_id':uid,'identity_verified':bool(profile),'memory_consent':bool(profile and profile['memory_consent'])})
    app.state.engine.care.note_speech(uid if profile else 'guest:'+request.state.guest_id,trusted.speech)
    care_event=app.state.engine.care.preflight(trusted)
    if care_event:return fast_result(care_event)
    with app.state.engine.lock:
        uid=app.state.sessions.resolve(x_member_session) if x_member_session else 'anonymous'
        profile=app.state.memory.profile(uid) if uid!='anonymous' else None
        # Never trust user_id / identity_verified / consent claimed in the JSON body.
        session_id=body.observation.session_id
        if uid=='anonymous':session_id=hashlib.sha256((request.state.guest_id+':'+session_id).encode()).hexdigest()
        observation=body.observation.model_copy(update={'user_id':uid,'session_id':session_id,'identity_verified':bool(profile),'memory_consent':bool(profile and profile['memory_consent']),'known_topics':[t for t in body.observation.known_topics if safe_text(t)]})
        visual=None
        if observation.visual_frame_id:
            try:visual=app.state.vision.frame(observation.visual_frame_id,x_member_session or 'guest:'+request.state.guest_id)
            except ValueError as e:raise HTTPException(400,str(e))
        preferences=body.dialogue_preferences.model_dump() if body.dialogue_preferences is not None else (app.state.memory.dialogue_preferences(uid) if profile and profile['memory_consent'] else {})
        source='current_selection' if body.dialogue_preferences is not None else ('saved_member' if preferences.get('mbti') or preferences.get('support','auto')!='auto' else 'default')
        try:
            social=getattr(app.state,'social',None)
            owner=x_member_session or 'guest:'+request.state.guest_id
            state=social.state(owner,body.observation.session_id,observation.speech,uid if profile else None,observation.audio_frame_id) if social else None
            result=app.state.engine.step(observation,visual,preferences,source,human_state=state)
            if social:
                if result.get('memory',{}).get('reason')=='explicit_forget_request':social.clear(uid=uid)
                else:social.buffer.record_action((owner,body.observation.session_id),result['response_plan']['response_strategy'])
            return result
        except ValueError as e:raise HTTPException(400,str(e))

from .scheduler import BusyError
from fastapi.responses import JSONResponse
@app.exception_handler(BusyError)
async def perception_busy(request,exc):return JSONResponse({'detail':'上一段感知尚未完成，请稍后重试。'},status_code=429)

@app.get('/v1/reminders',dependencies=[Depends(guard)])
def reminders(uid=Depends(member)):return app.state.memory.due(uid)

@app.post('/v1/reminders/{rid}/ack',dependencies=[Depends(guard)])
def ack(rid:int,uid=Depends(member)):
    item=app.state.engine.care.get(uid,rid)
    if item and item['repeat_seconds']:raise HTTPException(409,'重复提醒请通过带 occurrence 的陪护提醒接口确认')
    if not app.state.memory.acknowledge(uid,rid):raise HTTPException(404,'未找到提醒')
    return {'acknowledged':True}

from .robot import robot_guard
@app.post('/v1/robot/turn',dependencies=[Depends(guard),Depends(robot_guard)])
def robot_turn(body:StepRequest,request:Request,robot_id:str,x_member_session:str=Header(default='')):
    status=app.state.engine.robot.status(robot_id)
    if not status['online']:raise HTTPException(409,'请先发送机器人心跳')
    result=step(body,request,x_member_session)
    return {'turn':result,'output':app.state.engine.robot.envelope(robot_id,result)}
