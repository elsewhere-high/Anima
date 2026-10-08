const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
const quantile=(a,p)=>{const b=a.filter(Number.isFinite).sort((x,y)=>x-y);return b.length?b[Math.min(b.length-1,Math.ceil(b.length*p)-1)]:null;};
export function validateManifest(data){
  if(!Array.isArray(data.samples)||!data.samples.length)throw new Error('缺少 samples');
  const ids=new Set(),people=new Map();
  for(const s of data.samples){
    if(!s.id||ids.has(s.id))throw new Error('样本 ID 缺失或重复');ids.add(s.id);
    if(!s.person||!['development','heldout'].includes(s.split))throw new Error('请注明匿名人物与 development/heldout');
    if(people.has(s.person)&&people.get(s.person)!==s.split)throw new Error('同一个人出现在开发与留出集，存在泄漏');people.set(s.person,s.split);
    if(!Array.isArray(s.annotations)||s.annotations.length<2)throw new Error('每段至少两份独立人工标注');
    if(new Set(s.annotations.map(a=>a.annotator)).size<2)throw new Error('标注者不能重复');
    if(!Array.isArray(s.consensus))throw new Error('缺少仲裁结果，未知请填空数组并注明 unknown');
  }return data;
}
export function measure(samples,predictions){
  const byId=new Map(predictions.map(p=>[p.id,p])),labels=new Map(),latency=[],delay=[],failures=[],pairs=[];let covered=0,unknown=0,fpNegative=0,negatives=0,evidenceGood=0,evidenceTotal=0;
  for(const s of samples){
    const p=byId.get(s.id);if(!p||p.error){failures.push(s.id);continue;}
    const actual=new Set((p.signals||[]).map(x=>x.label)),expected=new Set(s.consensus.map(x=>typeof x==='string'?x:x.label));covered+=actual.size>0;unknown+=actual.size===0;
    if(!expected.size){negatives++;if(actual.size)fpNegative++;}
    for(const label of new Set([...expected,...actual])){const c=labels.get(label)||{tp:0,fp:0,fn:0};if(expected.has(label)&&actual.has(label))c.tp++;else if(actual.has(label))c.fp++;else c.fn++;labels.set(label,c);}
    for(const signal of p.signals||[]){evidenceTotal++;if(signal.refs?.length&&signal.observations?.length)evidenceGood++;}
    latency.push(p.latencyMs);for(const truth of s.consensus.filter(t=>typeof t==='object')){const found=(p.signals||[]).find(x=>x.label===truth.label);if(found&&Number.isFinite(truth.evidenceAvailableAt)&&Number.isFinite(found.detectedAt))delay.push((found.detectedAt-truth.evidenceAvailableAt)*1000);}
    pairs.push({person:s.person,score:actual.size===expected.size&&[...actual].every(x=>expected.has(x))?1:0});
  }
  const perLabel=Object.fromEntries([...labels].map(([label,c])=>[label,{...c,precision:c.tp+c.fp?c.tp/(c.tp+c.fp):null,recall:c.tp+c.fn?c.tp/(c.tp+c.fn):null,f1:2*c.tp+c.fp+c.fn?2*c.tp/(2*c.tp+c.fp+c.fn):null}]));
  return {samples:samples.length,responded:samples.length-failures.length,coverage:covered/samples.length,unknownRate:unknown/samples.length,failureRate:failures.length/samples.length,negativeFalsePositiveRate:negatives?fpNegative/negatives:null,macroF1:mean(Object.values(perLabel).map(x=>x.f1).filter(Number.isFinite)),perLabel,requestLatencyMs:{p50:quantile(latency,.5),p95:quantile(latency,.95)},evidenceToDetectionMs:{p50:quantile(delay,.5),p95:quantile(delay,.95)},traceableEvidenceRate:evidenceTotal?evidenceGood/evidenceTotal:null,failures,people:[...new Set(samples.map(s=>s.person))].length,exactMatch:mean(pairs.map(x=>x.score))};
}
export function groupedDifference(samples,a,b,iterations=1000){
  const ap=new Map(a.map(p=>[p.id,p])),bp=new Map(b.map(p=>[p.id,p]));
  const groups=new Map();for(const s of samples){if(!ap.has(s.id)||!bp.has(s.id)||ap.get(s.id).error||bp.get(s.id).error)continue;const expected=new Set(s.consensus.map(t=>typeof t==='string'?t:t.label));const score=p=>{const labels=new Set(p.signals.map(x=>x.label));return labels.size===expected.size&&[...labels].every(x=>expected.has(x))?1:0;};const values=groups.get(s.person)||[];values.push(score(ap.get(s.id))-score(bp.get(s.id)));groups.set(s.person,values);}
  const people=[...groups.values()].map(mean);if(people.length<2)return {difference:mean(people),ci95:null,reason:'至少需要两名独立人物；仍建议20人以上'};
  let seed=2437;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};const bootstrap=Array.from({length:iterations},()=>mean(people.map(()=>people[Math.floor(random()*people.length)])));
  return {metric:'按人宏平均的标签集合完全一致率差值',difference:mean(people),ci95:[quantile(bootstrap,.025),quantile(bootstrap,.975)],people:people.length};
}
