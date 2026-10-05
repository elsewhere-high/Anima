"""Launch an authenticated, real-model service, test HTTP, then stop our process tree."""
import os,sys,time,secrets,subprocess,argparse
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--launcher',action='store_true');args=p.parse_args()
env=os.environ.copy();env.update(SOCIAL_DEVICE='cuda',SOCIAL_API_TOKEN=secrets.token_urlsafe(24),SOCIAL_DB=str(ROOT/'reports/http_smoke.sqlite'),PYTHONUTF8='1')
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
with (ROOT/'reports/http_server.log').open('w',encoding='utf-8') as log:
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT.parent/'start_gpu.ps1')] if args.launcher else [sys.executable,'-m','uvicorn','social_world_zh.server:app','--host','127.0.0.1','--port','8766','--workers','1']
    process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
    try:
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Server exited before readiness; inspect http_server.log')
            try:
                r=httpx.get('http://127.0.0.1:8766/health',headers={'Authorization':'Bearer '+env['SOCIAL_API_TOKEN']},timeout=2)
                if r.status_code==200 and r.json().get('version')=='2.0.0':break
            except httpx.HTTPError:pass
            time.sleep(1)
        else:raise TimeoutError('Server readiness timed out')
        subprocess.run([sys.executable,'scripts/http_smoke.py'],cwd=ROOT,env=env,check=True,creationflags=flags)
        if args.launcher:
            with (ROOT/'reports/robot_client_demo.log').open('w',encoding='utf-8') as demo:
                subprocess.run([sys.executable,'examples/robot_client.py'],cwd=ROOT,env=env,stdout=demo,stderr=demo,check=True,creationflags=flags)
    finally:
        if process.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,check=False)
            else:process.terminate()
            process.wait(timeout=15)
print('Real authenticated HTTP checks complete; test server stopped')
