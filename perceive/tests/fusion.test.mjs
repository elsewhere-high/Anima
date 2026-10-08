import test from 'node:test';
import assert from 'node:assert/strict';
import {EvidenceBuffer,audioFeatures,wavFromPcm} from '../evidence.mjs';
import {normalizeFusion,completedArray,analyzeFusion} from '../fusion.mjs';
import {StateEngine} from '../state-engine.mjs';
import {LiveViewState,replayView} from '../public/live-state.js';

const input={start:0,end:5,duration:5,audio:{mimeType:'audio/wav',data:'YQ=='},frames:[{t:1,image:'YQ=='}],context:[],local:[],quality:{face:'single'}};
const raw=(label='反对',text='第二项我不同意')=>({speakerBound:true,transcript:text,observations:[{id:'o1',modality:'语意',text,start:1,end:4}],signals:[{label,target:'第二项',start:1,end:4,refs:['o1'],evidence:text,scope:'current_self',basis:'explicit',confidence:.8,tentative:false}]});

test('新字幕不清掉状态；过期清除；旧字幕不倒退；标签不错误锚到下一句话',()=>{
  const view=new LiveViewState();view.accept({type:'state',version:1,current:[{id:'1',start:0,end:2,expiresAt:8,anchor:'不同意'}]});view.accept({type:'transcript',start:3,end:4,text:'继续说'});assert.equal(view.view(4).signals.length,1);assert.equal(view.view(4).signals[0].anchor,'');view.accept({type:'transcript',start:1,end:2,text:'旧字幕'});assert.equal(view.view(4).text,'继续说');assert.equal(view.view(9).signals.length,0);view.accept({type:'quality',quality:{face:'multiple'}});assert.equal(view.view(4).signals.length,0);
});
test('“你在测试是吧”可保留确认行为，不能由一句确认推出兴趣',()=>{
  const r=raw('兴趣','你在测试是吧');r.behaviors=[{label:'确认',target:'测试',refs:['o1'],start:1,end:4}];const result=normalizeFusion(r,input);assert.equal(result.signals.length,0);assert.equal(result.behaviors[0].label,'确认');assert.equal(result.unknownFamilies.length,4);
});
test('平静反对仅产生有依据的反对，不自动补情绪；引用、历史与归属不明均拒绝',()=>{
  assert.deepEqual(normalizeFusion(raw(),input).signals.map(s=>s.label),['反对']);const quoted=raw();quoted.signals[0].scope='quoted_other';assert.equal(normalizeFusion(quoted,input).signals.length,0);quoted.signals[0].scope='current_self';quoted.speakerBound=false;assert.equal(normalizeFusion(quoted,input).signals.length,0);
});
test('缺画面不能声称画面依据；伪造引用、纯系数推出情绪、微表情声明被拒绝',()=>{
  const r=raw('愉悦');r.observations[0].modality='画面';assert.equal(normalizeFusion(r,{...input,frames:[]}).signals.length,0);r.signals[0].refs=['missing'];assert.equal(normalizeFusion(r,input).signals.length,0);r.signals[0].refs=['f-1'];assert.equal(normalizeFusion(r,{...input,local:[{id:'f-1',modality:'画面',text:'嘴角上扬',source:'measurement'}]}).signals.length,0);r.signals[0].refs=['o1'];r.observations[0].text='检测到微表情';assert.equal(normalizeFusion(r,input).signals.length,0);
});
test('投入变化要前后证据，反话要多模态依据，零长度结果不能漏出',()=>{
  assert.equal(normalizeFusion(raw('投入降低'),input).signals.length,0);assert.equal(normalizeFusion(raw('反话'),input).signals.length,0);const r=raw();r.signals[0].start=8;r.signals[0].end=9;assert.equal(normalizeFusion(r,input).signals.length,0);
});
test('内容冲突必须在本次短期上下文中找到逐字引文，不能编造前情',()=>{
  const r=raw();r.consistency=[{kind:'conflict',target:'第二项',quotes:[{time:0,text:'我赞同'},{time:2,text:'第二项我不同意'}]}];assert.equal(normalizeFusion(r,input).consistency.length,0);const context=[{start:0,end:1,transcript:'我赞同'}];assert.equal(normalizeFusion(r,{...input,context}).consistency.length,1);
});
test('增量解析完整信号，能处理引号、花括号和被截断的下一个条目',()=>{
  const text='{"signals":[{"label":"反对","evidence":"带{括号}及\\\"引号\\\""},{"label":"未完';assert.equal(completedArray(text,'signals').length,1);assert.equal(completedArray(text,'signals')[0].label,'反对');
});
test('状态出现、稳定更新、结束、初步撤回；拒绝迟到覆盖并隔离会话',()=>{
  const engine=new StateEngine('a'),r=normalizeFusion(raw(),input),meta={start:0,end:5,now:5.5,windowId:1};let e=engine.update({...r,partial:true},meta);assert.equal(e.changes[0].type,'detected');const id=e.current[0].id;e=engine.update(r,{...meta,now:6});assert.equal(e.current[0].id,id);assert.equal(e.changes[0].type,'updated');e=engine.update({...r,signals:[]},meta);assert.equal(e.changes[0].type,'retracted');assert.equal(engine.update(r,{...meta,end:2}).historical,true);assert.equal(engine.update(r,{...meta,now:20}).historical,true);const other=new StateEngine('b');assert.notEqual(other.update(r,meta).current[0].id,id);
});
test('独立时钟能使断流后的标签过期，不把旧标签无限保留',()=>{
  const engine=new StateEngine('a');engine.update(normalizeFusion(raw(),input),{start:0,end:5,now:5,windowId:1});const event=engine.tick(11);assert.equal(event.current.length,0);assert.equal(event.changes[0].type,'ended');
});
test('a review older than the current-state deadline is recorded without reviving its label',()=>{
 const engine=new StateEngine('late-review'),r=normalizeFusion(raw(),input);
 const event=engine.update(r,{start:0,end:5,now:7.01,windowId:1,ttl:2});
 assert.equal(event.historical,true);assert.equal(event.current.length,0);assert.equal(event.changes[0].type,'observed');
});
test('unconfirmed ASR suffix is visible as a draft but never enters semantic evidence',()=>{
 const b=new EvidenceBuffer();b.pushAudio(Buffer.alloc(64000),0,2);
 b.transcript({id:'draft',start:0,end:2,text:'I want to buy the company',confirmedText:'I want',provisional:true});
 assert.equal(b.snapshot().transcript,'I want');
 b.transcript({id:'draft',start:0,end:2,text:'I want to ask a question',confirmedText:'I want to ask a question',provisional:false});
 assert.equal(b.snapshot().transcript,'I want to ask a question');
});
test('committed timing can correct the same draft without restoring an older utterance or downgrading final text',()=>{
 const view=new LiveViewState();
 view.accept({type:'transcript',id:'a',text:'draft',start:0,end:2.2,provisional:true});
 view.accept({type:'transcript',id:'a',text:'final',start:0,end:2,provisional:false});
 assert.equal(view.view(2.4).text,'final');
 view.accept({type:'transcript',id:'a',text:'late draft',start:0,end:2.3,provisional:true});assert.equal(view.view(2.4).text,'final');
 view.accept({type:'transcript',id:'b',text:'new',start:2,end:3,provisional:true});
 view.accept({type:'transcript',id:'a',text:'old',start:0,end:2,provisional:false});assert.equal(view.view(3).text,'new');
});
test('滚动窗口严格只有已接收的5秒媒体；上下文清到45秒，结束重置',()=>{
  const b=new EvidenceBuffer();for(let i=0;i<60;i++){b.pushAudio(Buffer.alloc(32000),i,i+1);b.pushFrame('YQ==',i+.5);b.transcript({id:String(i),text:'第'+i+'秒',start:i,end:i+1,provisional:false});}
  const value=b.snapshot();assert.equal(value.start,55);assert.equal(value.end,60);assert.equal(Buffer.from(value.audio.data,'base64').length,160044);assert.ok(value.context.every(t=>t.end>=15&&t.end<55));assert.ok(value.frames.every(f=>f.t>=0&&f.t<=5));b.clear();assert.equal(b.transcripts.size,0);assert.equal(b.audio.length,0);
});
test('声音测量：静音不生成基频，正弦基频可检测，WAV长度正确',()=>{
  assert.equal(audioFeatures(Buffer.alloc(3200)).pitchHz,null);const pcm=Buffer.alloc(3200);for(let i=0;i<1600;i++)pcm.writeInt16LE(Math.round(10000*Math.sin(2*Math.PI*200*i/16000)),i*2);assert.ok(Math.abs(audioFeatures(pcm).pitchHz-200)<5);assert.equal(wavFromPcm(pcm).readUInt32LE(40),3200);
});

