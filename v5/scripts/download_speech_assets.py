"""Pinned upstream training weights and Silero VAD, with source/hash receipts."""
import hashlib,json,concurrent.futures
from pathlib import Path
from prepare_speech_training import get,ROOT,REPORT

def main():
    repo='FunAudioLLM/SenseVoiceSmall';folder=ROOT/'models/sensevoice_train'
    revision='3847d57b6bdf2dd8875cb1508d2af43d80a16bf7'
    meta=json.loads(get('https://huggingface.co/api/models/'+repo+'/revision/'+revision,folder/'repository.json'))
    assert meta['sha']==revision, 'Unexpected cached model revision'
    files=['config.yaml','configuration.json','am.mvn','chn_jpn_yue_eng_ko_spectok.bpe.model','model.pt','README.md']
    jobs=[(f'https://huggingface.co/{repo}/resolve/{revision}/{f}',folder/f) for f in files]
    vadrev='1e261b036686cd0017d500ee96acd1c4ba572a9d'
    jobs.extend((f'https://raw.githubusercontent.com/snakers4/silero-vad/{vadrev}/{src}',ROOT/'models/vad'/dest) for src,dest in [('src/silero_vad/data/silero_vad.onnx','silero_vad.onnx'),('LICENSE','LICENSE'),('src/silero_vad/utils_vad.py','upstream_utils_vad.py')])
    jobs.append(('https://raw.githubusercontent.com/modelscope/FunASR/main/MODEL_LICENSE',folder/'MODEL_LICENSE'))
    def download(job):
        url,path=job;raw=get(url,path);print(f'ready {path.name} {len(raw)}',flush=True)
        return {'url':url,'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:receipts=list(pool.map(download,jobs))
    REPORT.mkdir(parents=True,exist_ok=True);(REPORT/'asset_downloads.json').write_text(json.dumps(receipts,indent=2),encoding='utf-8')

if __name__=='__main__':main()
