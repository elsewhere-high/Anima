import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {NativeSocialSession} from '../native-social.mjs';
import {WindowScheduler} from '../window-scheduler.mjs';
class FakeSocket extends EventEmitter {
  constructor(){super();this.readyState=1;this.bufferedAmount=0;this.sent=[];queueMicrotask(()=>this.deliver({type:'session.created'}));}
  deliver(event){this.emit('message',Buffer.from(JSON.stringify(event)));}
  send(raw){
    const event=JSON.parse(raw);this.sent.push(event);
    if(event.type==='session.update')queueMicrotask(()=>this.deliver({type:'session.updated'}));
    if(event.type==='input_audio_buffer.commit')queueMicrotask(()=>this.deliver({type:'input_audio_buffer.committed'}));
    if(event.type==='response.create')queueMicrotask(()=>{
      this.deliver({type:'response.text.delta',delta:'{"p":1,"s":[["confidence",0,0.5,"medium","audio+visual","firm speech and direct gaze"]'});
      this.deliver({type:'response.text.delta',delta:']}'});
      this.deliver({type:'response.done',response:{status:'completed'}});
    });
  }
  close(){this.readyState=3;this.emit('close');}
  terminate(){this.close();}
}
test('persistent path sends media once, commits the bound prefix, streams rows and closes cleanly',async()=>{
  const socket=new FakeSocket(),session=new NativeSocialSession({workspace:'test',key:'test'},{socketFactory:()=>socket});
  await session.ready;
  const pcm=Buffer.alloc(16000);session.pushAudio(pcm,0,.5);session.pushFrame({image:'YQ=='},.5);
  const partial=[];const result=await session.analyze({start:0,end:.5,duration:.5,audio:{data:'test'},quality:{face:'single'}},null,undefined,{onPartial:r=>partial.push(r)});
  assert.equal(result.signals[0].code,'confidence');assert.equal(partial.length,1);assert.equal(result.nativeInput.frames,1);
  assert.equal(socket.sent.filter(e=>e.type==='input_audio_buffer.append').length,1);
  const commit=socket.sent.findIndex(e=>e.type==='input_audio_buffer.commit'),respond=socket.sent.findIndex(e=>e.type==='response.create');
  assert.ok(commit<respond);session.close();assert.equal(socket.readyState,3);
});
test('finer clock starts at half a second and cannot grow an unbounded queue',()=>{
  const s=new WindowScheduler({hop:.5,concurrency:3,firstEnd:.5});
  assert.equal(s.reserve(.4),null);assert.ok(s.reserve(.5));assert.ok(s.reserve(1));assert.ok(s.reserve(1.5));assert.equal(s.reserve(2),null);
  s.complete(1);assert.equal(s.reserve(3).end,3);s.close();
});
