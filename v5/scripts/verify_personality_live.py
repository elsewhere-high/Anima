"""Run bounded real-model cold-start examples as an anonymous guest."""
import json
import uuid
from pathlib import Path
import requests

cases=[
    ('INFJ','auto','今天有点累，我想跟你待一会儿。'),
    ('ENTJ','auto','最近事情很多，我不知道先做哪一件，帮我分析一下。'),
    ('ENTJ','analyze','我现在只想倾诉，先别给建议。'),
    ('ENFP','auto','今天有件开心的事，想跟你分享。'),
    ('ISTJ','auto','我想安静一会儿，请先不要打扰我。'),
]
rows=[]
for mbti,support,speech in cases:
    response=requests.post('http://127.0.0.1:8768/v1/step',json={
        'observation':{'session_id':'mbti-check-'+uuid.uuid4().hex,'speech':speech},
        'dialogue_preferences':{'mbti':mbti,'support':support}},timeout=90)
    response.raise_for_status();data=response.json()
    row={'mbti':mbti,'speech':speech,'response':data['response'],
         'dialogue_status':data['dialogue']['status'],'profile':data['state']['dialogue_profile'],
         'action':data['action'],'latency_ms':data['latency_ms']}
    rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    assert data['dialogue']['status']!='input_too_long'
    assert not data['task']['authorized'] and data['motion']['command']=='HOLD'
Path(__file__).resolve().parents[1].joinpath('reports/personality_live.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
