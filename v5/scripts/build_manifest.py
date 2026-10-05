import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parent;TARGET=ROOT/'deliverables/artifact_manifest.json'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if '--verify' in sys.argv:
    m=json.loads(TARGET.read_text(encoding='utf-8'));errors=[]
    for r in m['files']:
        p=(PROJECT/r['path']).resolve()
        if not p.is_relative_to(PROJECT.resolve()) or not p.is_file() or digest(p)!=r['sha256']:errors.append(r['path'])
    print(json.dumps({'checked':len(m['files']),'errors':errors}));raise SystemExit(bool(errors))
paths=list(ROOT.rglob('*'))+[PROJECT/p for p in ['start_v5.ps1','stop_v5.ps1','启动体验.cmd','PRODUCT.md','DESIGN.md','.impeccable/design.json','v4/models/release.json']]
rows=[]
for p in sorted(paths):
    if not p.is_file() or p==TARGET or any(x in p.parts for x in ['private','__pycache__','.cache','.pytest_cache']) or p.name.startswith('server_'):continue
    rows.append({'path':p.relative_to(PROJECT).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)})
TARGET.parent.mkdir(exist_ok=True)
TARGET.write_text(json.dumps({'version':5,'files':rows,'excluded':'Private runtime database and key, mutable server logs, Python/HF caches. V4 weights remain bound by v4/deliverables/artifact_manifest.json.','count':len(rows)},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'files':len(rows),'bytes':sum(r['bytes'] for r in rows)}))
