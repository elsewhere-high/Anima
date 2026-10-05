from datetime import datetime
from typing import Literal
from pydantic import Field,model_validator
from fastapi import APIRouter,Depends,HTTPException,Request
from .schema import Strict

class CareSettings(Strict):
    proactive_enabled:bool=False
    interval_minutes:int=Field(default=60,ge=30,le=240)
    quiet_start:int=Field(default=22,ge=0,le=23)
    quiet_end:int=Field(default=8,ge=0,le=23)
    utc_offset_minutes:int=Field(default=480,ge=-720,le=840)

class Reminder(Strict):
    text:str=Field(min_length=1,max_length=200)
    delay_seconds:int|None=Field(default=None,ge=1,le=31536000)
    due_at:datetime|None=None
    request_id:str=Field(min_length=8,max_length=80,pattern=r'^[\w.-]+$')
    repeat:Literal['once','daily']='once'
    kind:Literal['general','medication']='general'
    @model_validator(mode='after')
    def time_source(self):
        if (self.delay_seconds is None)==(self.due_at is None):raise ValueError('请选择倒计时或明确时间之一')
        if self.due_at is not None and self.due_at.utcoffset() is None:raise ValueError('时间必须带时区')
        return self

class Resolve(Strict):
    action:Literal['ack','snooze','cancel']
    occurrence:str=Field(min_length=1,max_length=80)
    minutes:int=Field(default=10,ge=1,le=1440)

class Poll(Strict):
    person_present:bool=False
    interaction_busy:bool=False

def router(guard,member):
    r=APIRouter(prefix='/v1/care',dependencies=[Depends(guard)])
    def care(request):return request.app.state.engine.care
    @r.get('/settings')
    def settings(request:Request,uid=Depends(member)):return care(request).settings(uid)
    @r.put('/settings')
    def put_settings(body:CareSettings,request:Request,uid=Depends(member)):
        try:return care(request).settings(uid,body.model_dump())
        except ValueError as e:raise HTTPException(403,str(e))
    @r.get('/reminders')
    def reminders(request:Request,uid=Depends(member)):return care(request).reminders(uid)
    @r.post('/reminders')
    def create(body:Reminder,request:Request,uid=Depends(member)):
        service=care(request);due=body.due_at.timestamp() if body.due_at else service.clock()+body.delay_seconds
        try:return service.add(uid,body.text,due,body.request_id,86400 if body.repeat=='daily' else 0,body.kind)
        except ValueError as e:raise HTTPException(400,str(e))
    @r.post('/reminders/{rid}/resolve')
    def resolve(rid:int,body:Resolve,request:Request,uid=Depends(member)):
        result=care(request).resolve(uid,rid,body.action,body.occurrence,body.minutes)
        if not result:raise HTTPException(404,'未找到属于你的提醒')
        if result['status']=='stale_occurrence':raise HTTPException(409,'提醒时间已变化，请刷新后重试')
        return result
    @r.post('/poll')
    def poll(body:Poll,request:Request,uid=Depends(member)):return care(request).poll(uid,body.person_present,body.interaction_busy)
    return r
