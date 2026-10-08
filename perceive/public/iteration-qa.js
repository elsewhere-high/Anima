import {LiveConnection} from './live.js';
import {audioFromVideo,frameData} from './media.js';
import {LiveViewState} from './live-state.js';
const options=new URLSearchParams(location.search);
const suite=options.get('suite')==='cremad-neutral'?'cremad-neutral':'interhuman';
const clips=suite==='cremad-neutral'?['1001_DFA_NEU_XX','1002_DFA_NEU_XX','1003_DFA_NEU_XX','1004_IEO_NEU_XX','1005_DFA_NEU_XX','1006_DFA_NEU_XX']:
  ['yann-lecun-wef','steve-jobs-interview','elon-musk-wef','pep-guardiola-press','mark-zuckerberg-interview'];
const asset=id=>`${suite==='cremad-neutral'?'/research-assets/cremad':'/assets'}/${id}.mp4`;
const selected=options.get('clips')?.split(',').filter(id=>clips.includes(id))||clips;
const rounds=Math.min(3,Math.max(1,Number(options.get('rounds'))||1));
const control=['blank','mute','no-video'].includes(options.get('control'))?options.get('control'):null;
const video=document.getElementById('sample'),button=document.getElementById('run'),report=document.getElementById('report');
button.onclick=async()=>{
  button.disabled=true;let worker;
  const log={variant:options.get('variant')||'unspecified',suite,requestedRounds:rounds,control,createdAt:new Date().toISOString(),protocol:'candidate-core-aligned-live-with-silero-v6',scope:'真实时钟测试；音频在检测器准备完成后才开始传输。参考覆盖不等于人工准确率。控制实验仅检查移除模态后的不当归因。',cameraAccess:false,microphoneAccess:false,phase:'准备',runs:[]};
  const show=()=>report.textContent=JSON.stringify(log,null,2);
  try{
    const status=await(await fetch('/api/status')).json();if(!status.configured)throw new Error('模型未配置');
    log.models={fusion:status.reviewModel,fast:status.fastModel,specialists:status.specialists};
    worker=new Worker('/face-worker.js');
    await new Promise((resolve,reject)=>{worker.onmessage=({data})=>{if(data.type==='ready')resolve();if(data.type==='error')reject(new Error(data.message));};worker.postMessage({type:'init',presenceDetection:options.get('presence')==='detector'});});
    const audio=new Map();for(const id of selected)audio.set(id,await audioFromVideo(await(await fetch(asset(id))).blob()));
    for(let round=1;round<=rounds;round++)for(const id of selected){
      const run={id,round,events:[],display:[],captureDriftMs:[],notices:[]};log.runs.push(run);log.phase=`第 ${round} 轮 · ${id}`;show();
      let source,ctx,stream,connection,vad,imageTimer,faceTimer,viewTimer,startedAt=0,ended=false;
      const view=new LiveViewState();let displayKey='';
      try{
        video.src=asset(id);video.loop=false;
        await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(new Error('素材读取失败'));});
        const original=audio.get(id),samples=['blank','mute'].includes(control)?new Float32Array(original.length):original;run.duration=Math.min(video.duration,samples.length/16000);
        ctx=new AudioContext({sampleRate:16000});await ctx.resume();const dest=ctx.createMediaStreamDestination();stream=dest.stream;
        const buffer=ctx.createBuffer(1,samples.length,16000);buffer.copyToChannel(samples,0);source=ctx.createBufferSource();source.buffer=buffer;source.connect(dest);
        connection=new LiveConnection(status,{offset:()=>0,onEvent:event=>{
          if(!startedAt)return;
          const receivedAt=(performance.now()-startedAt)/1000;
          run.events.push({...event,clientReceivedAt:receivedAt,afterStop:ended});view.accept(event);
          if(event.type==='notice')run.notices.push(event);
        },onError:error=>{run.error=error.message;}});
        await connection.connect();
        run.facePresence=[];
        let faceBusy=false;worker.onmessage=({data})=>{faceBusy=false;if(data.type==='result'&&!ended){run.facePresence.push({t:data.t,faces:data.faces,landmarkFaces:data.landmarkFaces,detectedFaces:data.detectedFaces});connection.face(data);}};
        await connection.startAudio(stream,{paused:true});
        window.ort.env.wasm.numThreads=1;run.activity=[];
        vad=await window.vad.MicVAD.new({model:'v6',startOnLoad:false,baseAssetPath:'/vendor/vad/',onnxWASMBasePath:'/vendor/ort/',redemptionMs:500,minSpeechMs:250,
          getStream:async()=>new MediaStream(stream.getAudioTracks()),pauseStream:async()=>{},resumeStream:async()=>new MediaStream(stream.getAudioTracks()),
          onSpeechStart:()=>{if(!ended){connection.send({type:'activity',speaking:true});run.activity.push({at:(performance.now()-startedAt)/1000,speaking:true});}},
          onSpeechEnd:()=>{if(!ended){connection.send({type:'activity',speaking:false});connection.commit();run.activity.push({at:(performance.now()-startedAt)/1000,speaking:false});}}
        });await vad.start();run.vadReady=true;
        await connection.resumeAudio();startedAt=performance.now();source.start();await video.play();run.playbackAlignmentMs=Math.round(performance.now()-startedAt);
        const hiddenVideo=['blank','no-video'].includes(control),blank=document.createElement('canvas');blank.width=640;blank.height=360;blank.getContext('2d').fillRect(0,0,640,360);
        imageTimer=setInterval(()=>{connection.image(hiddenVideo?{image:blank.toDataURL('image/jpeg').split(',')[1],brightness:0,t:video.currentTime}:frameData(video,video.currentTime));run.captureDriftMs.push(Math.round(((performance.now()-startedAt)/1000-video.currentTime)*1000));},500);
        faceTimer=setInterval(async()=>{if(faceBusy||ended)return;faceBusy=true;const image=await createImageBitmap(hiddenVideo?blank:video);if(ended){image.close();faceBusy=false;return;}worker.postMessage({type:'frame',image,t:video.currentTime},[image]);},200);
        viewTimer=setInterval(()=>{
          const at=(performance.now()-startedAt)/1000,current=view.view(at),key=current.signals.map(s=>s.id+':'+s.tentative).join('|');
          if(key!==displayKey){displayKey=key;run.display.push({at,signals:current.signals.map(s=>({id:s.id,code:s.code,label:s.label,source:s.source,start:s.start,end:s.end,detectedAt:s.detectedAt,tentative:s.tentative}))});}
        },100);
        await new Promise(resolve=>setTimeout(resolve,Math.max(0,run.duration*1000-(performance.now()-startedAt))));
        ended=true;run.stoppedAt=(performance.now()-startedAt)/1000;run.sentAudioSeconds=(connection.audioSamples||0)/16000;clearInterval(imageTimer);clearInterval(faceTimer);clearInterval(viewTimer);source.stop();video.pause();
        await connection.finish();run.completedAt=(performance.now()-startedAt)/1000;
      }catch(error){run.error=error.message;}
      finally{
        ended=true;clearInterval(imageTimer);clearInterval(faceTimer);clearInterval(viewTimer);connection?.close();await vad?.destroy();video.pause();try{source?.stop();await ctx?.close();}catch{}stream?.getTracks().forEach(t=>t.stop());
        try{
          const response=await fetch('/api/research/run',{method:'POST',headers:{'Content-Type':'application/json','X-Anima-Token':status.token},body:JSON.stringify({...log,runs:[run]}),signal:AbortSignal.timeout(5000)});
          if(!response.ok)throw new Error('研究记录自动保存失败');
          run.autosaved=true;
        }catch(error){run.autosaveError=error.message;}
        show();
      }
    }
    log.phase='完成';log.passed=log.runs.length===selected.length*rounds&&log.runs.every(r=>!r.error);show();
  }catch(error){log.phase='失败';log.error=error.message;show();}
  finally{worker?.terminate();button.disabled=false;}
};
