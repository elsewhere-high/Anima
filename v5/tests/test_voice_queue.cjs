// Exercise asynchronous turn ownership without a microphone or model.
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,{value:'',style:{}});return elements.get(id)};
const pending=[];const submitted=[];
let spoken=0;
const sandbox={console,Float32Array,Uint8Array,ArrayBuffer,DataView,AbortController,
 performance:{now:()=>0},setTimeout,clearTimeout,btoa:s=>Buffer.from(s,'binary').toString('base64'),
 document:{getElementById:element},TurnDetector:require('../web/turn_detector.js'),
 token:'',session:'test',chatBusy:false,notify:()=>{},stopCamera:()=>{},
 fetch:async()=>({ok:true,json:async()=>({text:'测试',quality:{requires_repeat:false}})}),
 submitSpeech:async text=>{submitted.push(text);return new Promise(resolve=>pending.push(resolve))},
 SpeechSynthesisUtterance:function(text){this.text=text},
 window:{addEventListener:()=>{},speechSynthesis:{cancel:()=>{},getVoices:()=>[{localService:true,lang:'zh-CN'}],speak:u=>{spoken++;u.onend()}},setupController:{ready:()=>true}}
};
let code=fs.readFileSync(require.resolve('../web/voice.js'),'utf8');
code=code.replace('window.voiceConversation={','window.__test={processTurn,activate:()=>{active=true},record:()=>{recording=true},snapshot:()=>({turnBusy,queued:!!queuedTurn,recording,phase})};window.voiceConversation={');
vm.runInNewContext(code,sandbox);
element('voiceChoice').value='device';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const t=sandbox.window.__test;t.activate();
 const first=t.processTurn([new Float32Array(1600)],16000);await tick();
 assert.equal(submitted.length,1);
 await t.processTurn([new Float32Array(1600)],16000);
 assert.equal(t.snapshot().queued,true);assert.equal(submitted.length,1);
 pending.shift()({response:'第一句'});await first;await tick();
 assert.equal(spoken,0,'queued speech must take precedence over playback');
 assert.equal(submitted.length,2,'next turn should run once previous request completes');
 t.record();pending.shift()({response:'第二句'});await tick();
 assert.equal(t.snapshot().recording,true,'speech begun while thinking must not be discarded');
 assert.equal(spoken,0);
 sandbox.window.voiceConversation.stop();t.activate();
 const third=t.processTurn([new Float32Array(1600)],16000);await tick();
 await t.processTurn([new Float32Array(1600)],16000);
 sandbox.window.voiceConversation.stop();pending.shift()({response:'过期回复'});await third;await tick();
 assert.equal(submitted.length,3,'stop must cancel the queued turn');
 assert.equal(spoken,0,'stopped response must not play');
 assert.equal(t.snapshot().turnBusy,false);
 console.log('voice queue: serialized turns, capture during thinking, suppression of stale playback, stop cancellation passed');
})().catch(error=>{console.error(error);process.exitCode=1});
