"""Evaluate published acoustic weights, without training or social-state claims.

Architecture/label order follow Romana et al., TASLP 2024:
https://github.com/amritkromana/disfluency_detection_from_audio
Only the supplied prefix is processed; the encoder is bidirectional within it.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['HF_HUB_OFFLINE'] = '1'
import imageio_ffmpeg
import numpy as np
import torch
from transformers import WavLMConfig, WavLMModel, Wav2Vec2FeatureExtractor

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'integrations/models/romana-disfluency'
LABELS = ['filled_pause', 'repetition', 'revision', 'restart', 'partial_word']
torch.set_num_threads(3)

class AcousticDetector(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.basemodel = WavLMModel(WavLMConfig.from_json_file(str(MODEL / 'config.json')))
        self.linear = torch.nn.Linear(768, 5)

    def forward(self, x):
        features = self.basemodel.feature_extractor(x).transpose(1, 2)
        features, _ = self.basemodel.feature_projection(features)
        return self.linear(self.basemodel.encoder(features, return_dict=True)[0])

def spans(probabilities, duration):
    result = []
    for j, label in enumerate(LABELS):
        mask = probabilities[:, j] > .5  # Authors' default; not tuned on demo.
        starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
        ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
        for start, end in zip(starts, ends):
            result.append({'label': label, 'start': round(float(start)*.02, 3),
                           'end': round(min(duration, (float(end)-1)*.02+.025), 3),
                           'meanScore': round(float(probabilities[start:end, j].mean()), 4),
                           'peakScore': round(float(probabilities[start:end, j].max()), 4)})
    return sorted(result, key=lambda x: x['start'])

def main():
    device = os.environ.get('ANIMA_PROBE_DEVICE', 'cpu')
    output = ROOT / 'research' / f'disfluency-feasibility-{device}.json'
    report = {'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'model': 'Romana-TASLP2024-acoustic-WavLM-base', 'device': device,
              'checkpointSha256': hashlib.file_digest(open(MODEL/'acoustic.pt', 'rb'), 'sha256').hexdigest(),
              'threshold': .5, 'frameStrideSeconds': .02, 'receptiveFieldSeconds': .025,
              'scope': 'Causal prefix/window feasibility only; no social emotion accuracy claim', 'runs': []}
    began = time.perf_counter()
    model = AcousticDetector()
    model.load_state_dict(torch.load(MODEL/'acoustic.pt', map_location='cpu', weights_only=True), strict=True)
    model.eval().to(device)
    report['parameters'] = sum(p.numel() for p in model.parameters())
    report['loadSeconds'] = round(time.perf_counter()-began, 3)
    features = Wav2Vec2FeatureExtractor(feature_size=1, sampling_rate=16000,
                                       padding_value=0, do_normalize=True, return_attention_mask=False)
    samples = [('silence', 0, np.zeros(48000, dtype=np.float32))]
    for path in sorted((ROOT/'public/assets').glob('*.mp4')):
        raw = subprocess.check_output([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(path),
                                       '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'])
        audio = np.frombuffer(raw, dtype='<f4').copy()
        for end in np.arange(1, len(audio)/16000+.01, .5):
            start = max(0, end-3)
            samples.append((path.stem, float(start), audio[round(start*16000):round(end*16000)]))
    for clip, start, audio in samples:
        began = time.perf_counter()
        tensor = features(audio, sampling_rate=16000, return_tensors='pt').input_values.to(device)
        with torch.inference_mode():
            probabilities = torch.sigmoid(model(tensor))[0].cpu().numpy()
        result = {'clip': clip, 'start': start, 'end': start+len(audio)/16000,
                  'wallMs': round((time.perf_counter()-began)*1000),
                  'spans': spans(probabilities, len(audio)/16000)}
        report['runs'].append(result)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({k: result[k] for k in ['clip', 'start', 'end', 'wallMs']}), flush=True)

if __name__ == '__main__':
    main()
