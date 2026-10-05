"""One code path, three measured scheduling budgets; one active speech backend."""
import os
from dataclasses import dataclass, asdict
import psutil

@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    audio_backend: str
    visual_interval: float
    active_interval: float
    body_interval: float
    threads: int = 2

PROFILES={
    'ultra_light': RuntimeProfile('ultra_light','whisper',2.0,.8,2.0),
    'balanced': RuntimeProfile('balanced','sensevoice',1.0,.4,1.0),
    'best_edge': RuntimeProfile('best_edge','sensevoice',.5,.2,.5,4),
}
def select_profile(name=None):
    name=name or os.getenv('SOCIAL_PROFILE','auto')
    if name=='auto':
        name='balanced' if psutil.virtual_memory().total>=12*1024**3 and (os.cpu_count() or 1)>=8 else 'ultra_light'
    if name not in PROFILES:raise ValueError('SOCIAL_PROFILE must be auto, ultra_light, balanced or best_edge')
    return PROFILES[name]
