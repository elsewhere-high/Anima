import test from 'node:test';
import assert from 'node:assert/strict';
import {endpoints,analyzeQwen,transcriptPreview,qwenError,realtimeErrorCode,REALTIME_MODEL,DEFAULT_ENDPOINT} from '../qwen.mjs';

test('flat gateway rejection is identified without exposing upstream message or request details',()=>{
 const e={code:'AccessDenied.Unpurchased',message:'private upstream details',request_id:'private'};
 assert.equal(realtimeErrorCode(e),'AccessDenied.Unpurchased');
 assert.match(qwenError(0,realtimeErrorCode(e)),/未获准/);
 assert.ok(!qwenError(0,realtimeErrorCode(e)).includes('private'));
 assert.equal(realtimeErrorCode({type:'session.created',session:{}}),null);
 assert.equal(realtimeErrorCode({type:'error',error:{code:'Unauthorized'}}),'Unauthorized');
});
import {PcmEncoder} from '../public/pcm.js';
import WebSocket from 'ws';
import {realtimeFixture} from './support/realtime-fixture.mjs';

test('百炼地址绑定官方业务空间；拒绝重定向、凭证和非官方域名',()=>{
  assert.equal(endpoints('space123').realtime,'wss://space123.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime');
  assert.equal(endpoints(DEFAULT_ENDPOINT).realtime,'wss://maas.qianwenaiapi.com/api-ws/v1/realtime');
  assert.equal(endpoints('https://space123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1').review,'https://space123.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions');
  for(const url of ['https://evil.test/','https://user:secret@space123.cn-beijing.maas.aliyuncs.com/','https://space123.cn-beijing.maas.aliyuncs.com/?key=secret','wss://space123.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model=m','https://space123.cn-beijing.maas.aliyuncs.com:444/'])assert.throws(()=>endpoints(url));
});
test('千问回看适配器发送原始声音和画面，并解析跨字节的流式 JSON',async()=>{
  const result={transcript:'拿不准',segments:[],signals:[],scene:'',unknown:''};
  const wire='data: '+JSON.stringify({choices:[{delta:{content:JSON.stringify(result)}}]})+'\n\ndata: [DONE]\n\n';
  const bytes=new TextEncoder().encode(wire);
  const response=await analyzeQwen({duration:2,context:[],face:[],audio:{mimeType:'audio/wav',data:'YQ=='},frames:[{t:1,image:'Yg=='}]},{key:'only-test-key',workspace:'test-space'},undefined,async(url,options)=>{
    assert.equal(url,endpoints('test-space').review);assert.equal(options.redirect,'error');assert.equal(options.headers.Authorization,'Bearer only-test-key');
    const body=JSON.parse(options.body);assert.equal(body.model,'qwen3.8-omni-flash');assert.equal(body.reasoning_effort,'none');assert.equal(body.stream,true);assert.equal(body.messages[1].content.filter(c=>c.type==='input_audio'||c.type==='image_url').length,2);
    return new Response(new ReadableStream({start(c){for(let i=0;i<bytes.length;i+=7)c.enqueue(bytes.slice(i,i+7));c.close();}}),{headers:{'content-type':'text/event-stream'}});
  });assert.equal(response.transcript,result.transcript);
});
test('边到达边显示原话；不把半截 JSON 或错误响应显示到画面',()=>{
  assert.equal(transcriptPreview('{"transcript":"我拿不'), '我拿不');
  assert.equal(transcriptPreview('{"transcript":"\\u4f'), '');
  assert.equal(transcriptPreview('{"signals":[]}'), '');
  assert.ok(!qwenError(401,'secret-key').includes('secret-key'));assert.match(qwenError(503),/暂时不可用/);
});
test('连续音频重采样：48k 和 44.1k 均每秒产生 16k PCM，分块边界不丢样',()=>{
  for(const rate of [48000,44100,16000]){
    const samples=Float32Array.from({length:rate},(_,i)=>i<rate/2?1:-1);
    const encoder=new PcmEncoder(rate),chunks=[];
    for(let i=0;i<samples.length;i+=128)chunks.push(...encoder.push(samples.subarray(i,i+128)));
    const combined=Buffer.concat(chunks.map(x=>Buffer.from(x)));assert.equal(combined.length,32000);assert.equal(combined.readInt16LE(0),32767);assert.equal(combined.readInt16LE(31998),-32768);
  }
});
test('实时端到端：长连接持续音视频、流式字幕、判断结果、结束前冲刷最后输入',async t=>{
  const fixture=await realtimeFixture();t.after(()=>fixture.close());
  const status=await(await fetch(fixture.origin+'/api/status')).json();
  const socket=new WebSocket(fixture.origin.replace('http','ws')+'/api/realtime',['anima',status.token],{origin:fixture.origin});
  t.after(()=>socket.terminate());
  const events=[],waitFor=type=>new Promise((resolve,reject)=>{
    if(events.some(e=>e.type===type))return resolve(events.find(e=>e.type===type));
    const timer=setTimeout(()=>{socket.off('message',listen);reject(new Error('等待 '+type+' 超时'));},3000);
    function listen(data){const event=JSON.parse(data);if(event.type===type){clearTimeout(timer);socket.off('message',listen);resolve(event);}}
    socket.on('message',listen);
  });
  socket.on('message',data=>events.push(JSON.parse(data)));await waitFor('ready');
  assert.equal(status.model,REALTIME_MODEL);assert.ok(fixture.report.requests[0].url.includes('test-space.cn-beijing.maas.aliyuncs.com'));assert.ok(fixture.report.requests[0].keyPresent);
  assert.equal(fixture.report.session.turn_detection,null);assert.deepEqual(fixture.report.session.modalities,['text']);assert.equal(fixture.report.session.audio.input.format.sample_rate,16000);
  socket.send(JSON.stringify({type:'start',offset:.3}));
  for(let i=0;i<12;i++)socket.send(Buffer.alloc(3200,0x1f));
  socket.send(JSON.stringify({type:'image',image:'YQ=='}));socket.send(JSON.stringify({type:'face',faces:1,cues:[]}));socket.send(JSON.stringify({type:'commit'}));
  const preview=await waitFor('transcript');assert.equal(preview.text,'我拿不准这个数字');
  // Continue streaming while inference is still in flight, then finish safely.
  for(let i=0;i<12;i++)socket.send(Buffer.alloc(3200,0x1f));
  socket.send(JSON.stringify({type:'finish'}));
  await new Promise(resolve=>socket.once('close',resolve));
  const results=events.filter(e=>e.type==='result');assert.equal(results.length,2);assert.equal(results[0].start,.3);assert.equal(results[0].end,1.5);assert.equal(results[0].signals[0].label,'不确定');assert.equal(fixture.report.audioChunks,24);assert.equal(fixture.report.images,0);assert.equal(fixture.report.commits,2);
  assert.equal(JSON.stringify(events).includes('fixture-only-key'),false);
  assert.equal(fixture.report.responses,0);assert.ok(fixture.report.fusionInputs.every(i=>i.audio&&i.frames.length&&i.local.length));assert.ok(events.some(e=>e.type==='state'&&e.current.length));
  const after=await(await fetch(fixture.origin+'/api/status')).json();assert.equal(after.apiVerified,true);
});
test('实时连接拒绝跨站和错误令牌',async t=>{
  const fixture=await realtimeFixture();t.after(()=>fixture.close());
  const status=await(await fetch(fixture.origin+'/api/status')).json();
  for(const [origin,token] of [['http://evil.test',status.token],[fixture.origin,'wrong']]){
    const code=await new Promise(resolve=>{const socket=new WebSocket(fixture.origin.replace('http','ws')+'/api/realtime',['anima',token],{origin});socket.on('unexpected-response',(_r,res)=>{resolve(res.statusCode);res.resume();socket.terminate();});socket.on('error',()=>{});});assert.equal(code,403);
  }
  assert.equal(fixture.report.requests.length,0);
});
test('机器人订阅只收到状态与文本事件，不含密钥或原始音视频；结束清空状态',async t=>{
  const fixture=await realtimeFixture();t.after(()=>fixture.close());const {token}=await(await fetch(fixture.origin+'/api/status')).json();
  const ws=path=>new WebSocket(fixture.origin.replace('http','ws')+path,['anima',token],{origin:fixture.origin});
  const subscriber=ws('/api/events'),events=[];subscriber.on('message',d=>events.push(JSON.parse(d)));await new Promise(r=>subscriber.once('open',r));
  const sender=ws('/api/realtime');t.after(()=>{subscriber.terminate();sender.terminate();});
  await new Promise(resolve=>sender.on('message',d=>{if(JSON.parse(d).type==='ready')resolve();}));
  for(let i=0;i<12;i++)sender.send(Buffer.alloc(3200,0x1f));sender.send(JSON.stringify({type:'face',faces:1,cues:[]}));sender.send(JSON.stringify({type:'finish'}));await new Promise(r=>sender.once('close',r));
  assert.ok(events.some(e=>e.type==='session.start'));assert.ok(events.some(e=>e.type==='state'&&e.current.length));assert.ok(events.some(e=>e.type==='session.end'));assert.equal(events.filter(e=>e.type==='state').at(-1).current.length,0);assert.ok(!JSON.stringify(events).includes('fixture-only-key'));assert.ok(events.every(e=>!e.audio&&!e.frames));subscriber.close();
});
