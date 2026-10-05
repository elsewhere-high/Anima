"""Hash V4 evidence and the local dependencies required for inference/reproduction."""
import sys,json,hashlib,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parent

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    target=ROOT/'deliverables/artifact_manifest.json'
    if '--verify' in sys.argv:
        manifest=json.loads(target.read_text(encoding='utf-8'));errors=[]
        for row in manifest['files']:
            path=(PROJECT/row['path']).resolve()
            if not path.is_relative_to(PROJECT.resolve()) or not path.is_file() or path.stat().st_size!=row['bytes'] or digest(path)!=row['sha256']:errors.append(row['path'])
        print(json.dumps({'checked':len(manifest['files']),'errors':errors},ensure_ascii=False))
        if errors:raise SystemExit(1)
        return
    if not (ROOT/'reports/runtime_cuda.json').exists():raise RuntimeError('Complete real-model verification first')
    candidates=list(ROOT.rglob('*'))
    for folder in ['v2/models/qwen35_2B','v2/models/social_zh/best','v2/social_world_zh','v3/social_v3']:
        candidates.extend((PROJECT/folder).rglob('*'))
    candidates.extend(PROJECT/path for path in ['start_v4_gpu.ps1','start_v4_cpu.ps1','stop_v4.ps1','v2/reports/calibration.json','v2/THIRD_PARTY_NOTICES.md','v3/scripts/evaluate.py'])
    files=[]
    for path in sorted(set(candidates)):
        if not path.is_file() or path==target or any(p in ['__pycache__','.pytest_cache'] for p in path.parts):continue
        if path.name.startswith('server_') or path.name.endswith(('.sqlite','.sqlite-wal','.sqlite-shm')):continue
        files.append({'path':path.relative_to(PROJECT).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)})
    result={'version':4,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'root':'project root, parent of v4','files':files,'n':len(files),'total_bytes':sum(r['bytes'] for r in files),'excluded':'Mutable runtime database, serving logs, Python caches and this self-referential manifest. Training/evaluation logs are included.'}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:result[k] for k in ['n','total_bytes']}))

if __name__=='__main__':main()
