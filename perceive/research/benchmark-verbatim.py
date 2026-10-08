"""Offline feasibility check; no emotion ground truth or realtime accuracy claim."""
import dataclasses
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
import imageio_ffmpeg
import numpy as np
import torch
from crisperwhisper import CrisperWhisperModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research' / 'verbatim-feasibility.json'
torch.set_num_threads(3)
device = 'mps' if torch.backends.mps.is_available() else 'cpu'
report = {'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'model': 'nyralabs/CrisperWhisper2.0_small', 'package': 'crisperwhisper-2.0.3',
          'device': device, 'computeType': 'float32', 'wordTimestamps': True,
          'scope': '3-second windows and whole public clips; latency feasibility, no accuracy truth', 'runs': []}
def save():
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))

began = time.perf_counter()
model = CrisperWhisperModel(str(ROOT / 'integrations/models/crisper-small'),
                           backend='transformers', device=device, compute_type='float32')
report['loadSeconds'] = time.perf_counter() - began
save()
samples = [('silence', 'negative-control', np.zeros(48000, dtype=np.float32))]
for path in sorted((ROOT / 'public/assets').glob('*.mp4')):
    raw = subprocess.check_output([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'])
    audio = np.frombuffer(raw, dtype='<f4').copy()
    samples.extend([(path.stem, 'first-3s', audio[:48000]),
                    (path.stem, 'last-3s', audio[-48000:]),
                    (path.stem, 'whole', audio)])
for clip, window, audio in samples:
    began = time.perf_counter()
    try:
        value = model.transcribe(audio, sr=16000, language='en', word_timestamps=True,
                                 max_new_tokens=128, temperature_fallback=False)
        row = {'clip': clip, 'window': window, 'wallMs': round((time.perf_counter()-began)*1000),
               'audioSeconds': len(audio)/16000, 'result': dataclasses.asdict(value)}
    except Exception as error:
        row = {'clip': clip, 'window': window, 'error': str(error), 'wallMs': round((time.perf_counter()-began)*1000)}
    report['runs'].append(row)
    save()
    print(json.dumps({k: row[k] for k in ['clip', 'window', 'wallMs', 'error'] if k in row}), flush=True)
