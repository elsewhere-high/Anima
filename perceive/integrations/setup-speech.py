"""Prepare the authors' frozen acoustic checkpoint. No training or credentials."""
import hashlib
import json
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent
record = json.loads((root.parent / 'research/romana-disfluency-evidence.json').read_text())
target = root / 'models/romana-disfluency'
target.mkdir(parents=True, exist_ok=True)
for name, item in [('acoustic.pt', record['weights']), ('config.json', record['config'])]:
    path = target / name
    def digest(p):
        with p.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    if path.exists():
        if digest(path) != item['sha256']:
            raise RuntimeError(f'Existing file has a different hash: {name}; preserve and inspect it before replacing.')
    else:
        temporary = path.with_suffix(path.suffix + '.download')
        urllib.request.urlretrieve(item['source'], temporary)
        if digest(temporary) != item['sha256']:
            raise RuntimeError(f'Download hash mismatch for {name}; the provider may have returned a web page. See research/romana-disfluency-evidence.json.')
        temporary.replace(path)
    print(f'{name}: verified')
