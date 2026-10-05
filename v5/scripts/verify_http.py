"""Real GPU HTTP integration; temporary members are removed in finally."""
import base64,json,secrets,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];URL='http://127.0.0.1:8768'

def request(path,method='GET',body=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['X-Member-Session']=token
    req=urllib.request.Request(URL+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)

def main():
    evidence={'health':request('/health'),'turns':[]};tokens=[]
    uid='verification_'+secrets.token_hex(5)
    try:
        r=request('/v1/members','POST',{'user_id':uid,'display_name':'临时集成测试','pin':secrets.token_urlsafe(10),'memory_consent':True});token=r['session_token'];tokens.append(token)
        def step(speech,session,**fields):
            out=request('/v1/step','POST',{'observation':{'speech':speech,'session_id':session,**fields}},token)
            evidence['turns'].append({'speech':speech,'session':session,'response':out['response'],'memories':out['retrieved_memories'],'memory':out['memory'],'dialogue_status':out['dialogue']['status'],'latency_ms':out['latency_ms']});return out
        step('我叫小林。我的眼镜放在卧室抽屉。','first')
        out=step('我把眼镜放在哪里了？','second')
        assert '抽屉' in out['response'],out['response']
        step('我把眼镜移到了客厅书桌。','third')
        out=step('现在我的眼镜在哪里？','fourth')
        assert '书桌' in out['response'] and '抽屉' not in out['response'],out['response']
        request('/v1/memory','POST',{'kind':'preference','slot':'园艺爱好','text':'我喜欢在阳台养兰花，每天给花浇水。'},token)
        out=step('你记得我喜欢什么园艺活动吗？','fifth')
        assert any(term in out['response'] for term in ['兰花','养花','给花浇水','浇花']),out['response']
        # Public fixture is analyzed transiently, never used to enroll a real member.
        raw=(ROOT/'tests/assets/astronaut.png').read_bytes()
        visual=request('/v1/vision/analyze','POST',{'image_base64':base64.b64encode(raw).decode(),'camera_id':'integration'},token)
        evidence['visual']=visual
        out=step('看看我的表情','visual',visual_frame_id=visual['frame_id'])
        assert out['dialogue']['status']=='grounded_face_observation'
        assert '不一定' in out['response']
        stranger=request('/v1/members','POST',{'user_id':uid+'_other','display_name':'另一位临时成员','pin':secrets.token_urlsafe(10),'memory_consent':True})['session_token'];tokens.append(stranger)
        assert request('/v1/memory',token=stranger)==[]
        forged=request('/v1/step','POST',{'observation':{'user_id':uid,'identity_verified':True,'memory_consent':True,'speech':'眼镜在哪里？','session_id':uid+'_forged'}})
        assert not forged['retrieved_memories'] and not forged['memory_persisted']
        evidence['spoof_identity_rejected']=True
        out=step('请忘记我的眼镜位置','delete')
        assert out['dialogue']['status']=='memory_deletion_receipt'
        remaining=request('/v1/memory?include_history=true',token=token)
        assert not any('眼镜' in r['text'] for r in remaining)
        evidence['selective_forget_verified']=True
        request('/v1/memory/consent','PUT',{'memory_consent':False},token)
        assert request('/v1/memory?include_history=true',token=token)==[]
        evidence['consent_revocation_verified']=True
        evidence['passed']=True
    except Exception as e:
        evidence['passed']=False;evidence['error']=repr(e);raise
    finally:
        for token in tokens:
            try:request('/v1/member','DELETE',token=token)
            except Exception as e:evidence.setdefault('cleanup_errors',[]).append(repr(e))
        (ROOT/'reports/http_integration.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(evidence,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
