"""Download pinned upstream ONNX assets, with an auditable local manifest."""
import hashlib, json, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'social-companion-v5'}), timeout=120) as r:
        return r.read()

def main():
    target = ROOT / 'models/vision'; target.mkdir(parents=True, exist_ok=True)
    reports = ROOT / 'reports/upstream'; reports.mkdir(parents=True, exist_ok=True)
    manifest = []
    repos = {'opencv/opencv_zoo':'47534e27c9851bb1128ccc0102f1145e27f23f98', 'sb-ai-lab/EmotiEffLib':'520a051c64cd191521e5934655314e769a319684'}
    assets = [
        ('opencv/opencv_zoo','models/face_detection_yunet/face_detection_yunet_2023mar.onnx','yunet.onnx','MIT'),
        ('opencv/opencv_zoo','models/face_recognition_sface/face_recognition_sface_2021dec.onnx','sface.onnx','Apache-2.0'),
        ('sb-ai-lab/EmotiEffLib','models/affectnet_emotions/onnx/enet_b0_8_best_vgaf.onnx','expression.onnx','repository Apache-2.0; see training-data terms'),
    ]
    for repo, path, name, license_name in assets:
        rev = repos[repo]
        url = f'https://media.githubusercontent.com/media/{repo}/{rev}/{path}'
        try: data = get(url)
        except Exception: data = get(f'https://raw.githubusercontent.com/{repo}/{rev}/{path}')
        if len(data)<100000 or data.startswith(b'version https://git-lfs'): raise RuntimeError('Not a model: '+name)
        (target/name).write_bytes(data)
        row = dict(file=name, repository=repo, revision=rev, url=url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), license=license_name)
        manifest.append(row); print(json.dumps(row), flush=True)
    for repo, path, name in [
        ('opencv/opencv_zoo','models/face_detection_yunet/LICENSE','yunet_LICENSE'),
        ('opencv/opencv_zoo','models/face_recognition_sface/LICENSE','sface_LICENSE'),
        ('sb-ai-lab/EmotiEffLib','LICENSE','emotieff_LICENSE'),
        ('sb-ai-lab/EmotiEffLib','emotiefflib/facial_analysis.py','emotieff_preprocessing_reference.py'),
        ('sb-ai-lab/EmotiEffLib','README.md','emotieff_README.md')]:
        (reports/name).write_bytes(get(f'https://raw.githubusercontent.com/{repo}/{repos[repo]}/{path}'))
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')

if __name__=='__main__': main()
