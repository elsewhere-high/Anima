'use strict';
// Local neural VAD, slower turn endings, bounded continuation and AEC-assisted interruption.
(() => {
 const ui=id=>document.getElementById(id);
 let active=false,phase='idle',epoch=0,mic=null,context=null,source=null,processor=null;
 let preroll=[],frames=[],recording=false,voiced=0,quiet=0,total=0,noise=.003;
 let audio=null,audioURL=null,playResolve=null,request=null,listenAfter=0;
 const detector=new TurnDetector();
 let vadChunks=[],vadQueue=[],vadRunning=false,vadGeneration=0,vadSequence=0,vadStream='',vadRequest=null,partialText='',partialSegments=0;
 let automaticBargeIn=false;
 let turnBusy=false,queuedTurn=null;
 const status=text=>ui('voiceStatus').textContent=text;
 function setPhase(value,text){phase=value;status(text);ui('voiceInterrupt').disabled=value!=='speaking';ui('voiceInterrupt').hidden=value!=='speaking';ui('voiceStop').hidden=!active;ui('voiceStart').hidden=active;ui('voicePreview').disabled=active;}
 function resetCapture(){preroll=[];frames=[];recording=false;voiced=quiet=total=0;vadChunks=[];detector.reset();}
 function headers(){const h={'Content-Type':'application/json'};if(token)h['X-Member-Session']=token;if(ui('gateway').value)h.Authorization='Bearer '+ui('gateway').value;return h;}
 async function post(path,body,signal){const r=await fetch(path,{method:'POST',headers:headers(),body:JSON.stringify(body),signal});if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.detail||'语音服务连接失败')}return r;}
 function stopPlayback(){
  if(request){request.abort();request=null}
  if(audio){audio.pause();audio.src='';audio=null}
  if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null}
  window.speechSynthesis?.cancel();if(playResolve){const resolve=playResolve;playResolve=null;resolve()}
 }
 function listen(){if(!active)return;resetCapture();listenAfter=performance.now()+150;setPhase('listening','我在听，你可以慢慢说');ui('voiceCaption').textContent=partialText?'已记下前半句，请继续说。':'说完停顿约两秒，我会回应。';}
 function deviceSpeak(text,style={}){return new Promise((resolve,reject)=>{
  const synth=window.speechSynthesis;if(!synth){reject(Error('此浏览器不支持设备朗读'));return}
  const voices=synth.getVoices().filter(v=>v.localService&&/^zh/i.test(v.lang));
  if(!voices.length){reject(Error('未找到本地中文声音，请选择晓晓、晓伊或云希'));return}
  const utterance=new SpeechSynthesisUtterance(text);utterance.voice=voices[0];utterance.lang='zh-CN';utterance.rate=Math.max(.75,Math.min(1.25,(1+Number(ui('voiceRate').value)/100)*(style.speed||1)));utterance.volume=style.volume??1;
  playResolve=resolve;utterance.onend=()=>{playResolve=null;resolve()};utterance.onerror=e=>{playResolve=null;if(e.error==='canceled'||e.error==='interrupted')resolve();else reject(Error('设备朗读失败，请换一种声音'))};synth.speak(utterance);
 });}
 async function say(text,run,style={}){
  if(!text)return;
  if(ui('voiceChoice').value==='device'){if(active)setPhase('speaking','我正在说，随时可以点击打断');await deviceSpeak(text,style);return}
  if(!window.setupController.cloudAllowed()){window.setupController.require('请先确认允许在线自然朗读，或选择设备自带声音。');throw Error('尚未确认在线朗读许可')}
  if(active)setPhase('synthesizing','正在准备自然语音…');
  request=new AbortController();const localRequest=request;
  const r=await post('/v1/voice/speak',{text:text.slice(0,1200),voice:ui('voiceChoice').value,rate:Math.max(-25,Math.min(25,Math.round(Number(ui('voiceRate').value)+((style.speed||1)-1)*100)))},localRequest.signal);
  const blob=await r.blob();if(run!==epoch||recording||queuedTurn)return;
  request=null;audioURL=URL.createObjectURL(blob);audio=new Audio(audioURL);audio.volume=style.volume??1;
  if(active)setPhase('speaking','我正在说，随时可以点击打断');
  try{await new Promise((resolve,reject)=>{playResolve=resolve;audio.onended=()=>{playResolve=null;resolve()};audio.onerror=()=>{playResolve=null;reject(Error('播放失败，请检查扬声器或重试'))};audio.play().catch(()=>{playResolve=null;reject(Error('浏览器阻止了播放，请点试听后再开始对话'))})})}
  finally{if(audio){audio.pause();audio=null}if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null}}
 }
 function encodeWav(chunks,rate){
  const length=chunks.reduce((sum,c)=>sum+c.length,0);const merged=new Float32Array(length);let offset=0;for(const c of chunks){merged.set(c,offset);offset+=c.length}
  const ratio=rate/16000,count=Math.floor(length/ratio),buffer=new ArrayBuffer(44+count*2),v=new DataView(buffer);
  const str=(at,s)=>{for(let i=0;i<s.length;i++)v.setUint8(at+i,s.charCodeAt(i))};str(0,'RIFF');v.setUint32(4,36+count*2,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,count*2,true);
  for(let i=0;i<count;i++){const begin=Math.floor(i*ratio),end=Math.max(begin+1,Math.floor((i+1)*ratio));let sum=0;for(let j=begin;j<end&&j<length;j++)sum+=merged[j];const x=Math.max(-1,Math.min(1,sum/(end-begin)));v.setInt16(44+i*2,x<0?x*32768:x*32767,true)}
  const bytes=new Uint8Array(buffer);let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);
 }
 async function processTurn(chunks,sampleRate,continued=false){
  if(turnBusy){
   if(queuedTurn){stop({keepCamera:true});ui('voiceCaption').textContent='收到的语音太快，请稍后重新说；未提交的内容已取消。';return}
   queuedTurn={chunks,sampleRate,continued};return;
  }
  turnBusy=true;
  const run=epoch;setPhase('transcribing','正在听懂这句话…');
  try{
   request=new AbortController();const r=await post('/v1/voice/transcribe',{audio_base64:encodeWav(chunks,sampleRate),session_id:session},request.signal);const result=await r.json();request=null;
   if(!active||run!==epoch)return;
   if(result.quality?.requires_repeat||(!result.text&&!result.voice?.audio_events?.some(e=>e==='Crying'||e==='Laughter'))){partialText='';partialSegments=0;listen();ui('voiceCaption').textContent='这次没听清，请靠近一点重新说；这句话尚未提交。';return}
   if(continued){partialText+=result.text;partialSegments++;if(partialSegments>=3){partialText='';partialSegments=0;queuedTurn=null;listen();ui('voiceCaption').textContent='这段比较长，请分成短一些的句子；尚未提交。';return}if(recording)setPhase('listening','我在听，请继续');else if(!queuedTurn)listen();return}
   result.text=partialText+result.text;partialText='';partialSegments=0;
   if(result.text.length>600){listen();ui('voiceCaption').textContent='这句话较长，请分成两句再说；尚未提交。';return}
   ui('voiceCaption').textContent='你说：'+result.text;
   if(/^(请)?(结束对话|停止语音|退出语音)[。！!，,\s]*$/.test(result.text)){stop();return}
   setPhase('thinking','我听到了，正在想怎么回应…');
   const reply=await submitSpeech(result.text,result.audio_frame_id);if(!active||run!==epoch)return;
   if(reply?.response&&!queuedTurn&&!recording)await say(reply.response,run,reply.response_plan?.voice_style);
   if(active&&run===epoch){if(recording)setPhase('listening','我在听，你继续说');else if(!queuedTurn)listen();}
  }catch(err){if(run!==epoch||!active)return;stop({keepCamera:true});status('语音已暂停，可重试或打字');ui('voiceCaption').textContent=err.message;notify(err.message,true)}
  finally{turnBusy=false;if(active&&queuedTurn){const next=queuedTurn;queuedTurn=null;void processTurn(next.chunks,next.sampleRate,next.continued)}}
 }
 async function drainVad(){
  if(vadRunning)return;vadRunning=true;const generation=vadGeneration;
  try{while(active&&generation===vadGeneration&&vadQueue.length){
   const item=vadQueue.shift(),sequence=vadSequence++;vadRequest=new AbortController();
   const timeout=setTimeout(()=>vadRequest?.abort(),3000);let result;
   try{const wav=atob(encodeWav(item.chunks,item.rate));const r=await post('/v1/voice/activity',{pcm_base64:btoa(wav.slice(44)),session_id:session,stream_id:vadStream,sequence,reset:sequence===0},vadRequest.signal);result=await r.json()}finally{clearTimeout(timeout)}
   if(!active||generation!==vadGeneration)return;
   if((item.phase==='speaking')!==(phase==='speaking')||item.epoch!==epoch)continue;
   const seconds=item.chunks.reduce((n,x)=>n+x.length,0)/item.rate;
   preroll.push(...item.chunks);while(preroll.reduce((n,x)=>n+x.length,0)/item.rate>.65)preroll.shift();
   const action=detector.update(result.probabilities,seconds,phase==='speaking'?'speaking':'listening');
   if(action==='interrupt'){
    const saved=preroll.slice();epoch++;stopPlayback();listen();frames=saved;preroll=[];detector.recording=true;detector.voice=.384;detector.total=saved.reduce((n,x)=>n+x.length,0)/item.rate;recording=true;ui('voiceCaption').textContent='已暂停，你继续说。';
   }else if(action==='start'){frames=preroll.slice();preroll=[];recording=true;ui('voiceCaption').textContent='听到你了，慢慢说…'}
   else if(recording){frames.push(...item.chunks);if(action==='end'||action==='continue'){const segment=frames;resetCapture();void processTurn(segment,item.rate,action==='continue')}}
  }}catch(err){if(active&&generation===vadGeneration){stop({keepCamera:true});ui('voiceCaption').textContent='语音检测中断，尚未提交未完成的句子。请重新开始或打字。';notify(err.message,true)}}
  finally{if(generation===vadGeneration){vadRunning=false;vadRequest=null}}
 }
 function capture(event){
  if(!active||!['listening','speaking','transcribing','thinking','synthesizing'].includes(phase)||(phase==='speaking'&&!automaticBargeIn)||performance.now()<listenAfter){vadChunks=[];return}
  const data=new Float32Array(event.inputBuffer.getChannelData(0));let power=0;for(const x of data)power+=x*x;
  ui('micLevel').style.width=Math.min(100,Math.sqrt(power/data.length)*1400)+'%';vadChunks.push(data);
  if(vadChunks.reduce((n,x)=>n+x.length,0)/context.sampleRate<.24)return;
  if(vadQueue.length>=3){stop({keepCamera:true});ui('voiceCaption').textContent='语音处理跟不上，请重新开始或改用文字。';return}
  vadQueue.push({chunks:vadChunks,rate:context.sampleRate,phase,epoch});vadChunks=[];void drainVad();
 }
 async function start(){
  if(!window.setupController.ready())return;
  if(active||chatBusy||turnBusy)return;if(!navigator.mediaDevices?.getUserMedia){notify('请在本机 Edge 或 Chrome 打开页面使用麦克风。',true);return}
  stopPlayback();const run=++epoch;active=true;ui('voiceStart').disabled=true;ui('voiceStop').disabled=false;setPhase('starting','正在连接麦克风…');
  try{
   const options=await api('/v1/voice/options');if(!options.recognition_ready||!options.activity_ready)throw Error('语音模型尚未准备好，请稍后重试');if(run!==epoch)return;
   vadStream=crypto.randomUUID();vadSequence=0;vadGeneration++;vadQueue=[];vadChunks=[];vadRunning=false;partialText='';partialSegments=0;
   const input=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
   if(run!==epoch){input.getTracks().forEach(t=>t.stop());return}mic=input;
   automaticBargeIn=mic.getAudioTracks().some(t=>t.getSettings?.().echoCancellation===true);
   for(const track of mic.getTracks())track.onended=()=>{if(active){stop();status('麦克风已断开，请重新连接')}};
   context=new (window.AudioContext||window.webkitAudioContext)();await context.resume();if(run!==epoch)return;
   source=context.createMediaStreamSource(mic);processor=context.createScriptProcessor(4096,1,1);processor.onaudioprocess=capture;source.connect(processor);processor.connect(context.destination);
   if(window.setupController.cameraAllowed())try{await startCamera();if(run!==epoch){stopCamera();return}ui('continuous').checked=true;ui('continuous').dispatchEvent(new Event('change'));}catch(err){notify('摄像头未开启，画面下方显示原因；语音可以继续。',true)}
   if(run===epoch)listen();
  }catch(err){if(run!==epoch)return;stop({keepCamera:true});status('未能开始语音，可重试或打字');ui('voiceCaption').textContent=err.name==='NotAllowedError'?'请允许麦克风权限，然后再次点击开始。':err.message;notify(ui('voiceCaption').textContent,true)}
 }
 function stop({keepCamera=false}={}){
  vadGeneration++;vadRequest?.abort();vadRequest=null;vadRunning=false;vadQueue=[];vadChunks=[];partialText='';partialSegments=0;queuedTurn=null;
  active=false;epoch++;stopPlayback();if(!keepCamera)stopCamera();if(processor){processor.onaudioprocess=null;processor.disconnect();processor=null}if(source){source.disconnect();source=null}if(mic){mic.getTracks().forEach(t=>t.stop());mic=null}if(context){void context.close();context=null}resetCapture();ui('micLevel').style.width='0';ui('voiceStart').disabled=false;ui('voiceStop').disabled=true;setPhase('idle','语音已暂停');ui('voiceCaption').textContent='点击开始，可以继续聊；也可以直接打字。';
 }
 ui('voiceStart').onclick=start;ui('voiceStop').onclick=()=>stop({keepCamera:true});
 ui('voiceInterrupt').onclick=()=>{if(phase==='speaking'){epoch++;stopPlayback();listen()}};
 ui('voicePreview').onclick=async()=>{if(active)return;stopPlayback();const run=++epoch;ui('voicePreview').disabled=true;window.setupController.previewStarting();try{await say('你好，我在这里。今天过得怎么样？慢慢说，我听着呢。',run);if(run===epoch)window.setupController.previewResult(true,'试听已播放。听见后请点击“我听到了”。')}catch(err){if(run===epoch){window.setupController.previewResult(false,err.message+'。可以返回选择其他声音，或改用文字。');notify(err.message,true)}}finally{if(run===epoch)ui('voicePreview').disabled=false}};
 function cancelPreview(){if(active)return;epoch++;stopPlayback();ui('voicePreview').disabled=false}
 window.voiceConversation={get active(){return active},get phase(){return phase},start,stop,cancelPreview};
 window.addEventListener('pagehide',()=>stop());
 if(window.speechSynthesis)window.speechSynthesis.getVoices();
})();
