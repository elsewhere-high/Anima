"""Summarize recorded application runs; no reference-label correctness scoring."""
from pathlib import Path
from datetime import datetime,timezone
import json,statistics,collections
root=Path(__file__).parent
records=[]
for path in (root/'autosaved').glob('*.json'):
    value=json.loads(path.read_text())
    if value.get('suite')=='app-live':records.append((path,value))
def stats(values):
    values=sorted(v for v in values if isinstance(v,(int,float)))
    if not values:return None
    return {'count':len(values),'p50':round(statistics.median(values),1),'p95':round(values[min(len(values)-1,int(len(values)*.95))],1),'max':round(max(values),1)}
summaries=[]
for seconds in [20,600]:
    selected=[(p,v) for p,v in records if v['variant'].startswith(f'app-live-{seconds}-')]
    if not selected:continue
    latest=max(v['createdAt'] for p,v in selected)
    selected=sorted([(p,v) for p,v in selected if v['createdAt']==latest],key=lambda pair:int(pair[1]['variant'].rsplit('-',1)[1]))
    events=[event for p,v in selected for event in v['runs'][0]['events']]
    final=next((v['runs'][0]['qa'] for p,v in selected if v['runs'][0]['qa'].get('final')),None)
    live=[e for e in events if not e.get('afterStop')]
    summary={'requestedSeconds':seconds,'createdAt':latest,'complete':bool(final),'files':[str(p.relative_to(root)) for p,v in selected],
        'final':final,'eventCounts':dict(collections.Counter(e['type'] for e in live)),
        'asrWindowEndToReceiptMs':stats([(e['receivedAt']-e['end'])*1000 for e in live if e['type']=='transcript']),
        'specialistComputeMs':{kind:stats([e['latencyMs'] for e in live if e['type']=='measurement' and e.get('kind')==kind]) for kind in ['face','voice','speech']},
        'independentAccuracy':None,'referenceLabelMatchRequired':False,
        'limits':['ASR latency is measured from the end of captured input, not first phoneme or DOM display.','Specialist times exclude capture, queue and DOM display.','No successful cloud result means no multimodal quality or latency verdict.','Blank controls are sampled once per second after two seconds of blank input.']}
    summaries.append(summary)
result={'generatedAt':datetime.now(timezone.utc).isoformat(),'runs':summaries}
path=root/'iterations/26-free-models/application-summary.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ['requestedSeconds','complete','eventCounts','asrWindowEndToReceiptMs']} for r in summaries],ensure_ascii=False))
