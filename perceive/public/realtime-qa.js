import {LiveConnection} from './live.js';
import {audioFromVideo,frameData} from './media.js';
const report=document.getElementById('report'),video=document.getElementById('sample'),button=document.getElementById('run');
button.onclick=async()=>{
  const log={phase:'准备',cameraAccess:false,microphoneAccess:false,transcriptUpdates:0,results:[],states:[],notices:[],faceMeasurements:0,specialistMeasurements:[],liveSignals:0};
  const show=()=>report.textContent=JSON.stringify(log,null,2);let context,connection,stream,timer,source,worker,faceTimer;button.disabled=true;show();
  try{
    const status=await(await fetch('/api/status')).json();if(!status.configured)throw new Error('先在主页面设置模型。');
    log.model=status.model;
    const audio=await audioFromVideo(await(await fetch('/assets/yann-lecun-wef.mp4')).blob());
    context=new AudioContext({sampleRate:16000});await context.resume();
    const destination=context.createMediaStreamDestination();stream=destination.stream;
    const buffer=context.createBuffer(1,audio.length,16000);buffer.copyToChannel(audio,0);source=context.createBufferSource();source.buffer=buffer;source.loop=true;source.connect(destination);
    let begin=performance.now();
    connection=new LiveConnection(status,{offset:()=>(performance.now()-begin)/1000,onEvent:event=>{
      if(event.type==='transcript'){log.transcriptUpdates++;log.preview=event.text;}
      if(event.type==='measurement')log.specialistMeasurements.push(event);if(event.type==='result')log.results.push(event);if(event.type==='state'){log.states.push(event);if(log.phase==='持续音视频输入')log.liveSignals+=event.changes.filter(e=>e.type==='detected').length;}
      if(event.type==='notice'){log.notice=event.message;log.notices.push(event);}
      show();
    },onError:error=>{log.error=error.message;show();}});
    log.phase='连接中';show();await connection.connect();await connection.startAudio(stream);
    worker=new Worker('/face-worker.js');await new Promise((resolve,reject)=>{worker.onmessage=({data})=>{if(data.type==='ready')resolve();if(data.type==='error')reject(new Error(data.message));};worker.postMessage({type:'init'});});let busy=false;worker.onmessage=({data})=>{busy=false;if(data.type==='result'){connection.face(data);log.faceMeasurements++;}};begin=performance.now();video.currentTime=0;video.loop=true;await video.play();source.start();log.phase='持续音视频输入';show();faceTimer=setInterval(async()=>{if(busy)return;busy=true;const image=await createImageBitmap(video);worker.postMessage({type:'frame',image,t:(performance.now()-begin)/1000},[image]);},200);
    timer=setInterval(()=>connection.image(frameData(video,(performance.now()-begin)/1000)),500);
    await new Promise(resolve=>setTimeout(resolve,22000));source.stop();clearInterval(timer);clearInterval(faceTimer);video.pause();
    log.phase='接收最后结果';show();await connection.finish();
    log.inputSeconds=22;log.checks={transcription:log.transcriptUpdates>0,fusion:log.results.length>1,face:log.specialistMeasurements.some(e=>e.kind==='face'),voice:log.specialistMeasurements.some(e=>e.kind==='voice'),labelsWhileLive:log.liveSignals>0,noErrors:!log.error&&log.notices.length===0};log.passed=Object.values(log.checks).every(Boolean);log.phase='完成';show();
  }catch(error){log.phase='失败';log.error=error.message;show();}
  finally{clearInterval(timer);clearInterval(faceTimer);worker?.terminate();video.pause();connection?.close();stream?.getTracks().forEach(t=>t.stop());try{source?.stop();await context?.close();}catch{}button.disabled=false;}
};
