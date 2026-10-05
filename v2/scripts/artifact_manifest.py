"""Produce and verify deployment file hashes without including environments/tools."""
import sys,json,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');a=p.parse_args();manifest=ROOT/'deliverables/artifact_manifest.json'
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
if a.verify:
    rows=json.loads(manifest.read_text(encoding='utf-8'))['files'];errors=[]
    for r in rows:
        path=ROOT/r['path']
        if not path.exists() or digest(path)!=r['sha256']:errors.append(r['path'])
    print(json.dumps({'checked':len(rows),'errors':errors}));sys.exit(bool(errors))
paths=[]
for folder in ['social_world_zh','scripts','tests','examples','models/qwen35_2B','models/social_zh/best','data/processed']:
    paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.cache' not in p.parts)
for file in ['models/social_zh/cpu_int8.pt','models/social_zh/transition_prior.npz','models/social_zh/transition_config.json','reports/calibration.json','README.md','THIRD_PARTY_NOTICES.md','requirements.txt','requirements.lock.txt','start_gpu.cmd','start_gpu.ps1','start_cpu.cmd','start_cpu.ps1','data/provenance.json','data/massive_features.json','data/processed/manifest.json']:
    paths.append(ROOT/file)
paths.extend(p for p in (ROOT/'deliverables').glob('*') if p.is_file() and p.name!='artifact_manifest.json')
paths.extend(p for p in (ROOT/'reports').glob('*') if p.is_file() and p.suffix in {'.json','.jsonl','.npz','.log','.png','.md'})
rows=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(set(paths))]
manifest.write_text(json.dumps({'version':'2.0.0','note':'Hashes verify this local delivery. Model licenses and data provenance remain separate. Runtime environments and document-rendering tools are excluded.','files':rows},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'files':len(rows),'total_bytes':sum(r['bytes'] for r in rows)}))
