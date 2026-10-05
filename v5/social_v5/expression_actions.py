"""Describe visible facial movements, without converting geometry into emotion."""
import math

PAIRS = {'mouth_corners_up':('mouthSmileLeft','mouthSmileRight'),
         'brows_drawn_down':('browDownLeft','browDownRight'),
         'eyes_closed':('eyeBlinkLeft','eyeBlinkRight'),
         'mouth_corners_down':('mouthFrownLeft','mouthFrownRight')}
ZH = {'mouth_corners_up':'嘴角上扬','brows_drawn_down':'眉部收紧',
      'eyes_closed':'双眼闭合','mouth_corners_down':'嘴角下压','jaw_open':'张口'}

def action_scores(blendshapes):
    clean = {k:float(v) for k,v in blendshapes.items() if isinstance(v,(int,float)) and math.isfinite(v) and 0 <= v <= 1}
    out = {name:min(clean[a],clean[b]) for name,(a,b) in PAIRS.items() if a in clean and b in clean}
    if 'jawOpen' in clean: out['jaw_open'] = clean['jawOpen']
    return out

def describe_actions(scores):
    return [ZH[k] for k,v in scores.items() if k in ZH and v >= .45]
