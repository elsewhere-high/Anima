import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeSocial,analyzeSocial,parseSocial,mergeSocialHeads} from '../social.mjs';
import {completionText} from '../qwen.mjs';
const input={duration:2,start:0,end:2,audio:{data:'YQ=='},frames:[{t:.5,image:'YQ=='}],quality:{face:'single'},face:[],local:[],context:[]};
test('social detector preserves audible word-search evidence without inventing a semantic statement',()=>{
 const r=normalizeSocial({p:1,s:[['hesitation',.2,1.8,'medium','audio','repeated false starts and interrupted articulation']]},input);
 assert.equal(r.signals[0].label,'犹豫');assert.deepEqual(r.signals[0].modalities,['声音']);
 assert.equal(normalizeSocial({p:0,s:[['confidence',0,2,'high','visual','steady gaze']]},input).signals.length,0);
 assert.equal(normalizeSocial({p:1,s:[['confidence',0,3,'high','visual','steady gaze']]},input).signals.length,0);
 assert.equal(normalizeSocial({p:1,s:[['confidence',0,2,'high','audio','firm voice']]},{...input,audio:null}).signals.length,0);
 for(const face of ['absent','multiple','unavailable'])assert.equal(normalizeSocial({p:1,s:[['confidence',0,2,'high','audio','firm voice']]},{...input,quality:{face}}).signals.length,0);
});
test('final stream token without a newline is not lost',async()=>{
 const response=new Response('data: '+JSON.stringify({choices:[{delta:{content:'}'}}]}),{headers:{'content-type':'text/event-stream'}});
 assert.equal(await completionText(response),'}');
});
test('native named fields preserve equivalent evidence and reject incomplete model rows',()=>{
 const row={code:'hesitation',onset:0,end:.8,level:'medium',modalities:['audio'],cue:'pause and repeated restarts'};
 const named=normalizeSocial({p:1,s:[row]},input);
 const array=normalizeSocial({p:1,s:[['hesitation',0,.8,'medium','audio',row.cue]]},input);
 assert.deepEqual(named,array);
 for(const missing of ['code','onset','end','level','modalities','cue']){
   const incomplete={...row};delete incomplete[missing];
   assert.equal(normalizeSocial({p:1,s:[incomplete]},input).signals.length,0);
 }
 const missingCode=[0,1,'high','audio+visual','firm assured delivery with clear conviction'];
 assert.equal(normalizeSocial({p:1,s:[missingCode]},input).signals.length,0);
 assert.equal(normalizeSocial({p:1,s:[{...row,code:'unknown'}]},input).signals.length,0);
 assert.equal(normalizeSocial({p:1,s:[row]},{...input,quality:{face:'single',quiet:true}}).signals.length,0);
});
test('only a complete compact array can recover a missing outer brace',()=>{
 assert.deepEqual(parseSocial('{"p":1,"s":[]'),{p:1,s:[]});
 assert.throws(()=>parseSocial('{"p":1,"s":[["confidence",0,2,"high","audio","firm delivery"]'));
 assert.throws(()=>parseSocial('{"p":1,"s":[["confidence",0,2,"high","audio","firm'));
});
test('compact stream emits completed rows before final JSON and preserves modality evidence',async()=>{
 const packets=[];const result=await analyzeSocial(input,{workspace:'test',key:'test'},undefined,{onPartial:r=>packets.push(r),fetcher:async()=>new Response(new ReadableStream({start(c){for(const text of ['{"p":1,"s":[["confidence",0,1.8,"medium","audio+visual","steady speech and directed gesture"]',']}'])c.enqueue(new TextEncoder().encode('data: '+JSON.stringify({choices:[{delta:{content:text}}]})+'\n\n'));c.close();}}),{headers:{'content-type':'text/event-stream'}})});
 assert.equal(packets.length,1);assert.equal(packets[0].partial,true);assert.equal(result.signals[0].label,'表达自信');assert.equal(result.signals[0].observations.length,2);
});
test('focused passes preserve concurrent states and unique references without pretending independent models',()=>{
 const delivery=normalizeSocial({p:1,s:[['confidence',0,2,'high','audio','firm steady delivery']]},input);
 const attitude=normalizeSocial({p:1,s:[['frustration',.4,2,'medium','audio+text','currently complaining about repeated failed attempts']]},input);
 const r=mergeSocialHeads({delivery,attitude});
 assert.deepEqual(r.signals.map(s=>s.code),['confidence','frustration']);
 assert.equal(new Set(r.observations.map(o=>o.id)).size,r.observations.length);
 assert.equal(r.method,'two-focused-passes-same-base-model');
 assert.equal(mergeSocialHeads({delivery,attitude:{...attitude,speakerBound:false}}).signals.length,0);
 assert.equal(mergeSocialHeads({delivery:{...delivery,signals:[],unknown:'当前证据不足'},attitude}).unknown,'');
});
