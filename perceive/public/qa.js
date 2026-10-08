import {audioFromVideo} from './media.js';
const result=document.getElementById('result');
document.getElementById('run').onclick=async()=>{
  const report={};document.getElementById('run').disabled=true;const show=()=>result.textContent=JSON.stringify(report,null,2);let mic,worker,context;
  try{
    report.face='加载中';show();
    worker=new Worker('/face-worker.js');
    await new Promise((resolve,reject)=>{worker.onmessage=({data})=>data.type==='ready'?resolve():data.type==='error'?reject(new Error(data.detail||data.message)):null;worker.onerror=reject;worker.postMessage({type:'init'});});
    report.face=[];
    for(const id of ['yann-lecun-wef','steve-jobs-interview','elon-musk-wef','pep-guardiola-press','mark-zuckerberg-interview']){
      const image=await createImageBitmap(await(await fetch(`/assets/${id}.jpg`)).blob());
      const detection=await new Promise((resolve,reject)=>{worker.onmessage=({data})=>data.type==='result'?resolve(data):reject(new Error(data.detail||data.message));worker.postMessage({type:'frame',image,t:0},[image]);});report.face.push({id,...detection});show();
    }
    worker.terminate();show();
    report.vad='加载中';show();const blob=await(await fetch('/assets/yann-lecun-wef.mp4')).blob(),audio=await audioFromVideo(blob);
    context=new AudioContext({sampleRate:16000});await context.resume();const destination=context.createMediaStreamDestination(),buffer=context.createBuffer(1,audio.length,16000);buffer.copyToChannel(audio,0);const source=context.createBufferSource();source.buffer=buffer;source.connect(destination);
    let frames=0,maxProbability=0,speechStarts=0,speechEnds=0;
    window.ort.env.wasm.numThreads=1;
    mic=await window.vad.MicVAD.new({model:'v6',startOnLoad:false,redemptionMs:850,minSpeechMs:300,baseAssetPath:'/vendor/vad/',onnxWASMBasePath:'/vendor/ort/',getStream:async()=>destination.stream,pauseStream:async()=>{},resumeStream:async()=>destination.stream,
      onFrameProcessed:(p)=>{frames++;maxProbability=Math.max(maxProbability,p.isSpeech);},onSpeechStart:()=>speechStarts++,onSpeechEnd:()=>speechEnds++});
    await mic.start();source.start();await new Promise(resolve=>{source.onended=()=>setTimeout(resolve,1300)});await mic.pause();
    report.vad={model:'Silero v6',inputSeconds:audio.length/16000,frames,maxProbability,speechStarts,speechEnds};show();
    const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;canvas.getContext('2d').fillRect(0,0,320,240);
    if(canvas.captureStream){document.body.append(canvas);const stream=canvas.captureStream(0);destination.stream.getAudioTracks().forEach(t=>stream.addTrack(t));const parts=[],recorder=new MediaRecorder(stream);recorder.ondataavailable=e=>parts.push(e.data);recorder.start(200);const replay=context.createBufferSource();replay.buffer=buffer;replay.connect(destination);replay.start();let counter=0;const timer=setInterval(()=>{const ctx=canvas.getContext('2d');ctx.fillStyle=`hsl(${counter++*10},50%,50%)`;ctx.fillRect(0,0,320,240);stream.getVideoTracks()[0].requestFrame?.();},50);await new Promise(r=>setTimeout(r,1600));clearInterval(timer);await new Promise(resolve=>{recorder.onstop=resolve;recorder.stop()});report.recording={bytes:new Blob(parts).size,type:recorder.mimeType};stream.getTracks().forEach(t=>t.stop());replay.stop();canvas.remove();}else report.recording={unavailable:'此浏览器不支持 canvas.captureStream，仅设备录制接口可用。'};
    report.passed=report.face.some(f=>f.faces===1)&&frames>0&&maxProbability>.5;show();
  }catch(e){report.error=String(e.message||e);show();}
  finally{worker?.terminate();try{await mic?.destroy();await context?.close();}catch{}document.getElementById('run').disabled=false;}
};
