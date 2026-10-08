import test from 'node:test';
import assert from 'node:assert/strict';
import {StateEngine} from '../state-engine.mjs';
import {WindowScheduler} from '../window-scheduler.mjs';
import {EvidenceBuffer} from '../evidence.mjs';
import {SpecialistTracker,specialistEvidence} from '../specialists.mjs';
import {normalizeFusion,analyzeFusion} from '../fusion.mjs';

const signal=(label='愉悦',start=0,end=1)=>({label,target:'',start,end,confidence:.8,source:'fusion',observations:[]});
test('短暂且迟到的变化留档，不重新显示成当前状态，也不覆盖较新判断',()=>{
  const e=new StateEngine('record');
  e.update({signals:[signal('低落',0,2)]},{start:9,end:11,now:11,windowId:2});
  const event=e.update({signals:[signal('愉悦',.2,.5)]},{start:0,end:3,now:12,windowId:1});
  assert.equal(event.historical,true);assert.equal(event.current[0].label,'低落');
  assert.equal(event.changes[0].type,'observed');assert.equal(event.changes[0].signal.start,.2);
  const again=e.update({signals:[signal('愉悦',.2,.5)]},{start:0,end:3,now:12.1,windowId:1});
  assert.equal(again.changes.length,0);
});
test('完整记录超过三个状态；面部和融合判断互不清空',()=>{
  const e=new StateEngine('all'),meta={start:0,end:2,now:2,windowId:1};
  const event=e.update({signals:['愉悦','确信','专注','赞同'].map(x=>signal(x,0,2))},meta);
  assert.equal(event.current.length,4);
  e.update({signals:[{...signal('愉悦表情',0,2),source:'facial_expression'}]},{...meta,lane:'face'});
  const next=e.update({signals:[]},{...meta,start:2,end:4,windowId:2});
  assert.equal(next.current[0].label,'愉悦表情');
});
test('两个重叠窗口并发；慢服务不会积累旧请求，空位直接看最新输入',()=>{
  const s=new WindowScheduler(),a=s.reserve(1),b=s.reserve(2);
  assert.ok(a&&b);assert.equal(s.reserve(3),null);
  s.complete(a.id);assert.equal(s.reserve(7).end,7);s.close();
  assert.equal(b.controller.signal.aborted,true);assert.equal(s.running.size,0);
});
test('采样覆盖整个窗口；专用模型依据使用相对时间，不引用未来分类',()=>{
  const e=new EvidenceBuffer({windowSeconds:3});
  for(let i=0;i<10;i++){e.pushAudio(Buffer.alloc(16000),i/2,(i+1)/2);e.pushFrame('YQ==',i/2);}
  e.pushSpecialist({id:'s1',start:3,end:4,source:'specialist'});e.pushSpecialist({id:'s2',start:4,end:5,source:'specialist'});
  const snap=e.snapshot({end:4});assert.equal(snap.start,1);
  assert.equal(snap.frames[0].t,0);assert.equal(snap.frames.at(-1).t,3);
  assert.deepEqual(snap.local.filter(x=>x.source==='specialist').map(x=>[x.id,x.start,x.end]),[['s1',2,3]]);
});
test('专用分类只显示表情或语调；中性、弱分数、多人不会硬贴心理标签',()=>{
  const t=new SpecialistTracker(),base={model:'OpenFace-3.0',faces:1,quality:'ok',scores:{happy:.93,neutral:.07},aus:{AU12:.9}};
  const o=specialistEvidence(base,'face',{start:1,end:1.5,id:'s1'});
  assert.equal(t.update(base,'face',o).signals[0].label,'愉悦表情');
  assert.equal(o.source,'specialist');
  assert.equal(t.update({...base,faces:2},'face',o).signals.length,0);
  assert.equal(t.update({...base,scores:{neutral:.95,happy:.05}},'face',o).signals.length,0);
});
test('原声言语事件先按原始窗口平移，再裁剪；不引用过期或未来线索',()=>{
  const e=new EvidenceBuffer({windowSeconds:3});
  for(let i=0;i<7;i++)e.pushAudio(Buffer.alloc(32000),i,i+1);
  const value={model:'acoustic',quality:'ok',speechSpans:[
    {label:'filled_pause',start:.2,end:.5,meanScore:.9},
    {label:'repetition',start:2.2,end:2.5,meanScore:.9}]};
  e.pushSpecialist(specialistEvidence(value,'speech',{start:1,end:4,id:'past-window'}));
  e.pushSpecialist(specialistEvidence(value,'speech',{start:4,end:7,id:'future-window'}));
  const s=e.snapshot({end:6}).local.filter(x=>x.details?.speechSpans);
  assert.equal(s.length,1);assert.equal(s[0].id,'past-window');
  assert.equal(s[0].details.speechSpans.length,1);
  assert.ok(Math.abs(s[0].details.speechSpans[0].start-.2)<1e-8);
  assert.equal(s[0].details.speechSpans[0].end,.5);
  assert.deepEqual(new SpecialistTracker().update(value,'speech',s[0]),{signals:[]});
});
test('第一段静音、未知或中性输入不会造成专用分析异常',()=>{
  for(const kind of ['face','voice'])for(const scores of [{},{neutral:.9,happy:.1},{'<unk>':.98}]){
    const t=new SpecialistTracker(),result={model:'fixture',faces:1,quality:'ok',scores};
    const observation=specialistEvidence(result,kind,{start:0,end:1,id:'first'});
    assert.deepEqual(t.update(result,kind,observation),{signals:[]});
  }
});
test('完整的一条信号及其内嵌依据可先显示，不等待转写和其余字段',async()=>{
  const input={duration:3,start:0,end:3,audio:null,frames:[],transcript:'我不同意',local:[],context:[],quality:{}};
  const raw={speakerBound:true,visiblePeople:1,signals:[{label:'反对',target:'第二项',start:0,end:2,refs:['o1'],observations:[{id:'o1',modality:'语意',text:'我不同意',start:0,end:2}],evidence:'明确反对',scope:'current_self',basis:'explicit',confidence:.8}]};
  const parts=[JSON.stringify(raw).slice(0,-1),',"transcript":"我不同意"}'],received=[];
  await analyzeFusion(input,{key:'test',workspace:'test'},undefined,{onPartial:r=>received.push(r),fetcher:async()=>new Response(new ReadableStream({start(c){for(const text of parts)c.enqueue(new TextEncoder().encode('data: '+JSON.stringify({choices:[{delta:{content:text}}]})+'\n\n'));c.close();}}),{headers:{'content-type':'text/event-stream'}})});
  assert.equal(received[0].signals[0].label,'反对');
  const many={...raw,signals:Array.from({length:5},(_,i)=>({...raw.signals[0],target:'第'+i+'项'}))};
  assert.equal(normalizeFusion(many,input).signals.length,5);
});
