import {audioFromVideo,encodeWav,toBase64,frameData} from './media.js';
import {cases} from './cases.js';
const video=document.getElementById('sample'),button=document.getElementById('run'),report=document.getElementById('report');
button.onclick=async()=>{
 button.disabled=true;let worker;const log={createdAt:new Date().toISOString(),scope:'真实模型对公开案例的离线分析，不是人工真值，不代表实时提前识别',results:[]};const show=()=>report.textContent=JSON.stringify(log,null,2);
 try{
  const status=await(await fetch('/api/status')).json();if(!status.configured)throw new Error('先配置模型');worker=new Worker('/face-worker.js');await new Promise((resolve,reject)=>{worker.onmessage=({data})=>data.type==='ready'?resolve():data.type==='error'?reject(new Error(data.message)):null;worker.postMessage({type:'init'});});
  for(const c of cases){
   log.phase=c.name;show();video.src=`/assets/${c.id}.mp4`;await new Promise(resolve=>{video.onloadedmetadata=resolve;});
   const audio=await audioFromVideo(await(await fetch(video.src)).blob()),duration=Math.min(video.duration,audio.length/16000),input={duration,audio:{mimeType:'audio/wav',data:await toBase64(encodeWav(audio))},frames:[],face:[],context:[]};
   for(let t=.15;t<duration;t+=Math.max(.8,duration/7)){await new Promise(resolve=>{video.onseeked=resolve;video.currentTime=t;});input.frames.push(frameData(video,t));const image=await createImageBitmap(video);input.face.push(await new Promise(resolve=>{worker.onmessage=({data})=>resolve(data);worker.postMessage({type:'frame',t,image},[image]);}));}
   const response=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json','X-Anima-Token':status.token},body:JSON.stringify(input)}),result=await response.json();log.results.push({id:c.id,duration,status:response.status,...result});show();
  }log.phase='完成';log.passed=log.results.length===5&&log.results.every(r=>r.status===200);show();
 }catch(e){log.error=e.message;show();}finally{worker?.terminate();button.disabled=false;}
};
