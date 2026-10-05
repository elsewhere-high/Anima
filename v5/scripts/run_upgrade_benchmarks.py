"""Sequential fresh processes prevent candidate/profile CPU and GPU contention."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/upgrade_20261001'
env={**os.environ,'PYTHONUTF8':'1'}
jobs=[('emotion2vec',[str(ROOT/'scripts/benchmark_emotion2vec.py')])]
jobs += [(name,[str(ROOT/'scripts/benchmark_social.py'),name,'--n','25' if 'face' in name or name=='pose' else '10']) for name in ['old_face','new_face','pose','whisper','sensevoice']]
jobs += [('profile_'+name,[str(ROOT/'scripts/benchmark_profiles.py'),name,'--n','7']) for name in ['old','ultra_light','balanced','best_edge']]
for name,args in jobs:
 print('START',name,flush=True)
 with (OUT/(name+'.log')).open('w',encoding='utf-8') as f:
  result=subprocess.run([sys.executable,*args],stdout=f,stderr=subprocess.STDOUT,env=env)
 print('END',name,result.returncode,flush=True)
 if result.returncode:raise SystemExit(result.returncode)
