"""Published Romana et al. WavLM acoustic detector; no training or diagnosis.
Architecture and label order: amritkromana/disfluency_detection_from_audio.
Uses the authors' 0.5 frame threshold. Scores are not calibrated probabilities.
"""
import base64
import io
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from transformers import WavLMConfig, WavLMModel, Wav2Vec2FeatureExtractor

LABELS = ['filled_pause', 'repetition', 'revision', 'restart', 'partial_word']
ROOT = Path(__file__).resolve().parent / 'models/romana-disfluency'

class AcousticDetector(torch.nn.Module):
    def __init__(self, root):
        super().__init__()
        self.basemodel = WavLMModel(WavLMConfig.from_json_file(str(root/'config.json')))
        self.linear = torch.nn.Linear(768, 5)

    def forward(self, x):
        features = self.basemodel.feature_extractor(x).transpose(1, 2)
        features, _ = self.basemodel.feature_projection(features)
        return self.linear(self.basemodel.encoder(features, return_dict=True)[0])

class DisfluencyModel:
    def __init__(self, root=ROOT):
        self.model = AcousticDetector(root)
        self.model.load_state_dict(torch.load(root/'acoustic.pt', map_location='cpu', weights_only=True), strict=True)
        self.model.eval()
        self.features = Wav2Vec2FeatureExtractor(feature_size=1, sampling_rate=16000,
                                                padding_value=0, do_normalize=True, return_attention_mask=False)

    def infer(self, request):
        audio, rate = sf.read(io.BytesIO(base64.b64decode(request['audio'], validate=True)), dtype='float32')
        if rate != 16000 or audio.ndim != 1 or not 6400 <= len(audio) <= 16000*8:
            raise ValueError('expected mono 16kHz WAV, .4–8 seconds')
        result = {'model': 'Romana-TASLP2024-WavLM-base', 'speechSpans': [], 'quality': 'ok',
                  'trainingLanguage': 'English', 'frameStrideSeconds': .02,
                  'scoreMeaning': 'uncalibrated acoustic event scores, not mental states'}
        if float(np.sqrt(np.mean(audio*audio))) < .0032:
            return {**result, 'quality': 'quiet'}
        tensor = self.features(audio, sampling_rate=16000, return_tensors='pt').input_values
        with torch.inference_mode():
            probabilities = torch.sigmoid(self.model(tensor))[0].numpy()
        for j, label in enumerate(LABELS):
            mask = probabilities[:, j] > .5
            starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
            ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
            for start, end in zip(starts, ends):
                result['speechSpans'].append({'label': label, 'start': round(float(start)*.02, 3),
                    'end': round(min(len(audio)/16000, (float(end)-1)*.02+.025), 3),
                    'meanScore': round(float(probabilities[start:end, j].mean()), 4)})
        result['speechSpans'].sort(key=lambda x: x['start'])
        return result
