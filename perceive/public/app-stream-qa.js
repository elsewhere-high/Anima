import {audioFromVideo} from './media.js';

// Runs the actual application's Experiment, recording and replay paths using
// an installed public clip. Never requests physical camera or microphone access.
export function install({prepare,observe,finish,inspect}){
 const seconds=Math.min(600,Math.max(10,Number(new URLSearchParams(location.search).get('seconds'))||20));
 const link=document.createElement('link');link.rel='stylesheet';link.href='/research-qa.css';document.head.append(link);
 const box=document.createElement('aside');box.className='research-qa';
 const button=document.createElement('button');button.textContent=`验证实际页面 · ${seconds} 秒`;
 const output=document.createElement('pre');output.id='app-qa-report';output.textContent='仅使用公开素材，不访问摄像头或麦克风。';box.append(button,output);document.body.append(box);
 button.onclick=async()=>{
  button.disabled=true;let context,stream,source,donor,drawTimer,tickTimer,starting=false,mediaStarted=false;
  const long=seconds>30,id=long?'yann-continuous':'yann-lecun-wef',createdAt=new Date().toISOString();
  const report={phase:'准备',seconds,profile:new URLSearchParams(location.search).get('profile')||'default',cameraAccess:false,microphoneAccess:false,transcripts:0,measurements:0,displayUpdates:0,notices:[],savedMinutes:0,blankChecks:[],cloudVerified:false};
  const show=()=>output.textContent=JSON.stringify(report,null,2);
  let lastIndex=0,chunk=[],display=[],lastDisplay='',part=0,nextSave=60,pendingSave=Promise.resolve();
  const collect=()=>{
   const snapshot=inspect();
   // During stop, the application briefly has no active experiment before its
   // saved recording is ready. Never reset the cursor and duplicate the full log.
   const log=snapshot.log||[],fresh=log.length>=lastIndex?log.slice(lastIndex):[];
   if(log.length>=lastIndex)lastIndex=log.length;chunk.push(...fresh);
   for(const e of fresh){if(e.type==='transcript')report.transcripts++;if(e.type==='measurement')report.measurements++;if(e.type==='notice')report.notices.push({code:e.code,message:e.message});}
   report.elapsedSeconds=Math.round(snapshot.time||0);
   report.reviewLiveResults=(snapshot.events||[]).filter(e=>!e.afterStop).length;
   report.fastLiveResults=log.filter(e=>e.type==='fast.result'&&!e.afterStop).length;
   report.cloudVerified||=report.reviewLiveResults>0;
   const tags=[...document.querySelectorAll('#caption .tag')].map(t=>t.textContent),key=tags.join('|');
   if(key!==lastDisplay){lastDisplay=key;display.push({at:snapshot.time,labels:tags});report.displayUpdates++;}
   return snapshot;
  };
  try{
   const status=await prepare();if(!status.configured)throw new Error('先配置模型。');report.localRuntime=status.localRuntime;
   const asset=long?'/research-assets/yann-continuous.mp4':'/assets/yann-lecun-wef.mp4';
   const audio=await audioFromVideo(await(await fetch(asset)).blob());
   donor=document.createElement('video');donor.muted=true;donor.playsInline=true;donor.src=asset;donor.loop=!long;
   await new Promise((r,j)=>{donor.onloadeddata=r;donor.onerror=()=>j(Error('测试素材读取失败'));});
   const canvas=document.createElement('canvas');canvas.width=640;canvas.height=Math.round(640*donor.videoHeight/donor.videoWidth);
   const painter=canvas.getContext('2d');painter.drawImage(donor,0,0,canvas.width,canvas.height);
   if(!canvas.captureStream)throw new Error('此浏览器不支持公开素材流验证。');
   stream=canvas.captureStream(25);context=new AudioContext({sampleRate:16000});await context.resume();
   const destination=context.createMediaStreamDestination(),gain=context.createGain();gain.connect(destination);destination.stream.getAudioTracks().forEach(t=>stream.addTrack(t));
   source=context.createBufferSource();const buffer=context.createBuffer(1,audio.length,16000);buffer.copyToChannel(audio,0);source.buffer=buffer;source.loop=!long;source.connect(gain);
   drawTimer=setInterval(()=>{
    const at=inspect().time,blank=!mediaStarted||(long&&at%60>=50&&at%60<55);
    gain.gain.value=blank?0:1;
    if(blank){painter.fillStyle='#000';painter.fillRect(0,0,canvas.width,canvas.height);}else painter.drawImage(donor,0,0,canvas.width,canvas.height);
    stream.getVideoTracks()[0]?.requestFrame?.();
   },40);
   // Warm the capture graph with muted audio and blank frames only. No future
   // human evidence enters the application before its observation clock starts.
   gain.gain.value=0;source.start();await donor.play();
   starting=true;show();let startupTimeout;
   try{await Promise.race([observe(stream),new Promise((_,reject)=>{startupTimeout=setTimeout(()=>reject(Error('页面媒体流启动超时')),30000);})]);}finally{clearTimeout(startupTimeout);}
   source.stop();source=context.createBufferSource();source.buffer=buffer;source.loop=!long;source.connect(gain);
   donor.currentTime=0;source.start();mediaStarted=true;gain.gain.value=1;await donor.play();report.phase='持续观察';show();
   const save=async(snapshot,final=false)=>{
    const events=chunk,shown=display;chunk=[];display=[];const number=++part;
    const run={id,round:1,duration:snapshot.time,completedAt:snapshot.time,events,display:shown,notices:events.filter(e=>e.type==='notice'),qa:{...report,final}};
    const body={variant:`app-live-${seconds}-part-${number}`,suite:'app-live',requestedRounds:1,control:null,createdAt,protocol:'application-stream-v1',models:{fusion:status.reviewModel,fast:status.fastModel,asr:status.model},runs:[run]};
    const response=await fetch('/api/research/run',{method:'POST',headers:{'Content-Type':'application/json','X-Anima-Token':status.token},body:JSON.stringify(body),signal:AbortSignal.timeout(5000)});
    if(!response.ok)throw Error('验证记录保存失败');report.savedMinutes++;
   };
   tickTimer=setInterval(()=>{
    const snapshot=collect(),at=snapshot.time;
    if(long&&at%60>=52&&at%60<55)report.blankChecks.push({at,visibleTags:document.querySelectorAll('#caption .tag').length});
    if(at>=nextSave){nextSave+=60;pendingSave=pendingSave.then(()=>save(snapshot)).catch(e=>{report.saveError=e.message;});}
    show();
   },1000);
   await new Promise(resolve=>setTimeout(resolve,seconds*1000));
   collect();clearInterval(tickTimer);clearInterval(drawTimer);source.stop();donor.pause();
   const final=await finish();report.recordedBytes=final?.blob?.size||0;report.recordedSeconds=final?.duration||0;
   const snapshot=inspect();collect();report.phase='完成';report.infrastructurePassed=report.recordedSeconds>=seconds-1&&report.transcripts>0&&report.measurements>0&&report.recordedBytes>0&&report.blankChecks.every(x=>x.visibleTags===0);
   report.fullMultimodalVerified=report.infrastructurePassed&&report.cloudVerified&&report.fastLiveResults>0&&!report.notices.some(n=>/UNAVAILABLE/.test(n.code));
   await pendingSave;await save(snapshot,true);show();
  }catch(error){report.phase='失败';report.error=error.message;show();}
  finally{
   clearInterval(drawTimer);clearInterval(tickTimer);donor?.pause();try{source?.stop();}catch{}
   if(starting&&inspect().active)await finish();stream?.getTracks().forEach(t=>t.stop());await context?.close();button.disabled=false;
  }
 };
}
