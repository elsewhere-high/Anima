"""Restart the managed local service and prove encrypted long-term recall survives."""
import json,secrets,subprocess,time
from pathlib import Path
from verify_http import request
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parent

def main():
    uid='restart_'+secrets.token_hex(5);pin=secrets.token_urlsafe(16);token=None
    result={'scope':'actual managed service restart; temporary member only'}
    try:
        token=request('/v1/members','POST',{'user_id':uid,'display_name':'临时重启测试','pin':pin,'memory_consent':True})['session_token']
        request('/v1/memory','POST',{'kind':'fact','slot':'公园散步时间','text':'我每周三下午去公园散步。'},token)
        for script in ['stop_v5.ps1','v5/start_background.ps1']:
            # A background Windows descendant can inherit captured pipe handles
            # and keep communicate() blocked after PowerShell exits. No pipes.
            subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(PROJECT/script)],cwd=PROJECT,check=True,timeout=30,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        started=time.monotonic()
        while time.monotonic()-started<180:
            try:
                health=request('/health')
                if health['status']=='ready':break
            except Exception:pass
            time.sleep(1)
        else:raise RuntimeError('Server did not become ready after restart')
        result['startup_seconds']=time.monotonic()-started
        token=request('/v1/login','POST',{'user_id':uid,'pin':pin})['session_token']
        records=request('/v1/memory',token=token)
        assert any('周三' in r['text'] for r in records)
        result['encrypted_records_survived']=True
        out=request('/v1/step','POST',{'observation':{'session_id':'after-restart','speech':'我每周几去公园散步？'}},token)
        result.update(response=out['response'],retrieved=out['retrieved_memories'],latency_ms=out['latency_ms'],working_history_turns_used=out['dialogue']['history_turns_used'])
        assert '周三' in out['response'],out['response']
        assert out['dialogue']['history_turns_used']==0
        result['passed']=True
    except Exception as e:result.update(passed=False,error=repr(e));raise
    finally:
        if token:
            try:request('/v1/member','DELETE',token=token)
            except Exception as e:result['cleanup_error']=repr(e)
        (ROOT/'reports/restart.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
