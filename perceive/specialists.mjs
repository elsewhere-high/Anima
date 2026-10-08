import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('./integrations/',import.meta.url));

export class Specialists {
  constructor({enabled=true}={}){this.enabled=enabled;this.process=null;this.requests=new Map();this.busy=new Set();this.serial=0;this.models={face:{status:'not_installed'},voice:{status:'not_installed'}};}
  start(){
    if(!this.enabled||this.process||!existsSync(root+'.venv/bin/python'))return;
    if(!existsSync(root+'models/openface/MTL_backbone.pth')&&!existsSync(root+'models/emotion2vec/model.pt'))return;
    this.models={face:{status:'loading'},voice:{status:'loading'}};
    this.process=spawn(root+'.venv/bin/python',['-u',root+'specialists.py'],{cwd:root,stdio:['pipe','pipe','pipe'],env:{...process.env,HF_HUB_OFFLINE:'1',PYTHONUNBUFFERED:'1'}});
    // Dependencies sometimes log paths and progress. Keep it off the user stream.
    this.process.stderr.on('data',()=>{});
    this.process.stdin.on('error',()=>{});
    createInterface({input:this.process.stdout}).on('line',line=>{
      let event;try{event=JSON.parse(line);}catch{return;}
      if(event.type==='model'){this.models[event.kind]={status:event.status,error:event.error};return;}
      if(event.type==='ready'){this.ready=true;this.runtime=event.runtime;return;}
      const pending=this.requests.get(event.id);if(!pending)return;
      clearTimeout(pending.timeout);this.requests.delete(event.id);this.busy.delete(pending.kind);
      if(event.error){pending.reject(new Error(event.error));return;}
      this.models[pending.kind]={status:'ready',latencyMs:event.latencyMs,model:event.result.model};
      pending.resolve({...event.result,latencyMs:event.latencyMs});
    });
    const lost=()=>{this.process=null;this.ready=false;for(const kind of Object.keys(this.models))this.models[kind]={status:'unavailable'};for(const p of this.requests.values()){clearTimeout(p.timeout);p.reject(new Error('specialist_unavailable'));}this.requests.clear();this.busy.clear();};
    this.process.on('error',lost);this.process.on('exit',lost);
  }
  status(){return {...this.models};}
  available(kind){return this.ready&&this.models[kind]?.status==='ready'&&!this.busy.has(kind);}
  infer(kind,payload){
    if(!this.available(kind)||!this.process)return Promise.reject(new Error('specialist_unavailable'));
    this.busy.add(kind);
    return new Promise((resolve,reject)=>{
      const id=++this.serial,timeout=setTimeout(()=>{
        this.requests.delete(id);this.busy.delete(kind);this.models[kind]={status:'unavailable',error:'timeout'};reject(new Error('specialist_timeout'));
      },15000);
      this.requests.set(id,{resolve,reject,timeout,kind});
      this.process.stdin.write(JSON.stringify({id,kind,...payload})+'\n');
    });
  }
  close(){this.enabled=false;this.process?.kill();this.process=null;}
}

const expressions={happy:'愉悦表情',sad:'低落表情',surprise:'惊讶表情',fear:'害怕表情',disgust:'厌恶表情',anger:'生气表情',contempt:'轻蔑表情'};
const voices={happy:'愉悦语调',sad:'低落语调',surprised:'惊讶语调',fearful:'害怕语调',disgusted:'厌恶语调',angry:'生气语调'};
export function specialistEvidence(result,kind,{start,end,id}){
  if(kind==='speech')return {id,modality:'声音',text:'原声言语结构检测：填充音、重复、改口等；不等于心理犹豫或不确定',start,end,source:'specialist',model:result.model,
    details:{speechSpans:result.speechSpans,quality:result.quality,trainingLanguage:result.trainingLanguage},latencyMs:result.latencyMs};
  const scores=Object.entries(result.scores||{}).filter(([,v])=>Number.isFinite(v)).sort((a,b)=>b[1]-a[1]);
  const modality=kind==='face'?'画面':'声音',top=scores.slice(0,3);
  const text=(kind==='face'?'面部表情分类':'原声情绪分类')+'：'+top.map(([k,v])=>`${k} ${v.toFixed(2)}`).join('，')+'；分类分数未校准，不等于心理状态'+(kind==='face'&&result.aus?'；'+Object.entries(result.aus).map(([k,v])=>`${k} ${Number(v).toFixed(2)}`).join('，'):'');
  return {id,modality,text,start,end,source:'specialist',model:result.model,details:{scores:result.scores,expressionModels:result.expressionModels,aus:result.aus,gaze:result.gaze,quality:result.quality,prosody:result.prosody},latencyMs:result.latencyMs};
}
export class SpecialistTracker {
  constructor(){this.previous=new Map();}
  update(result,kind,observation){
    const entries=Object.entries(result.scores||{}).filter(([,v])=>Number.isFinite(v)).sort((a,b)=>b[1]-a[1]);
    const [raw,score]=entries[0]||[],name=String(raw||'').split('/').at(-1).trim().toLowerCase();
    const label=(kind==='face'?expressions:voices)[name],previous=this.previous.get(kind);
    this.previous.set(kind,{label,end:observation.end});
    const consistent=previous&&previous.label===label&&observation.end-previous.end<2;
    // Thresholds are development heuristics, not calibrated probabilities.
    const enough=kind==='face'?(consistent&&score>=.65||score>=.85):score>=.65;
    if(!label||!enough||score-(entries[1]?.[1]||0)<.15||result.quality!=='ok'||kind==='face'&&result.faces!==1)return {signals:[]};
    const local={...observation,start:0,end:observation.end-observation.start};
    return {signals:[{label,family:'情绪',start:0,end:local.end,target:'',anchor:'',confidence:score,tentative:false,source:kind==='face'?'facial_expression':'vocal_expression',evidence:kind==='face'?'模型对可见表情的分类，不代表真实内心感受':'模型对原声的分类，尚未绑定画面中的说话人',refs:[local.id],observations:[local],modalities:[local.modality]}]};
  }
}