test('VAD转折在滚动窗口外仍保留当前说话状态，未来的结束事件不能提前生效',()=>{
 const b=new EvidenceBuffer({windowSeconds:3,contextSeconds:45});
 b.activity.push({t:0,speaking:true});
 for(let i=0;i<62;i++)b.pushAudio(Buffer.alloc(3200),i,i+.1);
 b.activity.push({t:61.05,speaking:false});
 assert.equal(b.snapshot({end:60}).quality.speech,true);
 assert.equal(b.snapshot({end:61.1}).quality.speech,false);
 assert.equal(b.activity[0].t,0);
 b.end=120;b.prune();assert.deepEqual(b.activity,[{t:61.05,speaking:false}]);
});
test('真实请求形状携带原声、帧和本地测量；完整信号到达即发布，无需等全段JSON',async()=>{
  const data=raw(),progress=[];data.speakerBound=true;const text=JSON.stringify({speakerBound:true,visiblePeople:1,...data});
  const result=await analyzeFusion({...input,local:[{id:'a-level',modality:'声音',text:'-24 dBFS'}]},{key:'test-key',workspace:'test'},undefined,{onPartial:r=>progress.push(r),fetcher:async(url,options)=>{
    const body=JSON.parse(options.body);assert.match(body.messages[1].content[0].text,/a-level/);assert.equal(body.messages[1].content.filter(x=>['input_audio','image_url'].includes(x.type)).length,2);
    return new Response(new ReadableStream({start(c){for(let i=0;i<text.length;i+=15)c.enqueue(new TextEncoder().encode('data: '+JSON.stringify({choices:[{delta:{content:text.slice(i,i+15)}}]})+'\n\n'));c.close();}}),{headers:{'content-type':'text/event-stream'}});
  }});assert.equal(result.signals[0].label,'反对');assert.ok(progress.length>0);assert.equal(progress[0].partial,true);
});

