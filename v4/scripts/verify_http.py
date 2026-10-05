"""UTF-8 HTTP smoke against the actually running local service."""
import json,time,urllib.request,os,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    base='http://127.0.0.1:8767';session='http_verify_'+uuid.uuid4().hex;records=[]
    def call(path,payload=None,method=None):
        headers={'Content-Type':'application/json; charset=utf-8'}
        token=os.getenv('SOCIAL_API_TOKEN')
        if token:headers['Authorization']='Bearer '+token
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None
        request=urllib.request.Request(base+path,data=data,headers=headers,method=method)
        start=time.monotonic()
        with urllib.request.urlopen(request,timeout=120) as response:result=json.loads(response.read().decode('utf-8'))
        records.append({'path':path,'input':payload,'result':result,'seconds':time.monotonic()-start})
        return result
    health=call('/health');assert health['status']=='ready' and health['physical_base_models']==1 and not health['forecast_enabled']
    def step(speech,**kw):return call('/v1/step',{'observation':{'user_id':session,'session_id':session,'speech':speech,**kw}})
    a=step('我把眼镜放在卧室的书桌上了。')
    b=step('刚才我说眼镜在哪里？');assert '卧室' in b['response'] or '书桌' in b['response'],b
    c=step('我只想说说今天的烦心事，先不用给建议。');assert c['response']
    d=step('请先别打扰我');assert d['action']=='SILENCE' and not d['response']
    e=step('现在可以聊天了');assert e['boundary_state']=='open'
    f=step('帮我打开灯');assert not f['task']['authorized']
    g=step('打开客厅灯',task_execution_authorized=True,target_device='living_light',confirmed_task_intent='iot_hue_lighton')
    assert g['task']['authorized'] and g['task']['execution_status']=='not_executed'
    assert all(not x['result'].get('memory_persisted',False) for x in records)
    call('/v1/users/'+session,method='DELETE')
    result={'checks_passed':True,'base_url':base,'real_model_http_requests':True,'hardware_actuated':False,'records':records}
    (ROOT/'reports/http_smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks_passed':True,'context_reply':b['response'],'support_reply':c['response']},ensure_ascii=False))

if __name__=='__main__':main()
