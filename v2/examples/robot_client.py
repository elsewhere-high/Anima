"""Run after start_gpu.cmd. A real controller replaces Simulator.submit."""
import sys,json,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from social_world_zh.adapter import command_from_decision,Simulator
token=os.getenv('SOCIAL_API_TOKEN','');headers={'Authorization':'Bearer '+token} if token else {}
base=os.getenv('SOCIAL_URL','http://127.0.0.1:8766');controller=Simulator()
with httpx.Client(base_url=base,headers=headers,timeout=90) as client:
    for speech in ['你好，小助手','先别打扰我','嗯','现在可以聊天了','帮我打开客厅灯']:
        observation={'session_id':'robot_demo','user_id':'demo','speech':speech,'identity_verified':False,'memory_consent':False}
        decision=client.post('/v1/step',json={'observation':observation});decision.raise_for_status();decision=decision.json()
        command=command_from_decision(decision);ack=controller.submit(command)
        print(json.dumps({'speech':speech,'action':decision['action'],'reply':decision['response'],'controller_ack':ack},ensure_ascii=False,indent=2))
    confirmed={'session_id':'confirmed_device_demo','speech':'帮我打开客厅灯','task_execution_authorized':True,'target_device':'living_light','confirmed_task_intent':'iot_hue_lighton'}
    response=client.post('/v1/step',json={'observation':confirmed});response.raise_for_status();decision=response.json()
    command=command_from_decision(decision);ack=controller.submit(command)
    print(json.dumps({'confirmed_device_example':True,'task':decision['task'],'command':command,'controller_ack':ack,'simulated_devices':controller.devices},ensure_ascii=False,indent=2))
    prediction=client.post('/v1/imagine',json={'speech':'今天工作不顺心，挺难过的','candidates':['听起来你很难受，我可以听你说。','这有什么好难过的。']});prediction.raise_for_status()
    print(json.dumps(prediction.json(),ensure_ascii=False,indent=2))
