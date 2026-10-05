"""Fetch THCHS-30 noise recordings, extracting only explicit WAV basenames."""
import hashlib
import io
import json
import tarfile
from prepare_speech_training import get, ROOT, REPORT


def main():
    url='https://openslr.elda.org/resources/18/resource.tgz'
    folder=ROOT/'data/speech_noise'
    raw=get(url,folder/'resource.tgz')
    receipts=[]
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        for basename in ['car.wav','cafe.wav','white.wav']:
            members=[m for m in archive.getmembers() if m.isfile() and m.name.rsplit('/',1)[-1]==basename]
            if len(members)!=1:raise ValueError('Expected one file: '+basename)
            data=archive.extractfile(members[0]).read()
            (folder/basename).write_bytes(data)
            receipts.append({'file':basename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    report={'source':url,'license':'Apache-2.0 per https://www.openslr.org/18/','archive_sha256':hashlib.sha256(raw).hexdigest(),'files':receipts}
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'noise_downloads.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
