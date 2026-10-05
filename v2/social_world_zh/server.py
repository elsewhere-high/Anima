import os,secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Depends
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from .schema import StepRequest,ImagineRequest
from .memory import MemoryStore
from .engine import SocialEngine
from .spec import ROOT
security=HTTPBearer(auto_error=False)
def authorize(credentials:HTTPAuthorizationCredentials|None=Depends(security)):
    token=os.getenv('SOCIAL_API_TOKEN','')
    if token and (credentials is None or not secrets.compare_digest(credentials.credentials,token)):raise HTTPException(401,'Invalid bearer token')
@asynccontextmanager
async def lifespan(app):
    from .predictor import Predictor
    device=os.getenv('SOCIAL_DEVICE','cuda')
    memory=MemoryStore(os.getenv('SOCIAL_DB',str(ROOT/'data/runtime.sqlite')))
    app.state.engine=SocialEngine(Predictor(device),memory);app.state.device=device
    yield
    memory.db.close()
app=FastAPI(title='中文居家社会世界模型',version='2.0.0',lifespan=lifespan,dependencies=[Depends(authorize)])
@app.get('/health')
def health():return {'status':'ready','version':'2.0.0','base':'Qwen3.5-2B','device':app.state.device,'backend':app.state.engine.predictor.backend,'physical_actuation':False,'forecast_horizon':1,'transition_prior_loaded':app.state.engine.predictor.transition is not None}
@app.post('/v1/step')
def step(request:StepRequest):return app.state.engine.step(request.observation)
@app.post('/v1/imagine')
def imagine(request:ImagineRequest):return app.state.engine.imagine(request)
@app.delete('/v1/users/{user_id}')
def forget(user_id:str):app.state.engine.forget(user_id);return {'deleted':True}
@app.get('/v1/users/{user_id}/reminders')
def reminders(user_id:str):return app.state.engine.memory.due(user_id)
@app.post('/v1/users/{user_id}/reminders/{reminder_id}/ack')
def ack(user_id:str,reminder_id:int):
    if not app.state.engine.memory.acknowledge(user_id,reminder_id):raise HTTPException(404,'Reminder not found')
    return {'acknowledged':True}
