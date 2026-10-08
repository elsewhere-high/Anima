import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeSpecialistSocial,normalizeSpecialistClasses,normalizeSpecialistSparse,normalizeSpecialistReview} from '../specialist-social.mjs';
test('sparse classifier preserves distinct code, support and modality without completing malformed rows',()=>{
 const input={duration:2,quality:{face:'single'},frames:[{}],transcript:'I am unsure'};
 const result=normalizeSpecialistSparse({p:1,s:[[3,2,2],[7,1,4]]},input);
 assert.deepEqual(result,normalizeSpecialistSparse({p:1,s:[{code:3,level:2,evidence:2},{code:7,level:1,evidence:4}]},input));
 assert.deepEqual(normalizeSpecialistSparse({p:1,s:[[3,2,2]]},input),normalizeSpecialistSparse({p:1,s:[3,2,2]},input));
 for(const s of [[3,2],[3,2,2,4],[3,2,2,'visual'],[3,2,8]])assert.throws(()=>normalizeSpecialistSparse({p:1,s},input),e=>e.code==='INVALID_SOCIAL_OUTPUT');
 for(const row of [{code:3,level:2},{code:3,level:'2',evidence:2},{code:3,level:2,evidence:2,guess:true}])assert.throws(()=>normalizeSpecialistSparse({p:1,s:[row]},input),e=>e.code==='INVALID_SOCIAL_OUTPUT');
 assert.deepEqual(result.signals.map(s=>s.code),['confidence','uncertainty']);
 assert.equal(result.signals[1].support,'low');assert.equal(normalizeSpecialistSparse({p:1,s:[]},input).signals.length,0);
 for(const s of [[[3,2]],[[3,2,2],[3,2,2]],[[10,2,2]],[[3,2,0]]])assert.throws(()=>normalizeSpecialistSparse({p:1,s},input));
 for(const raw of [[],{s:[[3,2,2]]},{p:'1',s:[[3,2,2]]}])assert.throws(()=>normalizeSpecialistSparse(raw,input),e=>e.code==='INVALID_SOCIAL_OUTPUT');
});
test('review distinguishes invalid wrapper from unsupported states and accepts complete equivalent evidence fields',()=>{
 const input={duration:2,quality:{face:'single'},frames:[{}],transcript:'I disagree'};
 for(const raw of [[],[{signal_code:'disagreement'}],{s:[]}])assert.throws(()=>normalizeSpecialistReview(raw,input),e=>e.code==='INVALID_SOCIAL_OUTPUT');
 const row=['disagreement',0,1,'medium',['text','visual'],'Says I disagree'];
 const named={signal_code:row[0],onset_seconds:0,end_seconds:1,support_level:'medium',used_modalities:row[4],observed_cue:row[5]};
 assert.deepEqual(normalizeSpecialistReview({p:1,s:[row]},input).signals,normalizeSpecialistReview({p:1,s:[named]},input).signals);
 assert.deepEqual(normalizeSpecialistReview({p:1,s:[row]},input).signals,normalizeSpecialistReview({p:1,s:[{...named,used_modalities:'text, visual'}]},input).signals);
 assert.equal(normalizeSpecialistReview({p:0,s:[row]},input).signals.length,0);
 assert.equal(normalizeSpecialistReview({p:1,s:[{...named,end_seconds:undefined}]},input).signals.length,0);
 assert.equal(normalizeSpecialistReview({p:1,s:[row]},{...input,frames:[]}).signals.length,0);
});
test('fast requests constrain the wrapper and report malformed content without inventing person binding',async()=>{
 const input={duration:2,start:0,end:2,quality:{face:'single'},frames:[{t:1,image:'YQ=='}],transcript:'hello'};
 for(const content of ['[]','{"s":[[3,2,2]]}','not JSON']){
  await assert.rejects(()=>analyzeSpecialistSocial(input,{key:'test',workspace:'test'},null,{compact:'sparse',fetcher:async(_,options)=>{
   const body=JSON.parse(options.body);assert.deepEqual(body.response_format,{type:'json_object'});assert.ok(!body.messages[0].content.includes('use [] if unsupported'));
   return Response.json({choices:[{message:{content}}]});
  }}),e=>e.code==='INVALID_SOCIAL_OUTPUT');
 }
});
test('compact fallback masks distinguish acoustic interpretation from direct sound and absent transcript',()=>{
 const s=Array(10).fill(0),m=Array(10).fill(0);s[3]=2;m[3]=4;
 const input={duration:2,quality:{face:'single'},frames:[{}],local:[]};
 assert.equal(normalizeSpecialistClasses({p:1,s,m},input).signals.length,0);
 assert.equal(normalizeSpecialistClasses({p:1,s,m},{...input,transcript:'certain'}).signals.length,1);
 m[3]=1;assert.equal(normalizeSpecialistClasses({p:1,s,m},input).signals.length,0);
 assert.equal(normalizeSpecialistClasses({p:1,s,m},{...input,local:[{source:'specialist',modality:'声音'}]}).signals[0].observations[0].source,'acoustic_measurement_interpretation');
 assert.throws(()=>normalizeSpecialistClasses({p:1,s:[2],m:[2]},input));
});
test('image and specialist fusion sends no waveform and rejects invented direct listening',async()=>{
 const input={duration:2,start:0,end:2,audio:{data:'PRIVATE_WAVEFORM'},frames:[{t:1,image:'YQ=='}],quality:{face:'single'},transcript:'I am not sure',local:[{modality:'声音',source:'specialist',model:'test',text:'repetition observed',start:0,end:2}]};
 const response={p:1,s:[['hesitation',0,2,'medium','acoustic','repetition observed'],['confidence',0,2,'medium','audio','I heard assured tone']]};
 const result=await analyzeSpecialistSocial(input,{key:'test',workspace:'test'},null,{fetcher:async(_,options)=>{
  const b=JSON.parse(options.body);assert.equal(b.model,'qwen3.7-flash');assert.ok(!options.body.includes('PRIVATE_WAVEFORM'));assert.ok(!b.messages[1].content.some(c=>c.type==='input_audio'));
  return new Response(JSON.stringify({choices:[{message:{content:JSON.stringify(response)}}]}),{headers:{'Content-Type':'application/json'}});
 }});
 assert.deepEqual(result.signals.map(s=>s.code),['hesitation']);assert.equal(result.rawAudioReceived,false);assert.equal(result.signals[0].observations[0].source,'acoustic_measurement_interpretation');
});
