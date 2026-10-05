'use strict';
(() => {
 let opening=null,generation=0,lease=null,timer=null,latest=null,leaseHeaders=null,releasing=Promise.resolve();
 const tab=crypto.randomUUID();const channel=window.BroadcastChannel?new BroadcastChannel('companion-camera'):null;
 const status=(text,error=false)=>{$('cameraStatus').textContent=text;$('cameraStatus').classList.toggle('camera-error',error)};
 function headers(){const h={};if(token)h['X-Member-Session']=token;if($('gateway').value)h.Authorization='Bearer '+$('gateway').value;return h;}
 function explain(error){
  const messages={NotAllowedError:'摄像头权限未允许。点击地址栏左侧的网站权限，允许摄像头后重试。',NotFoundError:'没有找到摄像头，请检查设备连接或笔记本摄像头开关。',NotReadableError:'浏览器无法启动摄像头，可选择“本机兼容模式”后重试。',OverconstrainedError:'当前摄像头不支持所选格式，请选择自动模式重试。',AbortError:'摄像头启动被中断，请重试。'};
  return messages[error.name]||error.message||'摄像头连接失败，请重试。';
 }
 async function poll(run){
  if(run!==generation||!lease)return;
  try{
   const r=await fetch('/v1/camera/frame',{headers:{...leaseHeaders,'X-Camera-Lease':lease},cache:'no-store'});
   if(!r.ok){const body=await r.json();throw Error(body.detail||'摄像头连接中断')}
   const blob=await r.blob();const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob)});
   if(run!==generation)return;latest=data;$('cameraPreview').src=data;await $('cameraPreview').decode();
   if(run!==generation)return;
   $('cameraPreview').hidden=false;$('video').hidden=true;$('cameraPlaceholder').hidden=true;
   timer=setTimeout(()=>void poll(run),160);
  }catch(error){if(run!==generation)return;stop();status(explain(error),true)}
 }
 async function compatible(run){
  const h=headers();const r=await fetch('/v1/camera/start',{method:'POST',headers:h});const body=await r.json();
  if(!r.ok)throw Error(body.detail||'兼容摄像头启动失败');
  if(run!==generation){void fetch('/v1/camera/stop',{method:'POST',headers:{...h,'X-Camera-Lease':body.lease}});return}
  lease=body.lease;leaseHeaders=h;stream={compat:true,getTracks:()=>[]};
  await poll(run);if(run!==generation||!stream)return;
  sessionStorage.setItem('companion-camera-mode','compat');status('摄像头已开启 · 本机兼容模式 · 画面不保存');
 }
 async function start(){
  if(stream)return;if(opening)return opening;
  if(window.setupController&&!window.setupController.cameraAllowed()){window.setupController.require();throw Error('请先在页面顶部确认使用摄像头。')}
  const run=++generation;status('正在连接摄像头…');$('cameraOn').disabled=true;
  channel?.postMessage({type:'claim',tab});
  opening=(async()=>{
   try{
    await releasing;if(run!==generation)return;
    let mode=$('cameraMode').value;
    if(mode==='auto'&&sessionStorage.getItem('companion-camera-mode')==='compat')mode='compat';
    if(mode==='compat')await compatible(run);
    else{
     try{
      if(!navigator.mediaDevices?.getUserMedia)throw Error('请在本机 Edge 或 Chrome 打开此页面');
      const s=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:24,max:30}},audio:false});
      if(run!==generation){s.getTracks().forEach(t=>t.stop());return}
      stream=s;$('video').hidden=false;$('cameraPreview').hidden=true;$('video').srcObject=s;
      await $('video').play();if(run!==generation)return;
      $('cameraPlaceholder').hidden=true;
      s.getVideoTracks()[0].onended=()=>{if(run===generation){stop();status('摄像头已断开，点击“开启摄像头”重新连接。',true)}};
      status('摄像头已开启 · 浏览器模式 · 画面不保存');
     }catch(error){
      if(run!==generation)return;
      if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;$('video').srcObject=null}
      if(mode==='auto'&&['NotReadableError','OverconstrainedError','AbortError'].includes(error.name)){
       status('浏览器采集失败，正在切换本机兼容模式…');await compatible(run);
      }else throw error;
     }
    }
    if(run!==generation||!stream)return;
    $('continuous').checked=true;clearTimeout(loop);void tick();
   }catch(error){if(run===generation){stop();status(explain(error),true)}throw error}
   finally{opening=null;sync()}
  })();return opening;
 }
 function stop(){
  generation++;clearTimeout(timer);timer=null;const oldLease=lease,h=leaseHeaders;lease=null;leaseHeaders=null;latest=null;
  if(oldLease)releasing=fetch('/v1/camera/stop',{method:'POST',headers:{...h,'X-Camera-Lease':oldLease},keepalive:true}).catch(()=>{});
  if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;$('video').srcObject=null;$('video').hidden=false;$('cameraPreview').hidden=true;$('cameraPreview').removeAttribute('src');
  lastFrame=null;frameAt=0;$('continuous').checked=false;clearTimeout(loop);$('cameraPlaceholder').hidden=false;
  const c=$('overlay');c.getContext('2d').clearRect(0,0,c.width,c.height);$('expression').textContent='摄像头已关闭';status('摄像头未开启');sync();
 }
 function capture(){
  if(stream?.compat){if(!latest)throw Error('摄像头画面正在准备，请稍候');return latest}
  const v=$('video');if(!stream||!v.videoWidth)throw Error('摄像头画面尚未就绪');const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);return c.toDataURL('image/jpeg',.86);
 }
 if(channel)channel.onmessage=e=>{if(e.data?.type==='claim'&&e.data.tab!==tab&&stream){stop();status('摄像头已交给另一个对话页面；需要时点击重新开启。')}};
 $('cameraMode').onchange=()=>{stop();status('已切换采集方式，点击“开启摄像头”连接。')};
 window.cameraController={start,stop,capture,get revision(){return generation},get active(){return !!stream},get mode(){return stream?.compat?'compat':stream?'browser':'off'}};
})();
