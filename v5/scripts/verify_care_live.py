"""Real HTTP/backend verification using one temporary, explicitly named test member."""
import json,secrets,time,urllib.request,urllib.error
from pathlib import Path
BASE='http://127.0.0.1:8768';headers={};report={'checks':[],'samples':[]}
def call(path,data=None,method=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,headers={'Content-Type':'application/json',**headers},method=method)
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def check(ok,name):
    if not ok:raise AssertionError(name)
    report['checks'].append(name)
uid='care_live_'+secrets.token_hex(5)
try:
    health=call('/health');check(health['version']=='5.2.0','running V5.2');report['health']=health
    user=call('/v1/members',{'user_id':uid,'display_name':'陪护联调测试','pin':secrets.token_urlsafe(16),'memory_consent':True});headers['X-Member-Session']=user['session_token']
    for speech in ['我喘不过气了','这个药能吃几片？','五分钟后提醒我给花浇水','一个人在家有点孤单，不想听大道理，你陪我说会儿话吧。','刚才我说的是什么？']:
        started=time.monotonic();r=call('/v1/step',{'observation':{'speech':speech,'session_id':'care-live'}});elapsed=time.monotonic()-started
        report['samples'].append({'speech':speech,'response':r['response'],'seconds':round(elapsed,3),'care':r.get('care',{}).get('kind'),'motion_authorized':r['motion']['authorized']})
        check(not r['motion']['authorized'] and not r['task']['authorized'],'no hardware authority: '+speech)
        if speech=='我喘不过气了':check(elapsed<1 and r['care']['priority']=='urgent' and not r['care']['human_contact_sent'],'urgent response before LLM')
    item=call('/v1/care/reminders',{'text':'这是联调提醒','delay_seconds':1,'request_id':'live-delivery-test'})
    time.sleep(1.1)
    due=call('/v1/care/poll',{'person_present':False});check(any(x['id']==item['id'] for x in due['reminders']),'due reminder visible without marking done')
    repeat=call('/v1/care/poll',{'person_present':False});check(any(x['id']==item['id'] for x in repeat['reminders']),'unacknowledged reminder retained')
    call(f"/v1/care/reminders/{item['id']}/resolve",{'action':'ack','occurrence':item['occurrence']})
    check(not any(x['id']==item['id'] for x in call('/v1/care/reminders')),'acknowledged reminder removed from pending')
finally:
    if headers:
        call('/v1/member',method='DELETE');report['checks'].append('temporary test member deleted')
    path=Path(__file__).resolve().parents[1]/'reports/care_live.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
