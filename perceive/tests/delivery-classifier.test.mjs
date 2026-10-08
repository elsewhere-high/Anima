import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeDeliveryClasses,normalizeSocialClasses,SOCIAL_CLASS_ORDER} from '../delivery-classifier.mjs';
const input={duration:1.5,audio:{data:'test'},frames:[{image:'test'}],quality:{face:'single'}};
test('ten-signal classifier preserves every independent code and refuses truncated vectors',()=>{
 for(let i=0;i<SOCIAL_CLASS_ORDER.length;i++){
  const s=Array(10).fill(0),m=Array(10).fill(0);s[i]=2;m[i]=3;
  assert.deepEqual(normalizeSocialClasses({p:1,s,m},input).signals.map(v=>v.code),[SOCIAL_CLASS_ORDER[i]]);
  assert.equal(normalizeSocialClasses({p:1,s,m},{...input,quality:{face:'multiple'}}).signals.length,0);
 }
 assert.throws(()=>normalizeSocialClasses({p:1,s:[2,0],m:[3,0]},input));
});
test('ordinal classifier publishes provisional window estimates, never invented precise cues',()=>{
 const result=normalizeDeliveryClasses({p:1,s:[2,1],m:[3,1]},input);
 assert.deepEqual(result.signals.map(s=>s.code),['confidence','hesitation']);
 assert.ok(result.signals.every(s=>s.tentative&&s.temporalResolution==='window'&&s.start===0&&s.end===1.5));
 assert.equal(result.signals[0].observations[0].source,'provisional_classifier');
 assert.equal(normalizeDeliveryClasses({p:1,s:[0,0],m:[0,0]},input).signals.length,0);
 assert.deepEqual(normalizeDeliveryClasses({p:1,s:[2,0],m:3},input).signals.map(s=>s.code),['confidence']);
 assert.equal(normalizeDeliveryClasses({p:1,s:[0,0],m:0},input).signals.length,0);
 assert.throws(()=>normalizeDeliveryClasses({p:1,s:[2,2],m:3},input));
});
test('classifier rejects incomplete scores and unavailable or unbound modalities',()=>{
 for(const raw of [{p:1,s:[2],m:[1,1]},{p:1,s:[2,0]},{p:1,s:[4,0],m:[1,0]},{p:1,s:[.7,0],m:[1,0]}])assert.throws(()=>normalizeDeliveryClasses(raw,input));
 for(const raw of [{p:1,s:[2,0],m:[0,0]},{p:0,s:[2,0],m:[3,0]},{p:2,s:[2,0],m:[3,0]}])assert.equal(normalizeDeliveryClasses(raw,input).signals.length,0);
 assert.equal(normalizeDeliveryClasses({p:1,s:[2,0],m:[1,0]},{...input,quality:{face:'single',quiet:true}}).signals.length,0);
 assert.equal(normalizeDeliveryClasses({p:1,s:[2,0],m:[2,0]},{...input,quality:{face:'absent'}}).signals.length,0);
});