test('回放严格按当时收到的版本，不提前显示未来的字幕或结束后返回的标签',()=>{
 const log=[{type:'transcript',text:'我',start:0,end:2,receivedAt:.5},{type:'transcript',text:'我不同意',start:0,end:2,receivedAt:2.2},{type:'state',version:1,current:[{label:'反对',start:0,end:2,expiresAt:8}],receivedAt:2.8,afterStop:true}];
 assert.equal(replayView(log,1).text,'我');assert.equal(replayView(log,2.5).text,'我不同意');assert.equal(replayView(log,3).signals.length,0);
});

test('人物离开画面后，迟到的声音标签不能重新出现在人物身上',()=>{
 const view=new LiveViewState();view.accept({type:'quality',quality:{face:'absent'}});
 view.accept({type:'state',version:1,current:[{id:'voice',label:'愉悦语调',expiresAt:5}]});
 assert.equal(view.view(1).signals.length,0);
 view.accept({type:'quality',quality:{face:'single'}});
 assert.equal(view.view(2).signals.length,0);
});

test('无法控制局面的结果陈述不是认知不确定；单个um也不是犹豫状态',()=>{
 const r=raw('不确定','we could not control it');assert.equal(normalizeFusion(r,input).signals.length,0);const pause=raw('犹豫','使用填充词um');pause.observations[0].modality='声音';pause.signals[0].basis='combined';assert.equal(normalizeFusion(pause,input).signals.length,0);pause.signals[0].basis='explicit';assert.equal(normalizeFusion(pause,input).signals.length,0);
});
