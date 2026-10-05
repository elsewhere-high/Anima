"""Release-bound task routing; state inference and dialogue share one backbone."""
import json, os, threading, hashlib
from pathlib import Path
import torch
from .runtime_model import SharedModel, ROOT, V2, STATE_LABELS
from .chat_model import generate_text
from .dialogue import format_messages
from social_world_zh.spec import HEADS, state_text
from social_world_zh.labels_zh import label_zh
from social_world_zh.model import checkpoint_fingerprint
from social_world_zh.affect import coarse_affect, ZH


def sha256(path):
    with Path(path).open('rb') as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


class Predictor:
    def __init__(self, device='cuda', release_path=None):
        torch.set_num_threads(int(os.getenv('SOCIAL_THREADS', '4')))
        self.device = device
        self.lock = threading.RLock()
        path = Path(release_path or ROOT / 'models/release.json')
        release = json.loads(path.read_text(encoding='utf-8'))
        if release.get('status') != 'validated': raise RuntimeError('V4 release is not validated')
        # All file references resolve against V4, not the working directory.
        self.release = release
        state = release.get('state')
        dialogue = release.get('dialogue')
        state_path = (ROOT / state['checkpoint']).resolve() if state else None
        dialogue_path = (ROOT / dialogue['checkpoint']).resolve() if dialogue else None
        if state and checkpoint_fingerprint(state_path) != state['fingerprint']: raise RuntimeError('State checkpoint fingerprint mismatch')
        if dialogue and sha256(dialogue_path / 'adapter/adapter_model.safetensors') != dialogue['sha256']: raise RuntimeError('Dialogue checkpoint fingerprint mismatch')
        quantized = device == 'cpu' and (ROOT / 'models/cpu_base_int8.pt').exists()
        if quantized:
            cpu = release.get('cpu_base')
            if not cpu or sha256(ROOT / cpu['file']) != cpu['sha256']:
                raise RuntimeError('CPU base fingerprint mismatch or missing release binding')
            from .cpu_model import SharedCPUModel
            self.model = SharedCPUModel(state_path, dialogue_path)
        else: self.model = SharedModel(device, state_path, dialogue_path)
        original_calibration = json.loads((V2 / 'reports/calibration.json').read_text())
        if self.model.checkpoint_fingerprint != original_calibration['checkpoint_fingerprint']: raise RuntimeError('Original checkpoint calibration mismatch')
        self.temperature = original_calibration['temperatures']
        self.accepted_heads = state['accepted_heads'] if state else []
        self.state_temperature = state['temperatures'] if state else {}
        self.backend = 'shared_qwen35_2b_cpu_int8_fp32_lora' if quantized else 'shared_qwen35_2b_bf16_' + device
        self.transition = None

    def _result(self, key, scores, names, temperature=1., source=None):
        p = (scores.float() / temperature).softmax(-1).cpu().tolist()
        index = max(range(len(p)), key=p.__getitem__)
        name = names[index]
        return {'label': name, 'label_zh': ZH[name] if key == 'sentiment' else label_zh(key, name), 'confidence': p[index], 'distribution': dict(zip(names, p)), 'source': source}

    def state(self, history, speech):
        keys = ['emotion', 'dialog_act', 'intent', 'boundary', 'policy', 'task_domain']
        if not speech.strip():
            defaults = dict(zip(keys, ['unknown', 'unknown', 'unknown', 'unspecified', 'WAIT', 'unknown']))
            return {k: {'label': v, 'label_zh': label_zh(k, v), 'confidence': 0., 'distribution': {}, 'source': 'not_evaluated_no_speech'} for k, v in defaults.items()}
        with self.lock, torch.inference_mode():
            inputs = self.model.tokenizer([state_text(history[-4:], speech)], padding=True, truncation=True, max_length=256, return_tensors='pt').to(self.device)
            original = self.model.original_logits(**inputs)
            results = {k: self._result(k, original[k][0], HEADS[k], self.temperature[k], 'v2_retained_task_adapter') for k in keys}
            original_sentiment = coarse_affect(results['emotion'])
            original_sentiment['source'] = 'v2_retained_derived_sentiment'
            if self.accepted_heads:
                current = self.model.state_logits(**inputs)
                for k in self.accepted_heads:
                    results[k] = self._result(k, current[k][0], STATE_LABELS[k], self.state_temperature[k], 'v4_trained_current_state_adapter')
            if 'sentiment' not in results: results['sentiment'] = original_sentiment
            return results

    def generate_dialogue(self, history, speech, memories=None, policy=None):
        with self.lock:
            route = 'dialogue' if self.model.dialogue_loaded else 'base'
            with self.model.route(route):
                result = generate_text(self.model.backbone, self.model.tokenizer, format_messages(history, speech, memories, policy), device=self.device)
            result['adapter'] = route
            return result

    def imagine(self, *args, **kwargs):
        return {'status': 'disabled_in_v4', 'reason': '本版本聚焦当前情绪理解和中文对话，未提供通过验收的未来预测。', 'predictions': [], 'advisory_only': True}
