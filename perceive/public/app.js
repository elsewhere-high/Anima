import {DISPLAY_SIGNALS} from './signal-catalog.js';
import {cases,labels,totalDuration,locateTime} from './cases.js';
import {encodeWav,toBase64,audioFromVideo,frameData} from './media.js';
import {LiveConnection} from './live.js';
import {LiveViewState,replayView} from './live-state.js';

const $=id=>document.getElementById(id),video=$('reel'),selfVideo=$('self-video');
const icon=(paths)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
const playIcon=icon('<path d="m8 5 11 7-11 7z"/>'),pauseIcon=icon('<path d="M8 5v14M16 5v14"/>');
const soundIcon=icon('<path d="m11 5-6 4H2v6h3l6 4zM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14"/>');
const muteIcon=icon('<path d="m11 5-6 4H2v6h3l6 4zM16 9l5 6M21 9l-5 6"/>');
let status=null,current=0,mode='cases',loadId=0,experiment=null,saved=null,captionKey='',toastTimer,detailTimer,panelWasPlaying=false;
let restoreTime=0,uploadController=null,captureRequest=0,stoppingPromise=null;
const captionSegmenter=new Intl.Segmenter('zh',{granularity:'word'});
let captionWords=[];
const timeText=t=>`${Math.floor(t/60).toString().padStart(2,'0')}:${Math.floor(t%60).toString().padStart(2,'0')}`;
const toast=text=>{$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5000)};
async function refreshStatus(){const res=await fetch('/api/status');if(!res.ok)throw new Error('本地服务不可用');status=await res.json();$('workspace').value=status.workspace||'';$('model').textContent=status.reviewModel||'实时感知';for(const [id,selected] of [['model-choice',status.reviewModel],['fast-model-choice',status.fastModel]]){$(id+'-label').hidden=!status.modelChoices?.length;$(id).replaceChildren(...(status.modelChoices||[]).map(name=>{const option=document.createElement('option');option.value=name;option.textContent=name;option.selected=name===selected;return option;}));}$('api-key').required=!status.configured;return status;}
async function post(path,body,signal){if(!status)await refreshStatus();const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Anima-Token':status.token},body:JSON.stringify(body),signal});const data=await res.json();if(!res.ok)throw new Error(data.error||'本次分析失败');return data;}

function controls(){const target=mode==='saved'?selfVideo:video;$('play').innerHTML=target.paused?playIcon:pauseIcon;$('play').setAttribute('aria-label',target.paused?'播放案例':'暂停播放');$('sound').innerHTML=target.muted?muteIcon:soundIcon;$('sound').setAttribute('aria-label',target.muted?'开启声音':'关闭声音');$('sound').setAttribute('aria-pressed',String(!target.muted));}
function newCaptionCharacters(text){
  const words=Array.from(captionSegmenter.segment(text),part=>part.segment),previous=captionWords;
  // Match retained words even when ASR revises a phrase or the visible line drops its beginning.
  const lengths=Array.from({length:previous.length+1},()=>new Uint16Array(words.length+1));
  for(let i=previous.length-1;i>=0;i--)for(let j=words.length-1;j>=0;j--)
    lengths[i][j]=previous[i]===words[j]?1+lengths[i+1][j+1]:Math.max(lengths[i+1][j],lengths[i][j+1]);
  const retained=new Set();let i=0,j=0;
  while(i<previous.length&&j<words.length){
    if(previous[i]===words[j]){retained.add(j);i++;j++;}
    else if(lengths[i+1][j]>=lengths[i][j+1])i++;else j++;
  }
  captionWords=words;
  return words.flatMap((word,index)=>Array(word.length).fill(!retained.has(index)&&word.trim().length>0));
}
function renderCaption(text='',signals=[],key=''){
  if(captionKey===key)return;captionKey=key;$('caption').replaceChildren();
  const limit=window.innerWidth<=540?32:54;
  if(/^[\x00-\x7f\s…]+$/.test(text)&&text.includes(' ')){
    const words=text.trim().split(/\s+/);while(words.length>1&&words.join(' ').length>limit)words.shift();text=words.join(' ');
  }else if(text.length>limit)text='…'+text.slice(-limit);
  const fresh=newCaptionCharacters(text);let remaining=text,character=0;
  const addText=t=>{
    if(!t)return;const span=document.createElement('span');span.className='word';
    for(let start=0;start<t.length;){
      const animate=fresh[character+start];let end=start+1;
      while(end<t.length&&fresh[character+end]===animate)end++;
      const part=t.slice(start,end);
      if(animate){const added=document.createElement('span');added.className='word-new';added.textContent=part;span.append(added);}
      else span.append(document.createTextNode(part));
      start=end;
    }
    character+=t.length;$('caption').append(span);
  };
  for(const signal of signals){
    const anchor=signal.anchor&&remaining.includes(signal.anchor)?signal.anchor:'';
    if(anchor){const end=remaining.indexOf(anchor)+anchor.length;addText(remaining.slice(0,end));remaining=remaining.slice(end);}
    const b=document.createElement('button');b.type='button';b.className='tag';b.dataset.family=signal.family||labels.find(x=>x.label===signal.label)?.family||'认知';b.textContent=signal.label+(signal.tentative?'？':'');b.setAttribute('aria-label',`查看${signal.label}的依据`);
    b.addEventListener('click',()=>{const d=$('signal-detail');d.replaceChildren();const title=document.createElement('strong');title.textContent=signal.label+(signal.target?' · '+signal.target:'');d.append(title);const items=signal.observations||[];for(const item of items){const line=document.createElement('p');line.textContent=`${item.modality} · ${item.text}${item.source==='measurement'?'（本地测量）':item.source==='specialist'?('（'+item.model+'）'):'（模型观察）'}`;d.append(line);}const note=document.createElement('p');note.textContent=signal.source==='preset'?'示意标注':signal.evidence;d.append(note);if(signal.latencyMs){const meta=document.createElement('small');meta.textContent=`${signal.source==='model_case'?'离线分析 · ':signal.tentative?'初步判断 · ':''}${(signal.latencyMs/1000).toFixed(1)} 秒 · 可被后续证据修正`;d.append(meta);}d.hidden=false;clearTimeout(detailTimer);detailTimer=setTimeout(()=>d.hidden=true,6000)});
    $('caption').append(b);
  }
  addText(remaining);
}
function renderSegments(){
  $('segments').replaceChildren();
  cases.forEach((c,i)=>{
    const button=document.createElement('button');button.className='segment';button.type='button';button.style.flex=String(c.duration);button.setAttribute('aria-label',`播放 ${c.name}`);button.dataset.index=i;
    const image=document.createElement('img');image.src=`/assets/${c.id}.jpg`;image.alt='';const text=document.createElement('span');text.textContent=c.name;const cursor=document.createElement('i');cursor.className='cursor';cursor.hidden=true;
    button.append(image,text,cursor);button.addEventListener('click',()=>{closePanel(false);switchCase(i,0,true)});$('segments').append(button);
  });
  if(saved){const b=document.createElement('button');b.className='segment';b.style.flex='6';b.type='button';b.setAttribute('aria-label','播放我的实验');const s=document.createElement('span');s.textContent='我的实验';s.style.display='inline';b.append(s);b.addEventListener('click',()=>playSaved());$('segments').append(b);}
}
for(let i=0;i<64;i++){const tick=document.createElement('i');if(i%4===0)tick.className='major';$('ticks').append(tick);}
function updateTimeline(t){
  const duration=mode==='saved'?saved.duration:totalDuration;$('seek').value=Math.round(t/duration*1000);$('seek').setAttribute('aria-valuetext',timeText(t));
  const ticks=$('ticks').children;
  for(let i=0;i<ticks.length;i++)ticks[i].classList.toggle('active',Math.abs(i/63-t/duration)<.04);
  const segments=$('segments').children;
  for(let i=0;i<segments.length;i++){
    const selected=mode==='saved'?i===cases.length:i===current;segments[i].classList.toggle('current',selected);segments[i].setAttribute('aria-current',String(selected));
    const cursor=segments[i].querySelector('.cursor');if(cursor){cursor.hidden=!selected;segments[i].style.setProperty('--progress',`${Math.max(2,Math.min(98,video.currentTime/cases[i].duration*100))}%`);}
  }
}
function updateCase(){
  if(mode!=='cases')return;const c=cases[current],t=video.currentTime,offset=cases.slice(0,current).reduce((s,c)=>s+c.duration,0);
  const cue=c.cues.find(x=>t>=x.start&&t<x.end)||c.cues.at(-1);
  if(cue){
    const count=Math.min(cue.text.length,Math.max(1,Math.ceil((t-cue.start+.15)/Math.max(.1,cue.end-cue.start)*cue.text.length)));
    let text=cue.text.slice(0,count);
    if(cue.text.includes(' ')&&count<cue.text.length)text=text.replace(/\s+\S*$/,'');
    const signals=cue.signals.filter(s=>t>=(s.start??cue.start)&&t<(s.end??cue.end));
    renderCaption(text,signals,`${current}:${cue.start}:${count}`);
  }
  updateTimeline(offset+t);
}
async function switchCase(i,time=0,play=true){
  uploadController?.abort();uploadController=null;
  if(experiment)await stopExperiment(false);mode='cases';const id=++loadId;current=i;
  selfVideo.pause();selfVideo.hidden=true;selfVideo.classList.remove('mirror');video.hidden=false;$('play').hidden=false;$('sound').hidden=false;$('status').textContent='';$('source-note').textContent='案例 · 模型离线分析';$('reel-controls').hidden=false;$('experiment-controls').hidden=true;$('download').hidden=true;$('analyze-saved').hidden=true;
  $('records-button').hidden=true;$('records-panel').hidden=true;const c=cases[i];video.poster=`/assets/${c.id}.jpg`;video.style.objectPosition=c.position;video.src=`/assets/${c.id}.mp4`;captionKey='';renderCaption('',[],`${i}:initial`);
  await new Promise(resolve=>{if(video.readyState>=1)return resolve();video.addEventListener('loadedmetadata',resolve,{once:true});video.addEventListener('error',resolve,{once:true});});
  if(id!==loadId)return;video.currentTime=Math.min(time,video.duration||c.duration);updateCase();if(play)await video.play().catch(()=>{});controls();
}
video.addEventListener('timeupdate',updateCase);video.addEventListener('ended',()=>{if(mode==='cases')switchCase((current+1)%cases.length,0,true)});
video.addEventListener('play',controls);video.addEventListener('pause',controls);selfVideo.addEventListener('play',controls);selfVideo.addEventListener('pause',controls);
video.addEventListener('error',()=>toast('案例读取失败，请重新启动本地服务或运行 npm run setup。'));
$('play').addEventListener('click',()=>{const target=mode==='saved'?selfVideo:video;target.paused?target.play().catch(()=>toast('视频无法播放')):target.pause();});
$('sound').addEventListener('click',()=>{const target=mode==='saved'?selfVideo:video;target.muted=!target.muted;controls()});
$('seek').addEventListener('input',()=>{const t=Number($('seek').value)/1000*(mode==='saved'?saved.duration:totalDuration);if(mode==='saved'){selfVideo.currentTime=t;updateSaved();}else{const point=locateTime(t);if(point.index===current){video.currentTime=point.time;updateCase();}else switchCase(point.index,point.time,!video.paused);}});
$('signals-button').addEventListener('click',()=>{const p=$('signals-popover');p.hidden=!p.hidden;$('signals-button').setAttribute('aria-expanded',String(!p.hidden));if(!p.children.length)for(const s of DISPLAY_SIGNALS){const span=document.createElement('span');span.textContent=s.label;p.append(span)}});

async function openPanel(){
  $('signal-detail').hidden=true;
  panelWasPlaying=mode==='saved'?!selfVideo.paused:!video.paused;video.pause();selfVideo.pause();$('stage').classList.add('panel-open');$('experiment-panel').hidden=false;$('model-form').hidden=true;
  try{await refreshStatus();const localReady=['face','voice'].every(kind=>status.specialists?.[kind]?.status==='ready');$('panel-message').textContent=status.connectionError?status.connectionError:status.configured?(localReady?'已就绪。实时分析声音与画面，结束后可回看。':'可开始观察。本机表情和语调模型尚未就绪。'):'先在模型设置中填写千问 API Key。';}catch(e){$('panel-message').textContent=e.message;}
  $('record').focus();
}
function closePanel(resume=true){captureRequest++;$('stage').classList.remove('panel-open');$('experiment-panel').hidden=true;$('model-form').hidden=true;$('api-key').value='';if(resume&&panelWasPlaying)(mode==='saved'?selfVideo:video).play().catch(()=>{});}
$('try').addEventListener('click',openPanel);$('cancel').addEventListener('click',()=>closePanel());
$('configure').addEventListener('click',()=>{$('model-form').hidden=!$('model-form').hidden;if(!$('model-form').hidden)$('api-key').focus();});
$('model-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const data=await post('/api/config',{key:$('api-key').value,workspace:$('workspace').value,region:'cn-beijing',perceptionModel:$('model-choice').value||undefined,fastPerceptionModel:$('fast-model-choice').value||undefined});status={...status,...data};await refreshStatus();$('api-key').value='';$('model-form').hidden=true;$('panel-message').textContent='已配置。点“开始实时观察”连接千问。';}catch(error){$('panel-message').textContent=error.message;}finally{b.disabled=false;}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('signal-detail').hidden=true;closePanel();}});

class Experiment {
  constructor(stream){this.stream=stream;this.startTime=performance.now();this.events=[];this.log=[];this.view=new LiveViewState();this.active=true;this.parts=[];this.bytes=0;this.faceBusy=false;this.configured=true;}
  get time(){return(performance.now()-this.startTime)/1000;}
  async start(){
    this.live=new LiveConnection(status,{offset:()=>this.time,onEvent:e=>this.onEvent(e),onError:e=>{if(this.active){this.failed=true;this.live.close();renderCaption('',[],'live:disconnected');$('status').textContent='实时连接中断';$('speech-state').textContent='请结束后重新连接';toast(e.message);}}});
    $('status').textContent='准备观察';await this.live.connect();if(!this.active)return;
    await this.live.startAudio(this.stream,{paused:true});
    const [,vadReady]=await Promise.all([this.prepareFace(),this.prepareVad()]);
    if(!this.active)return;
    if(status.capabilities?.localTranscription&&!vadReady)throw new Error('语音检测未能准备好，请重新开始。');
    this.startTime=performance.now();
    const mime=['video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(x=>MediaRecorder.isTypeSupported(x));
    this.recorder=new MediaRecorder(this.stream,mime?{mimeType:mime,videoBitsPerSecond:1200000}:undefined);
    this.recorder.ondataavailable=e=>{if(e.data.size){this.parts.push(e.data);this.bytes+=e.data.size;if(this.bytes>128*1024*1024)stopExperiment();}};
    if(this.vad)await this.vad.start();
    this.recorder.start(1000);await this.live.resumeAudio();if(!this.active)return;
    $('status').textContent='实时观察';$('speech-state').textContent='正在观察';
    this.capture();setTimeout(()=>this.capture(),120);this.captureFace();this.frameTimer=setInterval(()=>this.capture(),500);this.faceTimer=setInterval(()=>this.captureFace(),200);
    this.uiTimer=setInterval(()=>{
      $('record-time').textContent=timeText(this.time);
      this.renderLive();
      if(this.time>=(status.capabilities?.maxObservationSeconds||120))stopExperiment();
    },250);
  }
  prepareFace(){
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('画面分析准备超时，请重新开始。')),15000);
      this.worker=new Worker('/face-worker.js');this.worker.onmessage=({data})=>{
        if(data.type==='ready'){this.faceReady=true;clearTimeout(timer);resolve();}
        if(data.type==='result'){this.faceBusy=false;if(this.active){this.live.face(data);this.multipleFaces=data.faces>1;if(this.multipleFaces){renderCaption('',[],'live:multiple');$('speech-state').textContent='请只保留一个人';}}}
        if(data.type==='error'){this.faceBusy=false;this.faceReady=false;clearTimeout(timer);reject(new Error('画面分析未能准备好，请重新开始。'));}
      };
      this.worker.onerror=()=>{this.faceBusy=false;this.faceReady=false;clearTimeout(timer);reject(new Error('画面分析未能准备好，请重新开始。'));};
      this.worker.postMessage({type:'init',presenceDetection:true});
    });
  }
  async prepareVad(){
    try{
      window.ort.env.wasm.numThreads=1;
      this.vad=await window.vad.MicVAD.new({model:'v6',startOnLoad:false,baseAssetPath:'/vendor/vad/',onnxWASMBasePath:'/vendor/ort/',redemptionMs:500,minSpeechMs:250,
        getStream:async()=>new MediaStream(this.stream.getAudioTracks()),pauseStream:async()=>{},resumeStream:async()=>new MediaStream(this.stream.getAudioTracks()),
        onSpeechStart:()=>{if(this.active&&!this.failed){this.live.send({type:'activity',speaking:true});if(!this.multipleFaces)$('speech-state').textContent='正在说话';}},
        onSpeechEnd:()=>{if(this.active&&!this.failed){if(!this.multipleFaces)$('speech-state').textContent='正在观察';this.live.send({type:'activity',speaking:false});this.live.commit();}}
      });
      if(!this.active){await this.vad.destroy();return false;}return true;
    }catch{return false;}
  }
  async capture(){
    if(!this.active||this.failed||!selfVideo.videoWidth)return;
    this.live.image(frameData(selfVideo,this.time));
  }
  async captureFace(){
    if(!this.active||this.failed||!selfVideo.videoWidth)return;
    if(this.faceReady&&!this.faceBusy){this.faceBusy=true;try{const image=await createImageBitmap(selfVideo);if(this.active)this.worker.postMessage({type:'frame',t:this.time,image},[image]);else{image.close();this.faceBusy=false;}}catch{this.faceBusy=false;}}
  }
  renderLive(){
    if(!this.active||this.failed)return;
    const value=this.view.view(this.time);if(this.multipleFaces)value.signals=[];
    renderCaption(value.text,value.signals,`live:${value.text}:${value.signals.map(s=>s.id+':'+s.updatedAt+':'+s.tentative).join(',')}`);
    const signature=JSON.stringify([value.text,value.signals.map(s=>[s.id,s.label,s.tentative])]);
    if(signature!==this.lastDisplay){
      this.lastDisplay=signature;const at=this.time;
      // Timestamp the completed DOM update, independently of model receipt.
      this.log.push({type:'display',receivedAt:at,at,afterStop:false,text:value.text,transcriptId:this.view.caption?.id??null,transcriptEnd:this.view.caption?.end??null,transcriptTiming:this.view.caption?.timing??null,signals:value.signals.map(s=>({id:s.id,label:s.label,source:s.source,start:s.start,end:s.end,detectedAt:s.detectedAt,updatedAt:s.updatedAt,tentative:s.tentative,latencyMs:s.latencyMs}))});
      if(this.log.length>20000)this.log.splice(0,this.log.length-20000);
    }
  }
  onEvent(result){
    if((!this.active&&!this.finishing)||experiment!==this&&!this.finishing)return;
    this.view.accept(result);
    if(['transcript','state','measurement','quality','notice','fast.result','result','session.start','session.end'].includes(result.type)){
      // Keep one final form of each subtitle, all state transitions, and bounded notices.
      // Preserve the received version: replay must not reveal later ASR completions.
      this.log.push({...result,receivedAt:this.time,afterStop:!this.active});
      if(this.log.length>20000)this.log.splice(0,this.log.length-20000);
    }
    if(result.type==='notice'&&this.active&&!this.failed){$('speech-state').textContent=result.message;if(result.code==='MODEL_ACCESS_UNAVAILABLE')this.modelUnavailable=true;if(result.code==='FAST_DELIVERY_UNAVAILABLE')this.fastUnavailable=true;}
    if(result.type==='fast.result')this.fastUnavailable=false;
    if(result.type==='result')this.modelUnavailable=false;
    if(result.type==='state'&&this.active&&!this.failed){
      $('status').textContent=this.modelUnavailable?'本地观察':this.fastUnavailable?'部分分析':'实时观察';
      const quality=result.quality;
      $('speech-state').textContent=quality?.face==='multiple'?'请只保留一个人':quality?.dark?'画面偏暗':quality?.clipping?'声音失真':this.modelUnavailable?'云端模型未就绪':this.fastUnavailable?'快速判断未就绪':result.unknown?'继续观察':'正在观察';
    }
    if(result.type==='result')this.events.push({...result,signals:result.signals.map(s=>({...s,start:s.start+result.start,end:s.end+result.start})),afterStop:!this.active});
    this.renderLive();if(!$('records-panel').hidden)renderRecords();
  }
  async stop(){
    if(!this.active)return;this.active=false;this.finishing=true;clearInterval(this.frameTimer);clearInterval(this.faceTimer);clearInterval(this.uiTimer);this.worker?.terminate();this.live?.stopAudio();
    const duration=this.recorder?this.time:0;
    if(this.recorder?.state==='recording')await new Promise(resolve=>{this.recorder.addEventListener('stop',resolve,{once:true});this.recorder.stop();});
    this.stream.getTracks().forEach(t=>t.stop());try{await this.vad?.destroy();}catch{}
    if(this.live?.ready&&!this.failed){$('status').textContent='结束中';await this.live.finish();}else this.live?.close();
    this.finishing=false;
    const blob=new Blob(this.parts,{type:this.recorder?.mimeType||'video/webm'});
    return {blob,duration,events:this.events,log:this.log,protocol:'anima.perceive.v2',configured:this.configured};
  }
}
async function startExperiment(){
  const request=++captureRequest;$('record').disabled=true;
  let stream;
  try{
    await refreshStatus();
    if(!status.configured){$('model-form').hidden=false;$('panel-message').textContent='请先填写千问 API Key。';$('api-key').focus();return;}
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('请用本机 Chrome 或 Edge 打开此页面。');
    stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},facingMode:'user'},audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}});
    if(request!==captureRequest){stream.getTracks().forEach(t=>t.stop());return;}
    await observeStream(stream);
  }catch(e){stream?.getTracks().forEach(t=>t.stop());if(request!==captureRequest&&!stream)return;if(experiment)await stopExperiment(false);await switchCase(current,restoreTime,false);await openPanel();$('panel-message').textContent=e.name==='NotAllowedError'?'摄像头或麦克风未获许可。可选择视频继续。':e.name==='NotReadableError'?'摄像头正被占用。请关闭其他摄像头应用，或选择视频。':e.message;}
  finally{$('record').disabled=false;}
}
export async function observeStream(stream){
    closePanel(false);video.pause();video.hidden=true;selfVideo.hidden=false;selfVideo.src='';selfVideo.muted=true;selfVideo.srcObject=stream;selfVideo.classList.add('mirror');
    restoreTime=video.currentTime;mode='live';$('records-button').hidden=false;$('records-panel').hidden=true;$('play').hidden=true;$('sound').hidden=true;$('reel-controls').hidden=true;$('experiment-controls').hidden=false;$('status').textContent='连接千问中';$('source-note').textContent='我的实验 · 实时';$('download').hidden=true;$('analyze-saved').hidden=true;renderCaption('',[],`live:start`);
    await selfVideo.play();
    const run=new Experiment(stream);experiment=run;try{await run.start();}catch(error){if(experiment!==run)return;throw error;}
}
export async function finishObservedStream(){await stopExperiment();return saved;}
$('record').addEventListener('click',startExperiment);
async function stopExperiment(showSaved=true){
  if(stoppingPromise)return stoppingPromise;
  if(!experiment)return;const run=experiment;experiment=null;$('stop').disabled=true;
  stoppingPromise=(async()=>{
    try{const result=await run.stop();selfVideo.srcObject=null;selfVideo.classList.remove('mirror');if(result?.blob.size){if(saved?.url)URL.revokeObjectURL(saved.url);saved={...result,url:URL.createObjectURL(result.blob)};renderSegments();if(showSaved)await playSaved();}else if(showSaved)await switchCase(current,restoreTime,true);}
    finally{$('stop').disabled=false;$('experiment-controls').hidden=true;}
  })();
  try{return await stoppingPromise;}finally{stoppingPromise=null;}
}
$('stop').addEventListener('click',()=>stopExperiment());
async function playSaved(){
  if(!saved)return;closePanel(false);if(experiment)await stopExperiment(false);mode='saved';loadId++;video.pause();video.hidden=true;selfVideo.hidden=false;selfVideo.classList.remove('mirror');selfVideo.srcObject=null;selfVideo.src=saved.url;selfVideo.muted=video.muted;
  $('records-button').hidden=false;$('records-panel').hidden=true;$('play').hidden=false;$('sound').hidden=false;$('status').textContent='我的实验 · 回看';$('reel-controls').hidden=false;$('experiment-controls').hidden=true;$('download').hidden=false;$('analyze-saved').hidden=false;$('source-note').textContent=saved.events.length?'我的实验 · 模型结果':saved.log?.some(e=>e.type==='measurement')?'我的实验 · 本地观察':'我的实验 · 尚未分析';captionKey='';renderCaption('',[],'saved:start');await selfVideo.play().catch(()=>{});updateSaved();controls();
}
function updateSaved(){
  if(mode!=='saved'||!saved)return;const t=selfVideo.currentTime;
  if(saved.log?.some(e=>e.type==='state')){
    const value=replayView(saved.log,t);renderCaption(value.text,value.signals,`saved:${value.text}:${value.signals.map(s=>s.id+':'+s.updatedAt).join(',')}`);
  }else{
    const event=saved.events.filter(e=>t>=e.start&&t<e.end).at(-1);
    if(event){const seg=event.segments?.find(s=>t>=event.start+s.start&&t<event.start+s.end),signals=event.signals.filter(s=>t>=s.start&&t<=s.end);renderCaption(seg?.text||event.transcript||event.scene,signals,`saved:${event.start}:${signals.map(s=>s.label).join(',')}`);}else renderCaption('',[],'saved:empty');
  }
  updateTimeline(t);
}
function renderRecords(){
  const panel=$('records-list');panel.replaceChildren();const source=experiment||saved;
  const entries=(source?.log||[]).filter(e=>e.type==='state');const rows=[];if(!entries.length)for(const e of source?.events||[]){for(const signal of e.signals||[])rows.push({at:signal.start,label:signal.label,text:'视频分析',detail:signal.evidence,signal});for(const b of e.behaviors||[])rows.push({at:e.start+b.start,label:b.label,text:b.target,detail:'当前表达行为'});}
  for(const event of entries){
    for(const change of event.changes||[]){if(change.type==='updated')continue;rows.push({at:change.type==='observed'?change.signal.start:change.at,label:change.signal.label,text:{detected:'出现',observed:'片段识别',ended:'结束',retracted:'修正'}[change.type],detail:change.reason||change.signal.evidence,signal:change.signal,late:event.afterStop});}
    for(const b of event.behaviors||[])rows.push({at:event.at,label:b.label,text:b.target,detail:'当前表达行为',late:event.afterStop});
    for(const c of event.consistency||[])rows.push({at:event.at,label:'待核对',text:c.target,detail:c.quotes.map(q=>q.text).join(' ↔ '),late:event.afterStop});
  }
  if(!rows.length){const empty=document.createElement('p');empty.className='records-empty';empty.textContent=source?.events?.at(-1)?.unknown||'暂时没有足够依据。';panel.append(empty);}
  const seen=new Set();for(const row of rows.reverse()){
    const k=row.label+row.text+Math.floor(row.at/2);if(seen.has(k))continue;seen.add(k);
    const button=document.createElement('button');button.className='record-row';button.type='button';const time=document.createElement('time');time.textContent=timeText(row.at);const name=document.createElement('span');name.textContent=`${row.label} · ${row.text||''}${row.late?' · 结束后返回':''}`;const desc=document.createElement('small');desc.textContent=row.detail;button.append(time,name,desc);
    button.addEventListener('click',()=>{$('records-panel').hidden=true;$('records-button').setAttribute('aria-expanded','false');if(mode==='saved'){selfVideo.currentTime=Math.min(saved.duration-.05,row.signal?.start??row.at);selfVideo.pause();updateSaved();}if(row.signal){renderCaption('',[row.signal],`evidence:${row.signal.id}:${row.at}`);$('caption').querySelector('button')?.click();}});panel.append(button);if(seen.size>=50)break;
  }
}
$('records-button').addEventListener('click',()=>{const panel=$('records-panel');panel.hidden=!panel.hidden;$('records-button').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)renderRecords();});
$('records-close').addEventListener('click',()=>{$('records-panel').hidden=true;$('records-button').setAttribute('aria-expanded','false');});
selfVideo.addEventListener('timeupdate',updateSaved);
selfVideo.addEventListener('loadedmetadata',()=>{if(mode==='saved'&&Number.isFinite(selfVideo.duration)){saved.duration=selfVideo.duration;updateSaved();}});
$('download').addEventListener('click',()=>{
  if(!saved)return;const link=document.createElement('a');link.href=saved.url;link.download=`Anima-experiment.${saved.blob.type.includes('mp4')?'mp4':'webm'}`;link.click();
  const json=new Blob([JSON.stringify({protocol:saved.protocol||'anima.review.v1',duration:saved.duration,events:saved.events,log:saved.log||[]},null,2)],{type:'application/json'});const url=URL.createObjectURL(json);const data=document.createElement('a');data.href=url;data.download='Anima-experiment.json';data.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('upload').addEventListener('click',()=>$('video-file').click());
$('video-file').addEventListener('change',async()=>{
  const file=$('video-file').files[0];$('video-file').value='';if(!file)return;
  if(file.size>32*1024*1024){toast('请选择 32 MB 以内的短视频。');return;}
  closePanel(false);if(saved?.url)URL.revokeObjectURL(saved.url);saved={blob:file,url:URL.createObjectURL(file),duration:0,events:[],configured:!!status?.configured};renderSegments();
  await playSaved();selfVideo.pause();await new Promise(resolve=>{if(selfVideo.readyState>=1||selfVideo.error)return resolve();const done=()=>{clearTimeout(timer);selfVideo.removeEventListener('loadedmetadata',done);selfVideo.removeEventListener('error',done);resolve();},timer=setTimeout(done,5000);selfVideo.addEventListener('loadedmetadata',done,{once:true});selfVideo.addEventListener('error',done,{once:true});});
  if(!Number.isFinite(selfVideo.duration)||selfVideo.duration<=0||selfVideo.duration>120){toast('请选择两分钟以内、浏览器可播放的视频。');URL.revokeObjectURL(saved.url);saved=null;renderSegments();switchCase(current,restoreTime,false);return;}
  saved.duration=selfVideo.duration;if(!status?.configured){toast('视频已加载。连接模型后可进行分析。');return;}
  await analyzeUploaded();
});
async function analyzeUploaded(){
  const reference=saved;const controller=new AbortController();let faceWorker;uploadController=controller;$('try').disabled=true;$('seek').disabled=true;$('play').disabled=true;$('analyze-saved').disabled=true;selfVideo.pause();reference.events=[];
  try{
    const audio=await audioFromVideo(reference.blob);$('status').textContent='正在分析视频';
    try{
      faceWorker=new Worker('/face-worker.js');
      await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('面部模块加载超时')),8000);faceWorker.onmessage=({data})=>{if(data.type==='ready'||data.type==='error'){clearTimeout(timer);data.type==='ready'?resolve():reject(new Error(data.message));}};faceWorker.onerror=()=>{clearTimeout(timer);reject(new Error('面部模块不可用'));};faceWorker.postMessage({type:'init'});});
    }catch{faceWorker?.terminate();faceWorker=null;}
    for(let start=0;start<reference.duration;start+=6){
      if(saved!==reference||mode!=='saved')break;const end=Math.min(reference.duration,start+6),frames=[],face=[];
      for(let t=start;t<end;t+=1.5){
        if(controller.signal.aborted)throw new DOMException('已停止','AbortError');
        const target=Math.min(reference.duration-.01,Math.max(.01,t));
        if(Math.abs(selfVideo.currentTime-target)>.005)await new Promise((resolve,reject)=>{const done=()=>{clearTimeout(timer);resolve();},timer=setTimeout(()=>reject(new Error('视频定位失败，请换一段视频。')),5000);selfVideo.addEventListener('seeked',done,{once:true});selfVideo.currentTime=target;});
        frames.push(frameData(selfVideo,t-start));
        if(faceWorker){try{const image=await createImageBitmap(selfVideo);const detected=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('面部检测超时')),3000);faceWorker.onmessage=({data})=>{clearTimeout(timer);data.type==='result'?resolve(data):reject(new Error(data.message));};faceWorker.postMessage({type:'frame',image,t:t-start},[image]);});face.push(detected);}catch{faceWorker.terminate();faceWorker=null;}}
      }
      if(face.some(f=>f.faces>1))throw new Error('这一版只分析一个人，请选择单人视频。');
      const slice=audio.subarray(Math.floor(start*16000),Math.floor(end*16000));
      const result=await post('/api/analyze',{start,duration:end-start,audio:{mimeType:'audio/wav',data:await toBase64(encodeWav(slice))},frames,face,context:reference.events.slice(-5).map(e=>({start:e.start,end:e.end,transcript:e.transcript,signals:e.signals.map(s=>s.label)}))},controller.signal);
      if(saved!==reference||mode!=='saved')break;reference.events.push({...result,start,end,signals:result.signals.map(s=>({...s,start:s.start+start,end:s.end+start}))});$('status').textContent=`分析 ${Math.round(end/reference.duration*100)}%`;
    }
    if(saved===reference&&mode==='saved'){selfVideo.currentTime=0;$('source-note').textContent='我的实验 · 模型结果';$('status').textContent='我的实验 · 回看';await selfVideo.play().catch(()=>{});}
  }catch(e){if(e.name!=='AbortError')toast(e.message);if(saved===reference&&mode==='saved')$('status').textContent='分析未完成';}
  finally{faceWorker?.terminate();if(uploadController===controller)uploadController=null;$('try').disabled=false;$('seek').disabled=false;$('play').disabled=false;$('analyze-saved').disabled=false;}
}
$('analyze-saved').addEventListener('click',async()=>{await refreshStatus();if(!status.configured){await openPanel();$('model-form').hidden=false;$('api-key').focus();return;}if(saved?.duration)await analyzeUploaded();});
window.addEventListener('pagehide',()=>{uploadController?.abort();experiment?.stream.getTracks().forEach(t=>t.stop());experiment?.live?.close();experiment?.worker?.terminate();if(saved?.url)URL.revokeObjectURL(saved.url);});
refreshStatus().catch(()=>{});renderSegments();controls();switchCase(0,0,true);

if(new URLSearchParams(location.search).get('qa')==='public-stream'){
  const {install}=await import('./app-stream-qa.js');
  install({prepare:refreshStatus,observe:observeStream,finish:finishObservedStream,inspect:()=>({active:!!experiment?.active,time:experiment?.time??saved?.duration??0,log:experiment?.log??saved?.log??[],events:experiment?.events??saved?.events??[]})});
}
