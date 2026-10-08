import {audioFromVideo,encodeWav,toBase64,frameData} from './media.js';
const video=document.getElementById('sample'),button=document.getElementById('run'),report=document.getElementById('report');
button.onclick=async()=>{
  button.disabled=true;let worker;const log={scope:'同一公开片段的输入消融，仅验证集成与输入边界，不证明准确率',runs:[]};const show=()=>report.textContent=JSON.stringify(log,null,2);
  try{
    const status=await(await fetch('/api/status')).json();if(!status.configured)throw new Error('请先配置模型');
    const audio=await audioFromVideo(await(await fetch('/assets/yann-lecun-wef.mp4')).blob());
    const duration=Math.min(5,audio.length/16000),input={start:0,duration,audio:{mimeType:'audio/wav',data:await toBase64(encodeWav(audio.subarray(0,Math.round(duration*16000))))},frames:[],face:[],context:[]};
    worker=new Worker('/face-worker.js');await new Promise((resolve,reject)=>{worker.onmessage=({data})=>data.type==='ready'?resolve():data.type==='error'?reject(new Error(data.message)):null;worker.postMessage({type:'init'});});
    for(let t=.2;t<duration;t+=1.2){await new Promise(resolve=>{video.onseeked=resolve;video.currentTime=t;});input.frames.push(frameData(video,t));const image=await createImageBitmap(video);input.face.push(await new Promise(resolve=>{worker.onmessage=({data})=>resolve(data);worker.postMessage({type:'frame',t,image},[image]);}));}
    for(const mode of ['full','baseline','audio','video']){log.phase=mode;show();const response=await fetch('/api/evaluate',{method:'POST',headers:{'Content-Type':'application/json','X-Anima-Token':status.token},body:JSON.stringify({mode,input})}),result=await response.json();log.runs.push({mode,status:response.status,...result});show();}
    log.phase='完成';log.passed=log.runs.every(x=>x.status===200)&&log.runs.find(x=>x.mode==='audio').signals.every(s=>!s.modalities.includes('画面'))&&log.runs.find(x=>x.mode==='video').signals.every(s=>!s.modalities.includes('声音')&&!s.modalities.includes('语意'));show();
  }catch(e){log.error=e.message;show();}finally{worker?.terminate();button.disabled=false;}
};
