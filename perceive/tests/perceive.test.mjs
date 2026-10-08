import test from 'node:test';
import assert from 'node:assert/strict';
import {SIGNALS,normalizeResult,validateInput,analyzeGemini} from '../perceive.mjs';
import {createApp} from '../server.mjs';
import {encodeWav} from '../public/media.js';
import {locateTime,cases,totalDuration} from '../public/cases.js';
import http from 'node:http';
import {readFile} from 'node:fs/promises';

const input={duration:6,frames:[{image:'aW1hZ2U=',t:1}],audio:{mimeType:'audio/wav',data:'YXVkaW8='},context:[{transcript:'当前提议',signals:['赞同']}],face:[]};
const signal={label:'不确定',start:1,end:2,anchor:'拿不准',target:'数字',evidence:'原话明确表达拿不准',modalities:['语意'],tentative:false,confidence:.8};
test('20个信号；拒绝编造说谎、无对象立场与无证据标签',()=>{
  assert.equal(SIGNALS.length,20);
  const result=normalizeResult({transcript:'我拿不准这个数字',signals:[signal,{...signal,label:'说谎'},{...signal,label:'反对',target:''},{...signal,evidence:''},{...signal,label:'反话',modalities:['画面']}]},6);
  assert.equal(result.signals.length,1);assert.equal(result.signals[0].label,'不确定');
});
test('时间限制在窗口内；锚点必须在原话中，数据可安全显示',()=>{
  const result=normalizeResult({transcript:'当前原话',signals:[{...signal,start:-10,end:100,anchor:'不存在'}],segments:[{start:0,end:5,text:'不存在'},{start:1,end:100,text:'当前原话'}]},6);
  assert.deepEqual([result.signals[0].start,result.signals[0].end,result.signals[0].anchor],[0,6,'']);assert.equal(result.segments.length,1);assert.equal(result.segments[0].end,6);
});
test('音视频输入与短期上下文有界',()=>{
  assert.throws(()=>validateInput({}),/提供声音/);assert.throws(()=>validateInput({...input,audio:{mimeType:'text/html',data:'bad'}}));assert.throws(()=>validateInput({...input,frames:[{image:'<script>',t:0}]}));
  const actual=validateInput({...input,context:Array.from({length:50},()=>({transcript:'x'.repeat(500),signals:['说谎','赞同']}))});assert.equal(actual.context.length,6);assert.equal(actual.context[0].transcript.length,200);assert.deepEqual(actual.context[0].signals,['赞同']);
});
test('真实适配器发送原始声音和时序画面，解析与过滤结构化结果（模拟外部传输）',async()=>{
  let called=0;
  const result=await analyzeGemini(validateInput(input),{key:'test-secret',model:'gemini-3.8-flash'},undefined,async(url,options)=>{
    called++;assert.ok(url.startsWith('https://generativelanguage.googleapis.com/'));assert.equal(options.headers['x-goog-api-key'],'test-secret');const body=JSON.parse(options.body);assert.equal(body.contents[0].parts.filter(p=>p.inlineData).length,2);assert.ok(body.systemInstruction.parts[0].text.includes('不调用个人历史'));
    return Response.json({candidates:[{content:{parts:[{text:JSON.stringify({transcript:'我拿不准',segments:[],signals:[signal],scene:'',unknown:''})}]}}]});
  });assert.equal(called,1);assert.equal(result.transcript,'我拿不准');assert.equal(result.signals[0].label,'不确定');
});
test('模型错误不回显服务商响应或密钥',async()=>{
  await assert.rejects(()=>analyzeGemini(validateInput(input),{key:'secret',model:'m'},undefined,async()=>new Response('secret',{status:403})),/HTTP 403/);
  await assert.rejects(()=>analyzeGemini(validateInput(input),{key:'secret',model:'m'},undefined,async()=>Response.json({candidates:[]})),/有效结果/);
});
test('本地服务：来源保护、无密钥拒绝假结果、Range播放与路径限制',async t=>{
  const server=createApp({config:{key:'',model:'gemini-3.8-flash'}});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const origin=`http://127.0.0.1:${server.address().port}`;
  const status=await(await fetch(origin+'/api/status')).json();assert.equal(status.configured,false);assert.equal(status.key,undefined);
  assert.equal((await fetch(origin+'/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status,403);
  const headers={'Content-Type':'application/json','Origin':origin,'X-Anima-Token':status.token};
  const response=await fetch(origin+'/api/analyze',{method:'POST',headers,body:JSON.stringify(input)});assert.equal(response.status,503);assert.equal((await response.json()).code,'MODEL_NOT_CONFIGURED');
  const partial=await fetch(origin+'/styles.css',{headers:{Range:'bytes=0-31'}});assert.equal(partial.status,206);const received=Buffer.from(await partial.arrayBuffer());assert.deepEqual(received,(await readFile(new URL('../public/styles.css',import.meta.url))).subarray(0,32));assert.ok(partial.headers.get('content-range').startsWith('bytes 0-31/'));
  assert.equal((await fetch(origin+'/%2e%2e%2fserver.mjs')).status,403);
  const badHost=await new Promise(resolve=>{const req=http.get(origin+'/api/status',{headers:{Host:'evil.test:123'}},res=>{res.resume();resolve(res.statusCode)});req.on('error',()=>resolve(0));});assert.equal(badHost,403);
});
test('本地 HTTP 到模型适配器端到端（模拟模型），密钥不返回客户端',async t=>{
  const server=createApp({config:{key:'',workspace:''},fetcher:async()=>Response.json({choices:[{message:{content:JSON.stringify({transcript:'我拿不准',signals:[{...signal,scope:'current_self',basis:'explicit',refs:['o1']}],speakerBound:true,observations:[{id:'o1',modality:'语意',text:'我拿不准',start:1,end:2}],segments:[],scene:'',unknown:''})}}]})});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));const origin=`http://127.0.0.1:${server.address().port}`,status=await(await fetch(origin+'/api/status')).json(),headers={'Content-Type':'application/json',Origin:origin,'X-Anima-Token':status.token};
  const configured=await(await fetch(origin+'/api/config',{method:'POST',headers,body:JSON.stringify({key:'only-test-key',workspace:'test-space'})})).json();assert.equal(configured.configured,true);assert.equal(JSON.stringify(configured).includes('only-test-key'),false);
  const response=await fetch(origin+'/api/analyze',{method:'POST',headers,body:JSON.stringify(input)});assert.equal(response.status,200);const result=await response.json();assert.equal(result.source,'model');assert.equal(result.signals[0].label,'不确定');
});
test('音频编码与案例跨段定位',async()=>{
  const blob=encodeWav(new Float32Array([0,1,-1]));const bytes=await blob.arrayBuffer(),v=new DataView(bytes);assert.equal(new TextDecoder().decode(bytes.slice(0,4)),'RIFF');assert.equal(v.getUint32(24,true),16000);assert.equal(v.getInt16(46,true),32767);assert.equal(v.getInt16(48,true),-32768);
  assert.equal(locateTime(cases[0].duration+.1).index,1);assert.equal(locateTime(totalDuration).index,4);
});
