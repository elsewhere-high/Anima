"""Vendor-neutral, output-only robot contract with a heartbeat watchdog.

This module deliberately never converts conversation into motor/device calls.
A vendor adapter must enforce its own hardware emergency stop independently.
"""
import os,secrets,threading,time
from pydantic import BaseModel,ConfigDict,Field
from fastapi import APIRouter,Depends,HTTPException,Request

class Heartbeat(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    robot_id:str=Field(min_length=1,max_length=60,pattern=r'^[\w.-]+$')
    emergency_stop:bool=True
    battery_percent:float|None=Field(default=None,ge=0,le=100)
    speaker_ready:bool=False
    display_ready:bool=True

class RobotGateway:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.lock=threading.RLock();self.robots={}
    def heartbeat(self,value):
        with self.lock:
            self.robots={k:v for k,v in self.robots.items() if self.clock()-v['received']<60}
            if len(self.robots)>=16 and value['robot_id'] not in self.robots:raise ValueError('机器人连接已达上限')
            self.robots[value['robot_id']]={**value,'received':self.clock()};return self.status(value['robot_id'])
    def status(self,robot_id):
        with self.lock:
            r=self.robots.get(robot_id);age=self.clock()-r['received'] if r else None
            online=bool(r and age<=6);stop=not online or r['emergency_stop'] or (r['battery_percent'] is not None and r['battery_percent']<10)
            return {'robot_id':robot_id,'online':online,'heartbeat_age_seconds':age,'hold_required':stop,'motion_enabled':False,'physical_integration_verified':False,'speaker_ready':bool(online and r['speaker_ready']),'display_ready':bool(online and r['display_ready']), 'reason':'offline' if not online else 'emergency_stop' if r['emergency_stop'] else 'low_battery' if stop else 'output_only_ready'}
    def envelope(self,robot_id,result):
        state=self.status(robot_id)
        return {'protocol':'home-companion/1','event_id':secrets.token_hex(12),'created_unix':time.time(),'expires_after_ms':5000,
                'robot':state,'motion':{'command':'HOLD','authorized':False},'outputs':{'display':result['response'] if state['display_ready'] else '', 'speak':result['response'] if state['speaker_ready'] and not state['hold_required'] else ''},'care':result.get('care'), 'human_contact_sent':False}

def robot_guard(request:Request):
    key=os.getenv('SOCIAL_ROBOT_TOKEN','')
    if len(key)<24:raise HTTPException(503,'尚未配置机器人接入密钥（至少 24 字符）')
    if not secrets.compare_digest(request.headers.get('X-Robot-Token',''),key):raise HTTPException(401,'机器人接入密钥无效')

def router(guard):
    r=APIRouter(prefix='/v1/robot',dependencies=[Depends(guard),Depends(robot_guard)])
    @r.get('/capabilities')
    def capabilities():return {'protocol':'home-companion/1','outputs':['display','speak'],'motion_enabled':False,'calling_enabled':False,'watchdog_seconds':6,'required':['independent_hardware_estop','vendor_adapter','member_login_for_private_data']}
    @r.post('/heartbeat')
    def heartbeat(body:Heartbeat,request:Request):
        try:return request.app.state.engine.robot.heartbeat(body.model_dump())
        except ValueError as e:raise HTTPException(429,str(e))
    @r.get('/status/{robot_id}')
    def status(robot_id:str,request:Request):return request.app.state.engine.robot.status(robot_id)
    return r
