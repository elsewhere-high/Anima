import test from 'node:test';
import assert from 'node:assert/strict';
import {createApp} from '../server.mjs';
import {REVIEW_MODEL} from '../qwen.mjs';

// Exercise the real HTTP route: an upload must bring actual audio words into
// the image/text fusion call, while video-only ablation must not transcribe.
test('uploaded audio is transcribed before visual fusion; missing modalities stay absent',async t=>{
 const calls=[],inputs=[];
 const specialists={start(){},close(){},status(){return {};},available:k=>k==='face',infer:async()=>({faces:1,scores:{}})};
 const server=createApp({specialists,config:{key:'test-key',workspace:'test-space'},realtimeOptions:{specialistFusion:true},
  fetcher:async(_url,options)=>{const body=JSON.parse(options.body);calls.push(body);return Response.json({choices:[{message:{content:'I am not sure.'}}],usage:{prompt_tokens:10,completion_tokens:5,total_tokens:15}});},
  fusionAnalyzer:async input=>{inputs.push(input);return {transcript:'',signals:[],segments:[]};}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));
 const origin=`http://127.0.0.1:${server.address().port}`,status=await(await fetch(origin+'/api/status')).json();
 const headers={'Content-Type':'application/json','Origin':origin,'X-Anima-Token':status.token};
 const input={duration:2,audio:{mimeType:'audio/mpeg',data:'YXVkaW8='},frames:[{t:.5,image:'aW1hZ2U='}]};
 const full=await(await fetch(origin+'/api/analyze',{method:'POST',headers,body:JSON.stringify(input)})).json();
 assert.equal(calls.length,1);assert.equal(calls[0].model,REVIEW_MODEL);
 assert.equal(calls[0].messages[1].content[0].type,'input_audio');
 assert.equal(inputs[0].quality.face,'single');assert.equal(inputs[0].transcript,'I am not sure.');assert.equal(full.transcript,'I am not sure.');assert.equal(full.transcriptionModel,REVIEW_MODEL);
 assert.deepEqual(full.segments,[{start:0,end:2,text:'I am not sure.'}]);
 await fetch(origin+'/api/evaluate',{method:'POST',headers,body:JSON.stringify({mode:'video',input})});
 assert.equal(calls.length,1);assert.equal(inputs[1].transcript,'');assert.equal(inputs[1].audio,null);
 const supplied={...input,transcript:'Existing confirmed words'};
 await fetch(origin+'/api/analyze',{method:'POST',headers,body:JSON.stringify(supplied)});
 assert.equal(calls.length,1);assert.equal(inputs[2].transcript,supplied.transcript);
});
