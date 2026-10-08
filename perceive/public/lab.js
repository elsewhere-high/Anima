import {observeStream,finishObservedStream} from './app.js';
import {audioFromVideo} from './media.js';
const button=document.getElementById('lab-run'),status=document.getElementById('lab-status');
button.onclick=async()=>{
  button.disabled=true;let source,ctx,stream,draw,video,canvas;
  try{
    status.textContent='准备公开素材';
    const samples=await audioFromVideo(await(await fetch('/assets/yann-lecun-wef.mp4')).blob());
    ctx=new AudioContext({sampleRate:16000});await ctx.resume();const dest=ctx.createMediaStreamDestination(),buffer=ctx.createBuffer(1,samples.length,16000);buffer.copyToChannel(samples,0);source=ctx.createBufferSource();source.buffer=buffer;source.loop=true;source.connect(dest);
    video=document.createElement('video');video.src='/assets/yann-lecun-wef.mp4';video.muted=true;video.loop=true;video.playsInline=true;await video.play();
    canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;canvas.className='lab-canvas';document.body.append(canvas);
    const paint=canvas.getContext('2d');paint.drawImage(video,0,0,640,360);stream=canvas.captureStream(0);dest.stream.getAudioTracks().forEach(t=>stream.addTrack(t));
    draw=setInterval(()=>{paint.drawImage(video,0,0,640,360);stream.getVideoTracks()[0].requestFrame?.();},33);
    await observeStream(stream);video.currentTime=0;source.start();status.textContent='真实接口 · 正在观察公开素材';
    await new Promise(resolve=>setTimeout(resolve,24000));source.stop();const saved=await finishObservedStream();status.textContent='完成 · 可点记录、标签和回放';
    document.getElementById('lab-report').textContent=JSON.stringify({events:saved.events,log:saved.log,duration:saved.duration},null,2);
  }catch(e){status.textContent=e.message;}
  finally{clearInterval(draw);stream?.getTracks().forEach(t=>t.stop());video?.pause();canvas?.remove();try{source?.stop();await ctx?.close();}catch{}button.disabled=false;}
};
