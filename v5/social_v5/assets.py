"""Verify immutable model artifacts once per process before inference."""
import functools,hashlib,json
from . import ROOT
@functools.lru_cache(maxsize=16)
def checked_asset(name):
    path=ROOT/'models'/name
    rows=json.loads((ROOT/'models/social/manifest.json').read_text(encoding='utf-8'))
    row=next((r for r in rows if r['file']==name),None)
    if row is None:raise RuntimeError('Model missing from manifest: '+name)
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    if digest.hexdigest()!=row['sha256']:raise RuntimeError('Model checksum mismatch: '+name)
    return path
