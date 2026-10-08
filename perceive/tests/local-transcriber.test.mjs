import test from 'node:test';
import assert from 'node:assert/strict';
import {LocalTranscriber} from '../local-transcriber.mjs';
function fixture(infer=async input=>({transcript:`at ${input.end}`,model:'test'})){
 const events=[],inputs=[];
 const t=new LocalTranscriber({snapshot:v=>(inputs.push(v),v),infer,onTranscript:v=>events.push(v)});
 return {t,events,inputs};
}
test('causal partials replace the same utterance and finalize at VAD end',async()=>{
 const {t,events,inputs}=fixture();t.activity(true,.5);t.tick(1);await t.pending;
 t.tick(1.4);assert.equal(inputs.length,1);t.tick(2);await t.pending;
 t.activity(false,2.2);await t.finish(2.2);
 assert.equal(new Set(events.map(e=>e.id)).size,1);assert.deepEqual(events.map(e=>e.provisional),[true,true,false]);
 assert.ok(inputs.every(i=>i.end-i.windowSeconds===0));assert.equal(events.at(-1).end,2.2);
 t.activity(true,3);t.tick(3.7);await t.pending;assert.equal(events.at(-1).start,2.4);assert.notEqual(events[0].id,events.at(-1).id);t.close();
});
test('in-flight old drafts cannot become a newer utterance or survive close',async()=>{
 let resolve;const {t,events}=fixture(()=>new Promise(r=>{resolve=r;}));t.activity(true,0);t.tick(1);await Promise.resolve();
 t.activity(false,1.1);t.activity(true,1.5);t.tick(2);resolve({transcript:'old'});await t.pending;
 assert.equal(events[0].id,'local-asr-1');assert.equal(events[0].provisional,true);
 t.tick(2.1);await Promise.resolve();t.close();resolve({transcript:'late'});await t.pending;assert.equal(events.length,1);
});
test('silence does not invoke recognition and long utterances split into bounded causal inputs',async()=>{
 const {t,events,inputs}=fixture();t.tick(10);assert.equal(inputs.length,0);
 t.activity(true,0);t.tick(12);await t.pending;t.tick(13);await t.pending;
 assert.ok(inputs.every(v=>v.windowSeconds<=12));assert.equal(events[0].provisional,false);t.close();
});
