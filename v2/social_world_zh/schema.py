from typing import Literal,Annotated
from pydantic import BaseModel,Field,ConfigDict

class Observation(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    user_id:str=Field(default='anonymous',min_length=1,max_length=80,pattern=r'^[\w.-]+$')
    session_id:str=Field(default='default',min_length=1,max_length=80,pattern=r'^[\w.-]+$')
    speech:str=Field(default='',max_length=600)
    person_present:bool=True
    identity_verified:bool=False
    memory_consent:bool=False
    gaze:Literal['toward','away','unknown']='unknown'
    distance:float=Field(default=1.5,ge=0,le=100)
    pose:Literal['sitting','standing','lying','unknown']='unknown'
    movement:Literal['low','normal','high','unknown']='unknown'
    voice_arousal:Literal['low','normal','high','unknown']='unknown'
    current_task:str=Field(default='conversation',max_length=80)
    current_goal:str=Field(default='',max_length=120)
    last_action:str=Field(default='WAIT',max_length=30)
    emergency_verified:bool=False
    motion_authorized:bool=False
    boundary:Literal['open','do_not_disturb','keep_distance']|None=None
    preferred_distance:float|None=Field(default=None,ge=.5,le=5)
    preferred_style:Literal['neutral','warm','gentle','brief','silent']|None=None
    relationship_level:Literal['unknown','first_contact','acquaintance','familiar','trusted']|None=None
    known_topics:list[Annotated[str,Field(max_length=80)]]=Field(default_factory=list,max_length=10)
    positive_feedback:bool|None=None
    memory_note:str|None=Field(default=None,max_length=200)
    reminder_after_seconds:int|None=Field(default=None,ge=1,le=31536000)
    reminder_text:str|None=Field(default=None,max_length=200)
    cloud_consent:bool=False
    task_execution_authorized:bool=False
    asr_confidence:float=Field(default=1.0,ge=0,le=1)
    local_reasoning:bool=False
    target_device:str|None=Field(default=None,max_length=80,pattern=r'^[\w.-]+$')
    confirmed_task_intent:str|None=Field(default=None,max_length=60)

class StepRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    observation:Observation

class ImagineRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    speech:str=Field(min_length=1,max_length=600)
    history:list[tuple[Literal['用户','对方'],Annotated[str,Field(max_length=600)]]]=Field(default_factory=list,max_length=4)
    candidates:list[Annotated[str,Field(min_length=1,max_length=200)]]=Field(min_length=1,max_length=6)
