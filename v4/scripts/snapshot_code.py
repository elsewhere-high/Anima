"""Retain the exact Python inputs beside a recorded experiment."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def snapshot(folder,paths):
    folder=Path(folder);out=folder/'source_snapshot';out.mkdir(exist_ok=True);records=[]
    for relative in paths:
        source=ROOT/relative;destination=out/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists() and destination.read_bytes()!=source.read_bytes():raise RuntimeError('Refusing to replace an experiment source snapshot')
        shutil.copyfile(source,destination);records.append({'path':relative,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    (out/'manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')

if __name__=='__main__':
    snapshot(ROOT/'runs/current_state_lora',['scripts/train_current_state.py','social_v4/state_model.py','scripts/build_state_data.py'])
