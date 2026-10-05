import os,pathlib,json,argparse
ROOT=pathlib.Path(__file__).resolve().parents[1]
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ['HF_HOME']=str(ROOT/'cache')
from huggingface_hub import snapshot_download
p=argparse.ArgumentParser();p.add_argument('--size',default='0.8B');a=p.parse_args()
info=json.loads((ROOT/'research'/('qwen08_api.txt' if a.size=='0.8B' else 'qwen2_api.txt')).read_text())
snapshot_download('Qwen/Qwen3.5-'+a.size,revision=info['sha'],local_dir=ROOT/'models'/('qwen35_'+a.size),max_workers=2)
print('MODEL_DOWNLOAD_COMPLETE',a.size,flush=True)
