import {LiveConnection} from './live.js';
import {audioFromVideo,frameData} from './media.js';
import {LiveViewState} from './live-state.js';
const clips=['yann-lecun-wef','steve-jobs-interview','elon-musk-wef','pep-guardiola-press','mark-zuckerberg-interview'];
const video=document.getElementById('sample'),button=document.getElementById('run'),report=document.getElementById('report');
button.onclick=async()=>{
  button.disabled=true;let worker;
  const log={createdAt:new Date().toISOString(),protocol:'current-production-unchanged',scope:'三轮实时因果输入，无官网标签输入；无人工准确率真值',cameraAccess:false,microphoneAccess:false,phase:'准备',runs:[]};
  const show=()=>report.textContent=JSON.stringify(log,null,2);
  try{
    const status=await(await fetch('/api/status')).json();if(!status.configured)throw new Error('模型未配置');
    log.models={fusion:status.reviewModel,specialists:status.specialists};
    worker=new Worker('/face-worker.js');
    await new Promise((resolve,reject)=>{worker.onmessage=({data})=>{if(data.type==='ready')resolve();if(data.type==='error')reject(new Error(data.message));};worker.postMessage({type:'init'});});
    const audio=new Map();for(const id of clips)audio.set(id,await audioFromVideo(await(await fetch(`/assets/${id}.mp4`)).blob()));
    for(let round=1;round<=3;round++)for(const id of clips){
      const run={id,round,events:[],display:[],captureDriftMs:[],notices:[]};log.runs.push(run);log.phase=`第 ${round} 轮 · ${id}`;show();
      let source,ctx,stream,connection,imageTimer,faceTimer,viewTimer,startedAt=0,ended=false;
      const view=new LiveViewState();let displayKey='';
      try{
        video.src=`/assets/${id}.mp4`;video.loop=false;
        await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(new Error('素材读取失败'));});
        const samples=audio.get(id);run.duration=Math.min(video.duration,samples.length/16000);
        ctx=new AudioContext({sampleRate:16000});await ctx.resume();const dest=ctx.createMediaStreamDestination();stream=dest.stream;
        const buffer=ctx.createBuffer(1,samples.length,16000);buffer.copyToChannel(samples,0);source=ctx.createBufferSource();source.buffer=buffer;source.connect(dest);
        connection=new LiveConnection(status,{offset:()=>0,onEvent:event=>{
          if(!startedAt)return;
          const receivedAt=(performance.now()-startedAt)/1000;
          run.events.push({...event,clientReceivedAt:receivedAt,afterStop:ended});view.accept(event);
          if(event.type==='notice')run.notices.push(event);
        },onError:error=>{run.error=error.message;}});
        await connection.connect();
        let faceBusy=false;worker.onmessage=({data})=>{faceBusy=false;if(data.type==='result'&&!ended)connection.face(data);};
        await connection.startAudio(stream);startedAt=performance.now();source.start();await video.play();run.playbackAlignmentMs=Math.round(performance.now()-startedAt);
        imageTimer=setInterval(()=>{connection.image(frameData(video,video.currentTime));run.captureDriftMs.push(Math.round(((performance.now()-startedAt)/1000-video.currentTime)*1000));},500);
        faceTimer=setInterval(async()=>{if(faceBusy||ended)return;faceBusy=true;const image=await createImageBitmap(video);if(ended){image.close();faceBusy=false;return;}worker.postMessage({type:'frame',image,t:video.currentTime},[image]);},200);
        viewTimer=setInterval(()=>{
          const at=(performance.now()-startedAt)/1000,current=view.view(at),key=current.signals.map(s=>s.id+':'+s.tentative).join('|');
          if(key!==displayKey){displayKey=key;run.display.push({at,signals:current.signals.map(s=>({id:s.id,label:s.label,source:s.source,start:s.start,end:s.end,detectedAt:s.detectedAt,tentative:s.tentative}))});}
        },100);
        await new Promise(resolve=>setTimeout(resolve,Math.max(0,run.duration*1000-(performance.now()-startedAt))));
        ended=true;run.stoppedAt=(performance.now()-startedAt)/1000;clearInterval(imageTimer);clearInterval(faceTimer);clearInterval(viewTimer);source.stop();video.pause();
        await connection.finish();run.completedAt=(performance.now()-startedAt)/1000;
      }catch(error){run.error=error.message;}
      finally{ended=true;clearInterval(imageTimer);clearInterval(faceTimer);clearInterval(viewTimer);connection?.close();video.pause();try{source?.stop();await ctx?.close();}catch{}stream?.getTracks().forEach(t=>t.stop());show();}
    }
    log.phase='完成';log.passed=log.runs.length===15&&log.runs.every(r=>!r.error);show();
  }catch(error){log.phase='失败';log.error=error.message;show();}
  finally{worker?.terminate();button.disabled=false;}
};
