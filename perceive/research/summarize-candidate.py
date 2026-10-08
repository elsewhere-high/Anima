"""Actual input/arrival statistics; label counts are not accuracy scores."""
import sys,json,statistics,collections
from pathlib import Path
root=Path(__file__).parent
variant,out=sys.argv[1:3]
docs=[json.loads(p.read_text()) for p in (root/'autosaved').glob('*.json')]
docs=[d for d in docs if d['variant']==variant]
latest=max(d['createdAt'] for d in docs)
docs=[d for d in docs if d['createdAt']==latest]
merged=dict(docs[0]);merged['runs']=sorted([r for d in docs for r in d['runs']],key=lambda r:(r['round'],r['id']))
out=root/out;out.mkdir(parents=True,exist_ok=True)
(out/'live.json').write_text(json.dumps(merged,ensure_ascii=False,indent=2)+'\n')
def stats(a):
 a=sorted(a)
 return {'n':len(a),'p50Ms':round(statistics.median(a),1),'p95Ms':round(a[min(len(a)-1,int(len(a)*.95))],1),'maxMs':round(max(a),1)} if a else None
events=[e for r in merged['runs'] for e in r['events']]
summary={'variant':variant,'createdAt':latest,'sessions':len(merged['runs']),'models':merged['models'],'rounds':{},'notices':dict(collections.Counter(e.get('code') for e in events if e['type']=='notice')),'independentAccuracy':None,'exactReferenceMatching':False}
for kind in ['fast.result','result','transcript']:
 values=[e for e in events if e['type']==kind];live=[e for e in values if not e.get('afterStop')]
 summary[kind]={'total':len(values),'live':len(live),'liveNonempty':sum(bool(e.get('signals',e.get('text'))) for e in live),'requestLatency':stats([e['latencyMs'] for e in live if 'latencyMs'in e]),'inputEndToReceipt':stats([(e['clientReceivedAt']-e['end'])*1000 for e in live if kind!='transcript' or (not e.get('provisional') and (e.get('timing')=='committed-audio' or e.get('source')=='SenseVoiceSmall'))]),'stale':sum(bool(e.get('stale')) for e in live)}
for r in merged['runs']:
 summary['rounds'][f"{r['round']}-{r['id']}"]={'duration':r['duration'],'displayChanges':len(r['display']),'labels':sorted({s['label'] for d in r['display'] for s in d['signals']}),'error':r.get('error')}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['rounds','models']},ensure_ascii=False))
