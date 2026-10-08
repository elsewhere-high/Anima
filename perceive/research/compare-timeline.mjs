import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';

export function intervalsFromSteps(steps,duration){
  const intervals=new Map(),open=new Map();
  for(const step of [...steps,{at:duration,codes:[]}]){
    const at=Math.min(duration,Math.max(0,step.at)),codes=new Set(step.codes);
    for(const [code,start]of open)if(!codes.has(code)){
      if(at>start){if(!intervals.has(code))intervals.set(code,[]);intervals.get(code).push([start,at]);}
      open.delete(code);
    }
    for(const code of codes)if(!open.has(code)&&at<duration)open.set(code,at);
  }
  return intervals;
}
const length=intervals=>intervals.reduce((sum,[a,b])=>sum+b-a,0);
export function overlap(a,b){let n=0;for(const [x,y]of a)for(const [u,v]of b)n+=Math.max(0,Math.min(y,v)-Math.max(x,u));return n;}
export function compareEpisodes(reference,candidate,grace=.5){
  return reference.map(([start,end])=>{
    const first=candidate.find(([a,b])=>a<end&&b>start);
    const appearedAt=first?Math.max(start,first[0]):null;
    return {start,end,firstOverlappingDisplayAt:appearedAt,delayFromReferenceMs:appearedAt===null?null:Math.round((appearedAt-start)*1000),
      timely:appearedAt!==null&&appearedAt<=start+grace,alreadyVisibleAtReferenceOnset:!!first&&first[0]<start};
  });
}

async function main(input,output){
  const log=JSON.parse(await readFile(input,'utf8'));
  if(log.control||log.suite&&log.suite!=='interhuman')throw Error('Normal Interhuman comparison only');
  const refs=JSON.parse(await readFile(new URL('./interhuman-reference-events.json',import.meta.url),'utf8'));
  const runs=log.runs.map(run=>{
    const ref=refs.clips.find(c=>c.id===run.id),active=new Set(),steps=[];
    for(const e of ref.events){if(e.kind==='signal')active.add(e.signal.type);else if(e.kind==='signal_ended')active.delete(e.ended.type);else continue;steps.push({at:e.atMs/1000,codes:[...active]});}
    const reference=intervalsFromSteps(steps,run.duration),candidate=intervalsFromSteps((run.display||[]).map(d=>({at:d.at,codes:d.signals.map(s=>s.code||s.label)})),run.duration);
    return {id:run.id,round:run.round,error:run.error||null,labels:[...reference].map(([code,r])=>{
      const c=candidate.get(code)||[],shared=overlap(r,c),referenceSeconds=length(r),candidateSeconds=length(c);
      return {code,referenceIntervals:r,candidateIntervals:c,referenceSeconds,candidateSeconds,overlapSeconds:shared,
        displayedReferenceTimeCoverage:shared/referenceSeconds,displayTimelineIoU:shared/(referenceSeconds+candidateSeconds-shared),candidateAppearances:c.length,
        extraDisplaySeconds:candidateSeconds-shared,episodes:compareEpisodes(r,c)};
    }),additionalCandidateLabels:[...candidate.keys()].filter(c=>!reference.has(c))};
  });
  const labels=runs.flatMap(r=>r.labels),sum=k=>labels.reduce((n,l)=>n+l[k],0);
  const episodes=labels.flatMap(l=>l.episodes);
  const report={createdAt:new Date().toISOString(),input,scope:'Display timeline agreement with prerecorded reference, not model latency or human accuracy. Early extra time is a difference, not automatically a false positive. Repeated visible transitions can be flicker, not useful granularity.',
    referenceTimeCoverage:sum('overlapSeconds')/sum('referenceSeconds'),macroDisplayTimelineIoU:sum('displayTimelineIoU')/labels.length,
    episodeTiming:{referenceEpisodes:episodes.length,overlappingEpisodes:episodes.filter(e=>e.firstOverlappingDisplayAt!==null).length,timelyOverlappingEpisodes:episodes.filter(e=>e.timely).length,graceSeconds:.5,note:'A label that appeared early but disappeared before the reference episode gets no timely credit. Existing labels count only if still visible; correctness remains unverified.'},runs};
  await writeFile(output,JSON.stringify(report,null,2));console.log(JSON.stringify({referenceTimeCoverage:report.referenceTimeCoverage,macroDisplayTimelineIoU:report.macroDisplayTimelineIoU}));
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await main(...process.argv.slice(2));
