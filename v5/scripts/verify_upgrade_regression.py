"""Separate pytest processes avoid legacy same-name test module collisions."""
import json,os,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/upgrade_20261001';rows=[]
OUT.mkdir(parents=True,exist_ok=True)
for name,path in [('v2','v2/tests'),('v4','v4/tests'),('v5','v5/tests')]:
 xml=OUT/('tests_'+name+'.xml')
 with (OUT/('tests_'+name+'.log')).open('w',encoding='utf-8') as log:
  r=subprocess.run([sys.executable,'-m','pytest',path,'-q','--junitxml='+str(xml)],cwd=ROOT.parent,env={**os.environ,'PYTHONUTF8':'1'},stdout=log,stderr=subprocess.STDOUT)
 suite=ET.parse(xml).getroot().find('testsuite')
 rows.append({'suite':name,'exit_code':r.returncode,**suite.attrib});print(name,rows[-1],flush=True)
(OUT/'test_summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
if any(r['exit_code'] for r in rows):raise SystemExit(1)

