import WebSocket from 'ws';
import {endpoints,REALTIME_MODEL,qwenError,realtimeErrorCode} from './qwen.mjs';
import {SOCIAL_PROMPT,normalizeSocial,parseSocial} from './social.mjs';
import {completedArray} from './fusion.mjs';

// Experimental persistent audiovisual session. No answers, names or reference
// annotations enter this connection. Audio is sent once as it arrives.
export class NativeSocialSession {
  constructor(config,{socketFactory=(url,options)=>new WebSocket(url,options),onTrace=()=>{},rolling=false,prompt=SOCIAL_PROMPT,decode=normalizeSocial,streamRows=true,timingMode='localized'}={}){
    this.timingMode=timingMode;this.decode=decode;this.streamRows=streamRows;this.prompt=prompt;this.rolling=rolling;this.onTrace=onTrace;this.closed=false;this.audioEnd=0;this.committedEnd=0;this.frames=[];this.lastFrame=-1;
    const url=new URL(endpoints(config.workspace,config.region).realtime);url.searchParams.set('model',REALTIME_MODEL);
    this.socket=socketFactory(url.href,{headers:{Authorization:`Bearer ${config.key}`},handshakeTimeout:15000,maxPayload:262144,followRedirects:false});
    this.ready=new Promise((resolve,reject)=>{this.resolveReady=resolve;this.rejectReady=reject;});
    // The owner also awaits ready; this handler prevents unhandled rejections
    // if the other upstream fails first and cleanup closes this socket.
    this.ready.catch(()=>{});
    this.connectTimer=setTimeout(()=>this.fail(new Error('原生状态连接超时')),20000);
    this.socket.on('message',bytes=>{try{this.receive(JSON.parse(bytes));}catch(error){this.fail(error);}});
    this.socket.on('error',()=>this.fail(new Error('原生状态连接失败')));
    this.socket.on('unexpected-response',(_req,res)=>{res.resume();this.fail(new Error(qwenError(res.statusCode)));});
    this.socket.on('close',()=>{if(!this.closed)this.fail(new Error('原生状态连接断开'));});
  }
  send(event){if(this.socket.readyState===WebSocket.OPEN)this.socket.send(JSON.stringify(event));}
  receive(event){
    const failure=realtimeErrorCode(event);
    if(failure){this.onTrace({type:'native_error',code:failure});this.fail(new Error(qwenError(0,failure)));return;}
    if(event.type==='session.created'){
      this.send({type:'session.update',session:{modalities:['text'],instructions:this.prompt,turn_detection:null,
        temperature:.1,max_tokens:450,audio:{input:{format:{type:'pcm',sample_rate:16000,sample_format:'s16le',channels:1,packing:'interleaved',channel_layout:'mono'}}}}});return;
    }
    if(event.type==='session.updated'){
      if(!this.initialized){this.initialized=true;clearTimeout(this.connectTimer);this.resolveReady();}
      else if(this.pending){this.pending.configured=true;this.maybeRespond();}
      return;
    }
    const p=this.pending;if(!p)return;
    if(event.type==='input_audio_buffer.committed'){p.committed=true;this.maybeRespond();return;}
    if(event.type==='response.created'){p.responseId=event.response?.id;return;}
    if(event.type==='response.text.delta'||event.type==='response.audio_transcript.delta'){
      p.firstTokenMs??=Math.round(performance.now()-p.began);p.text+=event.delta||'';
      if(this.streamRows&&/"p"\s*:\s*1\b/.test(p.text)){
        const s=completedArray(p.text,'s'),key=JSON.stringify(s);
        if(s.length&&key!==p.lastRows){p.lastRows=key;p.firstRowMs??=Math.round(performance.now()-p.began);p.onPartial(normalizeSocial({p:1,s},p.input,{partial:true}));}
      }
    }
    if(event.type==='response.text.done'||event.type==='response.audio_transcript.done')p.text=event.text||event.transcript||p.text;
    if(event.type==='response.done'){
      this.pending=null;p.signal?.removeEventListener('abort',p.abort);
      this.onTrace({type:'native_result',start:p.input.start,end:p.input.end,firstTokenMs:p.firstTokenMs,firstRowMs:p.firstRowMs,totalMs:Math.round(performance.now()-p.began),output:p.text});
      try{
        if(event.response?.status==='failed')throw new Error('原生状态生成失败');
        p.resolve({...this.decode(parseSocial(p.text),p.input),nativeInput:{frames:p.input.frames.length,streaming:true,model:REALTIME_MODEL}});
      }catch(error){p.reject(error);}
    }
  }
  maybeRespond(){const p=this.pending;if(p?.committed&&p.configured&&!p.responded){p.responded=true;this.send({type:'response.create'});}}
  pushAudio(pcm,_start,end){
    if(this.closed||!this.initialized)return;
    if(this.socket.bufferedAmount>262144){this.fail(new Error('原生状态声音传输积压'));return;}
    this.audioEnd=end;if(!this.rolling)this.send({type:'input_audio_buffer.append',audio:pcm.toString('base64')});
  }
  pushFrame(frame,t){
    if(this.closed||!this.initialized||!this.audioEnd||t-this.lastFrame<.95)return;
    this.lastFrame=t;this.frames.push({image:frame.image,t});this.frames=this.frames.filter(f=>f.t>t-45);
    if(!this.rolling)this.send({type:'input_image_buffer.append',image:frame.image});
  }
  async analyze(input,_config,signal,{onPartial=()=>{}}={}){
    await this.ready;
    if(this.closed)throw new Error('原生状态连接已关闭');
    if(this.pending)throw new Error('原生状态请求尚未完成');
    if(input.end-this.committedEnd<.3)throw new Error('原生状态缺少新声音');
    if(signal?.aborted)throw signal.reason;
    // Commit before waiting for acknowledgement: later appended media remain
    // uncommitted and cannot leak into this response's evidence window.
    return new Promise((resolve,reject)=>{
      const frames=this.frames.filter(f=>f.t>=input.start&&f.t<=input.end).map(f=>({...f,t:f.t-input.start}));
      const abort=()=>{this.fail(new Error('原生状态判断超时'));};
      this.pending={input:{...input,frames},resolve,reject,signal,abort,onPartial,began:performance.now(),text:'',lastRows:'',firstTokenMs:null,firstRowMs:null};
      signal?.addEventListener('abort',abort,{once:true});
      if(this.rolling){
        const wav=Buffer.from(input.audio.data,'base64');
        if(wav.toString('ascii',0,4)!=='RIFF'||wav.toString('ascii',36,40)!=='data'){this.fail(new Error('原生窗口声音格式无效'));return;}
        const pcm=wav.subarray(44);let index=0;
        for(let from=0;from<pcm.length;from+=3200){
          const to=Math.min(from+3200,pcm.length);this.send({type:'input_audio_buffer.append',audio:pcm.subarray(from,to).toString('base64')});
          while(index<frames.length&&frames[index].t<=to/32000)this.send({type:'input_image_buffer.append',image:frames[index++].image});
        }
      }
      this.send({type:'input_audio_buffer.commit'});this.committedEnd=input.end;
      const timing=this.rolling?`\nAnalyze ONLY the newest user audio/video message, a ${input.duration.toFixed(2)} second clip. All output times are relative to this clip, from 0 to ${input.duration.toFixed(2)}. This rolling clip overlaps previous ones: do not accumulate their durations or copy their predictions. Detect all supported states and brief changes within this newest clip.`:`\nThe audio now ends at session time ${input.end.toFixed(2)} seconds. Judge only the last ${input.duration.toFixed(2)} seconds, using preceding context only for interpretation. Output timestamps relative to that recent window: 0 to ${input.duration.toFixed(2)}. Detect brief changes inside it; do not merely repeat an earlier label. Prior assistant outputs are fallible estimates, not evidence.`;
      const currentTiming=`\nAudio now ends at session time ${input.end.toFixed(2)} seconds. Judge CURRENT signals at that endpoint, using only the last ${input.duration.toFixed(2)} seconds and prior context for interpretation. Return only p, s and m; no timestamps. Earlier judgments are not evidence and may be wrong.`;
      this.send({type:'session.update',session:{instructions:this.prompt+(this.timingMode==='current'?currentTiming:timing)}});
    });
  }
  fail(error){
    this.rejectReady(error);
    const p=this.pending;this.pending=null;if(p){p.signal?.removeEventListener('abort',p.abort);p.reject(error);}
    this.close();
  }
  close(){
    if(this.closed)return;this.closed=true;clearTimeout(this.connectTimer);
    this.rejectReady(new Error('原生状态连接已关闭'));
    const p=this.pending;this.pending=null;if(p){p.signal?.removeEventListener('abort',p.abort);p.reject(new Error('原生状态连接已关闭'));}
    if(this.socket.readyState===WebSocket.OPEN)this.socket.close();else if(this.socket.readyState===WebSocket.CONNECTING)this.socket.terminate();
  }
}
