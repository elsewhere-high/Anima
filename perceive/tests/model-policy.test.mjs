import test from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createApp} from '../server.mjs';
import {analyzeSpecialistSocial} from '../specialist-social.mjs';
import {modelUsage} from '../model-policy.mjs';

test('selected free-quota candidate is really called and reported usage is counted without guessing remaining credit',async()=>{
  let called;
  await analyzeSpecialistSocial({duration:1,start:0,end:1,frames:[],local:[]},{key:'fixture',workspace:'test',perceptionModel:'qwen3.8-27b'},null,{compact:'sparse',fetcher:async(_,options)=>{
    called=JSON.parse(options.body);
    return new Response('data: '+JSON.stringify({choices:[{delta:{content:'{"p":0,"s":[]}'}}]})+'\n\ndata: '+JSON.stringify({choices:[],usage:{prompt_tokens:100,completion_tokens:10,total_tokens:110}})+'\n\ndata: [DONE]\n',{headers:{'Content-Type':'text/event-stream'}});
  }});
  assert.equal(called.model,'qwen3.8-27b');assert.equal(called.stream_options.include_usage,true);
  assert.equal(modelUsage().models['qwen3.8-27b'].totalTokens,110);
  assert.equal(modelUsage().remainingFreeTokens,null);
  await assert.rejects(()=>analyzeSpecialistSocial({},{perceptionModel:'qwen-image-3.0'},null,{fetcher:()=>{throw Error('must not send');}}),/图像理解/);
});

for(const localAsr of [true,false])test(`model setting preserves the key and reports ${localAsr?'local':'cloud'} transcription with actual fusion models`,async()=>{
  const app=createApp({config:{key:'fixture-secret',workspace:'test'},realtimeOptions:{localAsr,specialistFusion:true},specialists:{start(){},close(){},status(){return{};}}});
  app.listen(0,'127.0.0.1');await once(app,'listening');
  const base=`http://127.0.0.1:${app.address().port}`;
  try{
    const before=await(await fetch(base+'/api/status')).json();
    const headers={Origin:base,'Content-Type':'application/json','X-Anima-Token':before.token};
    const set=await fetch(base+'/api/config',{method:'POST',headers,body:JSON.stringify({key:'',perceptionModel:'qwen3.8-max'})});
    assert.equal(set.status,200);const value=await set.json();assert.equal(value.model,localAsr?'SenseVoiceSmall':'qwen3.8-omni-flash-realtime');assert.equal(value.reviewModel,'qwen3.8-max');assert.equal(value.configured,true);assert.ok(!JSON.stringify(value).includes('fixture-secret'));
    assert.equal((await(await fetch(base+'/api/status')).json()).reviewModel,'qwen3.8-max');
    assert.equal((await fetch(base+'/api/config',{method:'POST',headers,body:JSON.stringify({perceptionModel:'wan3.0-video'})})).status,400);
    assert.equal((await(await fetch(base+'/api/status')).json()).reviewModel,'qwen3.8-max');
    const pair=await fetch(base+'/api/config',{method:'POST',headers,body:JSON.stringify({fastPerceptionModel:'qwen3.7-flash-2026-07-15',perceptionModel:'qwen3.8-max-0902'})});
    assert.equal(pair.status,200);const paired=await pair.json();assert.equal(paired.fastModel,'qwen3.7-flash-2026-07-15');assert.equal(paired.reviewModel,'qwen3.8-max-0902');
    assert.equal((await fetch(base+'/api/config',{method:'POST',headers,body:JSON.stringify({fastPerceptionModel:'wan3.0-video'})})).status,400);
    const status=await(await fetch(base+'/api/status')).json();assert.equal(status.fastModel,'qwen3.7-flash-2026-07-15');assert.equal(status.reviewModel,'qwen3.8-max-0902');
  }finally{app.closeAllConnections();await new Promise(r=>app.close(r));}
});

test('fast and review models receive their assigned calls without silently switching lanes',async()=>{
 const called=[],config={key:'fixture',workspace:'test',fastPerceptionModel:'qwen3.7-flash-2026-07-15',perceptionModel:'qwen3.8-max-0902'};
 for(const compact of ['sparse',false])await analyzeSpecialistSocial({duration:1,start:0,end:1,frames:[],local:[]},config,null,{compact,fetcher:async(_,options)=>{called.push(JSON.parse(options.body).model);return Response.json({choices:[{message:{content:'{"p":0,"s":[]}'}}]});}});
 assert.deepEqual(called,['qwen3.7-flash-2026-07-15','qwen3.8-max-0902']);
});
