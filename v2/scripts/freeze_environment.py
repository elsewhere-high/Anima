import json,importlib.metadata,platform,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
packages=sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())
(root/'requirements.lock.txt').write_text('\n'.join(f'{name}=={version}' for name,version in packages)+'\n',encoding='utf-8')
import torch
(root/'reports/environment.json').write_text(json.dumps({'python':platform.python_version(),'platform':platform.platform(),'torch':torch.__version__,'cuda_runtime':torch.version.cuda,'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None,'packages':dict(packages)},indent=2))
