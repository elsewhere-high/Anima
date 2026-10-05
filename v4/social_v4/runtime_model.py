"""One physical Qwen base, isolated task adapters and classifier weights."""
import sys, contextlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT.parent / 'v2'
sys.path.insert(0, str(V2))
import torch
from social_world_zh.model import SocialModel
from social_world_zh.spec import HEADS

STATE_LABELS = {k: HEADS[k] for k in ('emotion', 'dialog_act')}
STATE_LABELS['sentiment'] = ['negative', 'neutral', 'positive']


class SharedModel(SocialModel):
    def __init__(self, device='cuda', state_checkpoint=None, dialogue_checkpoint=None):
        super().__init__(device, V2 / 'models/social_zh/best')
        self.state_heads = None
        self.dialogue_loaded = False
        if state_checkpoint:
            state_checkpoint = Path(state_checkpoint)
            self.backbone.load_adapter(str(state_checkpoint / 'adapter'), adapter_name='current_state', is_trainable=False)
            weights = torch.load(state_checkpoint / 'heads.pt', map_location=device, weights_only=True)
            width = self.heads['emotion'].in_features
            self.state_heads = torch.nn.ModuleDict({k: torch.nn.Linear(width, len(v)) for k, v in STATE_LABELS.items()}).to(device)
            self.state_heads.load_state_dict({k: v for k, v in weights.items() if k.split('.')[0] in STATE_LABELS})
        if dialogue_checkpoint:
            self.backbone.load_adapter(str(Path(dialogue_checkpoint) / 'adapter'), adapter_name='dialogue', is_trainable=False)
            self.dialogue_loaded = True
        self.backbone.set_adapter('default')
        self.requires_grad_(False)
        self.eval()

    @contextlib.contextmanager
    def route(self, name):
        """Caller serializes inference; every route restores original task adapter."""
        try:
            if name == 'base':
                with self.backbone.disable_adapter():
                    yield
            else:
                self.backbone.set_adapter(name)
                yield
        finally:
            self.backbone.set_adapter('default')

    def state_logits(self, **inputs):
        if self.state_heads is None:
            raise RuntimeError('Current-state adapter is not loaded')
        with self.route('current_state'), torch.autocast(self.device_name, dtype=torch.bfloat16):
            h = self.backbone(**inputs, use_cache=False).last_hidden_state
        h = h[torch.arange(len(h), device=h.device), inputs['attention_mask'].sum(1) - 1].float()
        return {k: head(h) for k, head in self.state_heads.items()}

    def original_logits(self, **inputs):
        with self.route('default'):
            return super().forward(**inputs)
