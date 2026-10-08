"""Summarize one actual application's displayed/received live timeline."""
import json,statistics,collections,sys
from pathlib import Path
root=Path(__file__).parent
profile=sys.argv[1]
docs=[]
for p in (root/'autosaved').glob('*.json'):
 d=json.loads(p.read_text())
 if d.get('suite')=='app-live' and d['runs'][0].get('qa',{}).get('profile')==profile:docs.append((p,d))
if not docs:raise SystemExit('No saved minute yet')
latest=max(d['createdAt'] for p,d in docs)
docs=sorted([(p,d) for p,d in docs if d['createdAt']==latest],key=lambda pair:int(pair[1]['variant'].rsplit('-',1)[1]))
events=[e for p,d in docs for e in d['runs'][0]['events']]
live=[e for e in events if not e.get('afterStop')]
final=next((d['runs'][0]['qa'] for p,d in docs if d['runs'][0]['qa'].get('final')),None)
def stats(a):
 a=sorted(x for x in a if isinstance(x,(int,float)))
 return {'n':len(a),'p50Ms':round(statistics.median(a),1),'p95Ms':round(a[min(len(a)-1,int(len(a)*.95))],1),'maxMs':round(max(a),1)} if a else None
def summarize(events):
 return {'asrCompletedWindowEndToReceipt':stats([(e['receivedAt']-e['end'])*1000 for e in events if e['type']=='transcript' and not e.get('provisional')]),
  'fastInputEndToReceipt':stats([(e['receivedAt']-e['end'])*1000 for e in events if e['type']=='fast.result']),
  'fastRequest':stats([e['latencyMs'] for e in events if e['type']=='fast.result']),
  'reviewInputEndToReceipt':stats([(e['receivedAt']-e['end'])*1000 for e in events if e['type']=='result']),
  'specialistCompute':{k:stats([e['latencyMs'] for e in events if e['type']=='measurement' and e['kind']==k]) for k in ['face','voice','speech']}}
shown_ids=set();tag_appearances=[];caption_ends=set();caption_appearances=[]
for e in live:
 if e['type']!='display':continue
 end=e.get('transcriptEnd')
 if e.get('text') and end is not None and e.get('transcriptTiming')=='committed-audio' and end not in caption_ends:
  caption_ends.add(end);caption_appearances.append((e['at']-end)*1000)
 for s in e['signals']:
  if s['id'] in shown_ids:continue
  shown_ids.add(s['id']);tag_appearances.append({'label':s['label'],'source':s['source'],'inputEndToDisplayMs':(e['at']-s['end'])*1000,'at':e['at']})
result={'profile':profile,'createdAt':latest,'complete':bool(final),'models':docs[0][1]['models'],'files':[str(p.relative_to(root)) for p,d in docs],'final':final,
 'savedParts':len(docs),'liveEventCounts':dict(collections.Counter(e['type'] for e in live)),
 'notices':dict(collections.Counter(e.get('code') for e in live if e['type']=='notice')),
 'latency':summarize(live),'captionInputEndToFirstDOM':stats(caption_appearances),
 'tagInputEndToFirstDOM':{source:stats([s['inputEndToDisplayMs'] for s in tag_appearances if s['source']==source]) for source in sorted({s['source'] for s in tag_appearances})},
 'minutes':{str(i):summarize([e for e in live if (i-1)*60<=e['receivedAt']<i*60]) for i in range(1,11) if any((i-1)*60<=e['receivedAt']<i*60 for e in live)},
 'independentAccuracy':None,'limits':['Input-end latency excludes waiting to collect a roughly 2s ASR chunk.','Draft timestamps based on receipt are excluded from caption DOM latency. Older runs without timing provenance have no accepted caption DOM latency.','Label onset is model estimated; input-end-to-DOM is not physical expression onset latency.','Local model time excludes capture and queue.','Repeated public clip stress test is not held-out accuracy.']}
out=root/(sys.argv[2] if len(sys.argv)>2 else 'iterations/31-continuous/application-summary.json')
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['profile','complete','savedParts','notices','latency','captionInputEndToFirstDOM','tagInputEndToFirstDOM']},ensure_ascii=False))
