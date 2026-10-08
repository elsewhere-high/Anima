import test from 'node:test';
import assert from 'node:assert/strict';
import WebSocket from 'ws';
import {setTimeout as delay} from 'node:timers/promises';
import {realtimeFixture} from './support/realtime-fixture.mjs';

for(const failFast of [false,true])test(`fast delivery ${failFast?'failure preserves the slower path':'publishes before the slower path, with bounded provisional labels'}`,async()=>{
 const events=[];let closed=0;
 const fixture=await realtimeFixture({fusionDelay:700,realtimeOptions:{fastModel:'fixture-fast',fastAnalyzerFactory:()=>({ready:Promise.resolve(),pushAudio(){},pushFrame(){},close(){closed++;},async analyze(input){
  await delay(30);if(failFast)throw new Error('fixture failure');
  return {signals:[{code:'confidence',label:'表达自信',start:0,end:input.duration,confidence:.7,observations:[]},{code:'interest',label:'兴趣',start:0,end:input.duration,confidence:.7,observations:[]}]};
 }})}});
 const status=await(await fetch(fixture.origin+'/api/status')).json();
 const ws=new WebSocket(fixture.origin.replace('http:','ws:')+'/api/realtime',['anima',status.token],{headers:{Origin:fixture.origin}});
 try{
  await new Promise((resolve,reject)=>{ws.on('message',data=>{const e=JSON.parse(data);events.push(e);if(e.type==='ready')resolve();});ws.once('error',reject);});
  ws.send(JSON.stringify({type:'start',offset:0}));
  for(let i=0;i<18;i++){ws.send(Buffer.alloc(3200));ws.send(JSON.stringify({type:'face',faces:1,cues:[]}));await delay(100);}
  await delay(450);
  const slowIndex=events.findIndex(e=>e.type==='result');assert.ok(slowIndex>=0);
  if(failFast){assert.ok(events.some(e=>e.code==='FAST_DELIVERY_UNAVAILABLE'));assert.equal(events.filter(e=>e.type==='fast.result').length,0);}
  else{const fastIndex=events.findIndex(e=>e.type==='fast.result');assert.ok(fastIndex>=0&&fastIndex<slowIndex);const fast=events[fastIndex];assert.deepEqual(fast.signals.map(s=>s.code),['confidence']);assert.equal(fast.signals[0].tentative,true);assert.ok(events.some(e=>e.type==='state'&&e.current.some(s=>s.source==='native_delivery')));}
 }finally{ws.close();await delay(20);await fixture.close();assert.equal(closed,1);}
});

for(const persistent of [false,true])test(`malformed fast window ${persistent?'stops after three consecutive failures':'recovers on fresh media without publishing the bad result'}`,async()=>{
 const events=[],ends=[];let closed=0;
 const fixture=await realtimeFixture({realtimeOptions:{fastAnalyzerFactory:()=>({ready:Promise.resolve(),pushAudio(){},pushFrame(){},close(){closed++;},async analyze(input){
  ends.push(input.end);if(persistent||ends.length===1)throw Object.assign(new Error('bad format'),{code:'INVALID_SOCIAL_OUTPUT'});
  return {signals:[]};
 }})}});
 const status=await(await fetch(fixture.origin+'/api/status')).json();
 const ws=new WebSocket(fixture.origin.replace('http:','ws:')+'/api/realtime',['anima',status.token],{headers:{Origin:fixture.origin}});
 try{
  await new Promise((resolve,reject)=>{ws.on('message',data=>{const e=JSON.parse(data);events.push(e);if(e.type==='ready')resolve();});ws.once('error',reject);});
  ws.send(JSON.stringify({type:'start',offset:0}));
  for(let i=0;i<25;i++){ws.send(Buffer.alloc(3200));ws.send(JSON.stringify({type:'face',faces:1,cues:[]}));await delay(100);}
  assert.ok(events.some(e=>e.type==='result'));
  assert.ok(ends.every((end,i)=>!i||end>ends[i-1]));
  if(persistent){assert.equal(ends.length,3);assert.equal(events.filter(e=>e.type==='fast.result').length,0);assert.equal(events.filter(e=>e.code==='FAST_DELIVERY_UNAVAILABLE').length,1);}
  else{assert.ok(ends.length>=2);assert.ok(events.some(e=>e.type==='fast.result'));assert.equal(events.filter(e=>e.code==='FAST_DELIVERY_WINDOW_DROPPED').length,1);assert.ok(!events.some(e=>e.code==='FAST_DELIVERY_UNAVAILABLE'));}
 }finally{ws.close();await delay(20);await fixture.close();assert.equal(closed,1);}
});

for(const permanent of [false,true])test(`stateless fast requests ${permanent?'stop on denied access':'recover from format and transient failures on fresh input'}`,async()=>{
 const events=[],ends=[];
 const fixture=await realtimeFixture({realtimeOptions:{fastSource:'visual_local_classifier',fastAnalyzerFactory:()=>({ready:Promise.resolve(),pushAudio(){},pushFrame(){},close(){},async analyze(input){
  ends.push(input.end);
  if(permanent)throw Object.assign(Error('denied'),{retryable:false});
  if(ends.length<=3)throw Object.assign(Error('temporary'),{code:ends.length===2?'INVALID_SOCIAL_OUTPUT':'ECONNRESET'});
  return {signals:[]};
 }})}});
 const status=await(await fetch(fixture.origin+'/api/status')).json();
 const ws=new WebSocket(fixture.origin.replace('http:','ws:')+'/api/realtime',['anima',status.token],{headers:{Origin:fixture.origin}});
 try{
  await new Promise((resolve,reject)=>{ws.on('message',data=>{const e=JSON.parse(data);events.push(e);if(e.type==='ready')resolve();});ws.once('error',reject);});
  ws.send(JSON.stringify({type:'start',offset:0}));
  for(let i=0;i<40;i++){ws.send(Buffer.alloc(3200));ws.send(JSON.stringify({type:'face',faces:1,cues:[]}));await delay(100);}
  assert.ok(events.some(e=>e.type==='result'));
  if(permanent){assert.equal(ends.length,1);assert.ok(events.some(e=>e.code==='FAST_DELIVERY_UNAVAILABLE'));}
  else{assert.ok(events.some(e=>e.type==='fast.result'));assert.equal(events.filter(e=>e.code==='FAST_DELIVERY_WINDOW_DROPPED').length,3);assert.ok(!events.some(e=>e.code==='FAST_DELIVERY_UNAVAILABLE'));assert.ok(ends.every((e,i)=>!i||e>ends[i-1]));}
 }finally{ws.close();await delay(20);await fixture.close();}
});
