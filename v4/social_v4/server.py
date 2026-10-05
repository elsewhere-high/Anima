import os, secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .runtime_model import ROOT
from social_world_zh.schema import StepRequest
from social_world_zh.memory import MemoryStore
from .engine import SocialEngine

security = HTTPBearer(auto_error=False)


def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    token = os.getenv('SOCIAL_API_TOKEN', '')
    if token and (credentials is None or not secrets.compare_digest(credentials.credentials, token)):
        raise HTTPException(401, 'Invalid bearer token')


@asynccontextmanager
async def lifespan(app):
    from .predictor import Predictor
    memory = MemoryStore(os.getenv('SOCIAL_DB', str(ROOT / 'data/runtime.sqlite')))
    try:
        app.state.engine = SocialEngine(Predictor(os.getenv('SOCIAL_DEVICE', 'cuda')), memory)
        yield
    finally:
        memory.db.close()


app = FastAPI(title='中文居家社会交互模型', version='4.0.0', lifespan=lifespan, dependencies=[Depends(authorize)])


@app.get('/health')
def health():
    p = app.state.engine.predictor
    return {'status': 'ready', 'version': '4.0.0', 'base': 'Qwen3.5-2B', 'backend': p.backend, 'physical_base_models': 1, 'physical_actuation': False, 'forecast_enabled': False, 'trained_current_heads': p.accepted_heads, 'dialogue_adapter_loaded': p.model.dialogue_loaded, 'quality_profile':'cpu_experimental_quantization' if p.device=='cpu' else 'gpu_public_data_evaluated', 'field_validated':False}


@app.post('/v1/step')
def step(request: StepRequest): return app.state.engine.step(request.observation)


@app.delete('/v1/users/{user_id}')
def forget(user_id: str):
    app.state.engine.forget(user_id)
    return {'deleted': True}


@app.get('/v1/users/{user_id}/reminders')
def reminders(user_id: str): return app.state.engine.memory.due(user_id)


@app.post('/v1/users/{user_id}/reminders/{reminder_id}/ack')
def ack(user_id: str, reminder_id: int):
    if not app.state.engine.memory.acknowledge(user_id, reminder_id): raise HTTPException(404, 'Reminder not found')
    return {'acknowledged': True}
