import test from 'node:test';
import assert from 'node:assert/strict';
import {validateManifest,measure,groupedDifference} from '../research/metrics.mjs';
const annotations=[{annotator:'a'},{annotator:'b'}];
test('评测禁止同人跨开发集与验收集、单标注者和重复样本',()=>{
 const samples=[{id:'1',person:'p',split:'development',annotations,consensus:[]},{id:'2',person:'p',split:'heldout',annotations,consensus:[]}];assert.throws(()=>validateManifest({samples}),/泄漏/);assert.throws(()=>validateManifest({samples:[{...samples[0],annotations:[annotations[0]]}]}),/两份/);
});
test('评测报告误报、漏报、覆盖率与失败率；不能靠全部未知获得高分',()=>{
 const samples=[{id:'1',person:'a',consensus:['反对']},{id:'2',person:'b',consensus:[]}];const result=measure(samples,[{id:'1',signals:[],latencyMs:100},{id:'2',signals:[{label:'兴趣'}],latencyMs:200}]);assert.equal(result.perLabel['反对'].fn,1);assert.equal(result.negativeFalsePositiveRate,1);assert.equal(result.coverage,.5);assert.equal(result.macroF1,0);assert.equal(result.requestLatencyMs.p95,200);assert.equal(measure(samples,[]).failureRate,1);
});
test('对照不把同一人的不同片段当作独立人群',()=>{
 const samples=[{id:'1',person:'a',consensus:['反对']},{id:'2',person:'a',consensus:['反对']}],a=samples.map(s=>({id:s.id,signals:[{label:'反对'}]})),b=samples.map(s=>({id:s.id,signals:[]}));assert.equal(groupedDifference(samples,a,b).ci95,null);
});
