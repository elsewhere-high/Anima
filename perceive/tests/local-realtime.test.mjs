import test from 'node:test';
import assert from 'node:assert/strict';
import WebSocket from 'ws';
import {createApp} from '../server.mjs';
test('local live transcription works with no remote ASR socket and flushes the final words',async t=>{
 let remote=0;
 const specialists={start(){},close(){},status(){return {asr:{status:'ready'}};},available:k=>k==='asr',infer:async(k,payload)=>{assert.equal(k,'asr');assert.ok(payload.audio);await new Promise(r=>setTimeout(r,50));return {transcript:'local final words',model:'fixture-asr'};}};
 const app=createApp({specialists,config:{key:'fixture-key',workspace:'test'},realtimeOptions:{localAsr:true},upstreamFactory:()=>{remote++;throw Error('remote ASR must not open');},fusionAnalyzer:async input=>({signals:[],observations:[],quality:input.quality})});
 await new Promise(r=>app.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>app.close(r)));
 const origin=`http://127.0.0.1:${app.address().port}`,s=await(await fetch(origin+'/api/status')).json(),events=[];
 const ws=new WebSocket(origin.replace('http','ws')+'/api/realtime',['anima',s.token],{origin});t.after(()=>ws.terminate());
 await new Promise((r,j)=>{const timer=setTimeout(()=>j(Error('ready timeout')),2000);ws.on('message',raw=>{const e=JSON.parse(raw);events.push(e);if(e.type==='ready'){clearTimeout(timer);r();}});});
 ws.send(JSON.stringify({type:'activity',speaking:true}));for(let i=0;i<12;i++)ws.send(Buffer.alloc(3200,0x1f));
 ws.send(JSON.stringify({type:'activity',speaking:false}));ws.send(JSON.stringify({type:'finish'}));
 await new Promise((r,j)=>{const timer=setTimeout(()=>j(Error('finish timeout')),3000);ws.once('close',()=>{clearTimeout(timer);r();});});
 assert.equal(remote,0);const captions=events.filter(e=>e.type==='transcript');assert.equal(captions.at(-1).text,'local final words');assert.equal(captions.at(-1).provisional,false);
 assert.ok(events.findIndex(e=>e.type==='transcript')<events.findIndex(e=>e.type==='session.end'));
});
