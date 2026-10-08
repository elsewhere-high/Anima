import test from 'node:test';
import assert from 'node:assert/strict';
import WebSocket from 'ws';
import {setTimeout as delay} from 'node:timers/promises';
import {qwenFailure} from '../qwen.mjs';
import {realtimeFixture} from './support/realtime-fixture.mjs';

test('permanent model denial stops requests, preserves captions and finishes without waiting for the timeout',async()=>{
 const fixture=await realtimeFixture({fusionError:qwenFailure(403,'AccessDenied.Unpurchased')}),events=[];
 const status=await(await fetch(fixture.origin+'/api/status')).json();
 const socket=new WebSocket(fixture.origin.replace('http:','ws:')+'/api/realtime',['anima',status.token],{origin:fixture.origin});
 try{
  await new Promise((resolve,reject)=>{socket.on('message',data=>{const e=JSON.parse(data);events.push(e);if(e.type==='ready')resolve();});socket.once('error',reject);});
  for(let i=0;i<24;i++){socket.send(Buffer.alloc(3200,0x1f));await delay(90);}
  assert.equal(fixture.report.fusionInputs.length,1);
  assert.equal(events.filter(e=>e.code==='MODEL_ACCESS_UNAVAILABLE').length,1);
  assert.ok(events.some(e=>e.type==='transcript'));
  const ended=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('finish waited too long')),2500);socket.once('close',()=>{clearTimeout(timer);resolve();});});
  socket.send(JSON.stringify({type:'finish'}));await ended;
  assert.equal(events.filter(e=>e.type==='session.end').at(-1).reason,'finished');
 }finally{socket.terminate();await fixture.close();}
});

test('configured session duration is enforced by captured media, not just the wall timer',async()=>{
 const fixture=await realtimeFixture({realtimeOptions:{maxSessionSeconds:1}}),events=[];
 const status=await(await fetch(fixture.origin+'/api/status')).json();
 const socket=new WebSocket(fixture.origin.replace('http:','ws:')+'/api/realtime',['anima',status.token],{origin:fixture.origin});
 try{
  await new Promise(resolve=>socket.on('message',raw=>{const e=JSON.parse(raw);events.push(e);if(e.type==='ready')resolve();}));
  const ended=new Promise(resolve=>socket.once('close',resolve));for(let i=0;i<12;i++)socket.send(Buffer.alloc(3200));await ended;
  assert.equal(events.find(e=>e.type==='session.end').reason,'time_limit');
 }finally{socket.terminate();await fixture.close();}
});
