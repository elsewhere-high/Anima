"""Download only the pinned public inference weights. No training or cloud provisioning."""
import hashlib,json,os
import urllib.request
from pathlib import Path
os.environ.setdefault("HF_HUB_DISABLE_XET","1")
from huggingface_hub import hf_hub_download
ROOT=Path(__file__).resolve().parent
lock=json.loads((ROOT/"models.lock.json").read_text())
for download in lock.get("downloads",[]):
    destination=ROOT/"models"/download["path"]
    if not destination.is_file():
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix(".download")
        urllib.request.urlretrieve(download["url"],temporary)
        with temporary.open("rb") as stream:
            if hashlib.file_digest(stream,"sha256").hexdigest()!=download["sha256"]:
                raise RuntimeError("Model integrity mismatch: "+download["path"])
        temporary.rename(destination)
    with destination.open("rb") as stream:
        if hashlib.file_digest(stream,"sha256").hexdigest()!=download["sha256"]:
            raise RuntimeError("Model integrity mismatch: "+download["path"])
    print(download["path"]+" verified",flush=True)
for model in lock["models"]:
    for filename,expected in model["files"].items():
        destination=ROOT/"models"/model["directory"]/filename
        if not destination.is_file():
            hf_hub_download(model["id"],filename,revision=model["revision"],local_dir=destination.parent)
        with destination.open("rb") as stream:
            actual=hashlib.file_digest(stream,"sha256").hexdigest()
        if actual!=expected:
            raise RuntimeError("Model integrity mismatch: "+model["directory"]+"/"+filename)
        print(model["directory"]+"/"+filename+" verified",flush=True)
