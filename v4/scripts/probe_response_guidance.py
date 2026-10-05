"""Known-development prompt diagnostics; never reported as held-out accuracy."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from social_v4.predictor import Predictor
p=Predictor('cuda');rows=json.loads((ROOT/'data/dialogue_development_cases.json').read_text(encoding='utf-8'))
guidance='先直接回答用户已经说清楚的问题。能依据现有信息给出生活建议时，不要用不必要的确认问题代替答案。设备执行限制不妨碍提供一般生活建议。'
results=[]
for r in rows:
    if r['id'] not in ['reference_sister','listen_only','no_vision','grief_not_minimize','recent_fact','ordinary_knowledge']:continue
    out=p.generate_dialogue(r['history'],r['speech'],policy={'回答要求':guidance})
    results.append({'id':r['id'],'reply':out['reply']});print(json.dumps(results[-1],ensure_ascii=False),flush=True)
(ROOT/'reports/response_guidance_probe.json').write_text(json.dumps({'known_development':True,'guidance':guidance,'responses':results},ensure_ascii=False,indent=2),encoding='utf-8')
