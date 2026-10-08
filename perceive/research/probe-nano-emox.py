"""Bounded local feasibility probe. Only public clip prefixes enter the model."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys
import time

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations'))
import numpy as np
import imageio_ffmpeg
import torch
from nano_emox_adapter import NanoEmox

clip=sys.argv[1] if len(sys.argv)>1 else 'elon-musk-wef'
if clip not in ['yann-lecun-wef','steve-jobs-interview','elon-musk-wef','pep-guardiola-press','mark-zuckerberg-interview']:
    raise ValueError('Public reference clips only')
duration=3
path=ROOT/'public/assets'/f'{clip}.mp4'
out=ROOT/'research/nano-emox-probe'/clip
out.mkdir(parents=True,exist_ok=True)
ff=imageio_ffmpeg.get_ffmpeg_exe()
audio=np.frombuffer(subprocess.check_output([ff,'-v','error','-i',str(path),'-t',str(duration),'-f','f32le','-ac','1','-ar','16000','-']),dtype='<f4').copy()
frames=np.frombuffer(subprocess.check_output([ff,'-v','error','-i',str(path),'-t',str(duration),'-vf','fps=8/3,scale=224:224','-f','rawvideo','-pix_fmt','rgb24','-']),dtype=np.uint8).reshape(-1,224,224,3).copy()
torch.set_num_threads(3)
report={'createdAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'clip':clip,'duration':duration,'device':'mps','checkpoint':'epoch60','scope':'Prefix feasibility only, not social-signal parity or calibrated accuracy','transcriptInput':'none','runs':[]}
started=time.perf_counter()
try:
    model=NanoEmox('mps')
    report.update(loadMs=round((time.perf_counter()-started)*1000),parameters=sum(p.numel() for p in model.model.parameters()),loadReport=model.load_report)
    print(json.dumps({'loaded':True,'loadMs':report['loadMs'],'parameters':report['parameters'],'loadReport':report['loadReport']}),flush=True)
    for repeat in range(2):
        value=model.infer(list(frames),audio,max_tokens=64)
        report['runs'].append(value)
        (out/'result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
        print(json.dumps(value,ensure_ascii=False),flush=True)
except Exception as error:
    report['error']=type(error).__name__+': '+str(error)
    (out/'result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    raise
