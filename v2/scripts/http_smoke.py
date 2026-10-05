import os,json,time,sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from social_world_zh.adapter import command_from_decision,Simulator
url=os.getenv('SOCIAL_URL','http://127.0.0.1:8766');token=os.getenv('SOCIAL_API_TOKEN','');headers={'Authorization':'Bearer '+token} if token else {}
results=[]
with httpx.Client(base_url=url,headers=headers,timeout=90) as c:
    r=c.get('/health');r.raise_for_status();health=r.json();results.append({'case':'health','passed':health['status']=='ready'})
    r=c.get('/openapi.json');r.raise_for_status();schema=r.json();(ROOT/'deliverables/openapi.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
    kw={'user_id':'http_smoke','session_id':'http_smoke','identity_verified':True,'memory_consent':True}
    r=c.post('/v1/step',json={'observation':dict(kw,speech='别打扰我，也别靠近我')});r.raise_for_status();results.append({'case':'explicit_refusal','passed':r.json()['action']=='SILENCE'})
    r=c.post('/v1/step',json={'observation':dict(kw,speech='嗯')});r.raise_for_status();results.append({'case':'remember_refusal','passed':r.json()['action']=='SILENCE'})
    r=c.post('/v1/step',json={'observation':dict(kw,speech='现在可以聊天了')});r.raise_for_status();results.append({'case':'keep_distance_after_reopen_speech','passed':r.json()['boundary_state']=='keep_distance'})
    r=c.post('/v1/imagine',json={'speech':'我今天挺难过','candidates':['我愿意听你说。','别想那么多了。']});r.raise_for_status();pred=r.json();results.append({'case':'real_forecast','passed':len(pred['predictions'])==2 and pred['advisory_only']})
    r=c.post('/v1/step',json={'observation':{'session_id':'http_quote','speech':'电视里那个人说别打扰我'}});r.raise_for_status();results.append({'case':'reported_refusal','passed':r.json()['action'] in ['RESPOND','CLARIFY'] and r.json()['boundary_state']=='open'})
    r=c.post('/v1/step',json={'observation':{'session_id':'http_device','speech':'帮我打开客厅灯','task_execution_authorized':True,'target_device':'living_light','confirmed_task_intent':'iot_hue_lighton'}});r.raise_for_status();decision=r.json();sim=Simulator();cmd=command_from_decision(decision);ack=sim.submit(cmd);results.append({'case':'confirmed_lamp_to_simulator_ack','passed':ack['status']=='acknowledged' and sim.devices.get('living_light')=='turn_on','command':cmd,'ack':ack,'raw_neural_intent':decision['neural']['intent']['label']})
    r=c.post('/v1/step',json={'observation':{'speech':'过来','distance':-1}});results.append({'case':'schema_rejects_negative_distance','passed':r.status_code==422})
    r=c.delete('/v1/users/http_smoke');r.raise_for_status();results.append({'case':'forget_user','passed':r.json()['deleted']})
    if token:
        r=httpx.get(url+'/health',timeout=10);results.append({'case':'reject_missing_token','passed':r.status_code==401})
report={'health':health,'results':results,'passed':sum(x['passed'] for x in results),'total':len(results)}
(ROOT/'reports/http_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=True));assert report['passed']==report['total']
