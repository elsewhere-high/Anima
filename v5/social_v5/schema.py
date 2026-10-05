from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from social_world_zh.schema import Observation as OriginalObservation

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class Observation(OriginalObservation):
    visual_frame_id:str|None=Field(default=None,max_length=100)
    audio_frame_id:str|None=Field(default=None,max_length=100)

class DialoguePreferences(Strict):
    mbti:str|None=Field(default=None,pattern=r'^[EI][SN][TF][JP]$')
    support:Literal['auto','listen','analyze','explore']='auto'

class StepRequest(Strict):
    observation:Observation
    dialogue_preferences:DialoguePreferences|None=None

class Register(Strict):
    user_id:str=Field(min_length=1,max_length=60,pattern=r'^[\w.-]+$')
    display_name:str=Field(min_length=1,max_length=30)
    pin:str=Field(min_length=6,max_length=64)
    memory_consent:bool=False

class Login(Strict):
    user_id:str=Field(min_length=1,max_length=60)
    pin:str=Field(min_length=6,max_length=64)

class Consent(Strict):
    memory_consent:bool

class Frame(Strict):
    image_base64:str=Field(min_length=20,max_length=5500000)
    camera_id:str=Field(default='local',min_length=1,max_length=60,pattern=r'^[\w.-]+$')

class Enrollment(Strict):
    images_base64:list[str]=Field(min_length=3,max_length=6)
    biometric_consent:Literal[True]

class MemoryWrite(Strict):
    kind:Literal['fact','preference','event']='fact'
    slot:str=Field(min_length=1,max_length=80)
    text:str=Field(min_length=1,max_length=300)
    ttl_days:int|None=Field(default=None,ge=1,le=3650)
    importance:float=Field(default=.7,ge=0,le=1)
    preserve_expiry:bool=False
