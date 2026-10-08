"""Download released research checkpoints only. Never train or load remote code."""
from pathlib import Path
import json
from huggingface_hub import HfApi, snapshot_download

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'integrations/models/nano-emox'
SOURCES = [
    ('Jiaha0Hu4ng/Nano-EmoX', 'adapters', ['README.md', 'checkpoint_000060_loss_0.285.pth']),
    ('Qwen/Qwen2.5-1.5B-Instruct', 'qwen', ['*.json', '*.txt', 'model.safetensors']),
    ('openai/clip-vit-large-patch14', 'clip', ['*.json', '*.txt', 'model.safetensors']),
    ('TencentGameMate/chinese-hubert-large', 'hubert', ['config.json', 'preprocessor_config.json', 'pytorch_model.bin']),
    ('kartiknarayan/facexformer', 'face', ['ckpts/model.pt']),
    ('google-bert/bert-base-uncased', 'bert', ['config.json']),
]
DEST.mkdir(parents=True, exist_ok=True)
manifest = {'scope':'Feasibility only, no Anima accuracy claim; last released epoch selected before testing.', 'sources':[]}
for repo, name, patterns in SOURCES:
    revision = HfApi(token=False).model_info(repo).sha
    print('Downloading', repo, revision, flush=True)
    snapshot_download(repo, revision=revision, token=False, local_dir=DEST/name,
                      allow_patterns=patterns, max_workers=2)
    manifest['sources'].append({'repo':repo,'revision':revision,'directory':name,'patterns':patterns})
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('All Nano-EmoX research weights downloaded',flush=True)
