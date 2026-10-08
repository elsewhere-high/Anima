import WebSocket,{WebSocketServer} from 'ws';
import {randomUUID} from 'node:crypto';
import {endpoints,qwenError,realtimeErrorCode,REVIEW_MODEL} from './qwen.mjs';
import {EvidenceBuffer} from './evidence.mjs';
import {analyzeFusion} from './fusion.mjs';
import {StateEngine} from './state-engine.mjs';
import {WindowScheduler} from './window-scheduler.mjs';
import {SpecialistTracker,specialistEvidence} from './specialists.mjs';
import {judgmentModel} from './fusion-provider.mjs';
import {speechDelivery} from './speech-delivery.mjs';
import {LocalTranscriber} from './local-transcriber.mjs';
import {perceptionModel} from './model-policy.mjs';
const json=(socket,value)=>{if(socket.readyState===WebSocket.OPEN&&socket.bufferedAmount<1048576)socket.send(JSON.stringify(value));};
const bounded=(n,min,max)=>Math.max(min,Math.min(max,Number(n)||0));

export function attachRealtime(server,{getConfig,token,specialists,realtimeOptions={},onActive=()=>{},onVerified=()=>{},onError=()=>{},upstreamFactory=(url,options)=>new WebSocket(url,options),fusionAnalyzer=analyzeFusion}={}){
  const sockets=new WebSocketServer({noServer:true,maxPayload:270000,handleProtocols:p=>p.has('anima')?'anima':false}),subscribers=new Set();let live=0;
  const publish=value=>{for(const s of subscribers)json(s,value);};
  server.on('upgrade',(req,socket,head)=>{
    const host=req.headers.host||'',protocols=String(req.headers['sec-websocket-protocol']||'').split(',').map(x=>x.trim()),config=getConfig();
    const reject=code=>socket.end(`HTTP/1.1 ${code}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
    if(!['/api/realtime','/api/events'].includes(req.url)||!/^(127\.0\.0\.1|localhost|\[::1\]):\d+$/.test(host)||req.headers.origin!==`http://${host}`||!protocols.includes('anima')||!protocols.includes(token)){reject('403 Forbidden');return;}
    if(req.url==='/api/events'){
      if(subscribers.size>=8){reject('429 Too Many Requests');return;}
      sockets.handleUpgrade(req,socket,head,s=>{subscribers.add(s);s.on('error',()=>{});s.on('close',()=>subscribers.delete(s));json(s,{type:'subscribed',protocol:'anima.perceive.v2'});});return;
    }
    if(!config.key||!config.workspace){reject('503 Service Unavailable');return;}if(live){reject('409 Conflict');return;}
    sockets.handleUpgrade(req,socket,head,client=>{
      live++;onActive(1);
      const specialistFusion=realtimeOptions.localAsr||realtimeOptions.specialistFusion;
      const analysisModel=specialistFusion?perceptionModel(config):realtimeOptions.model||judgmentModel(config);
      const sessionId=randomUUID(),evidence=new EvidenceBuffer({windowSeconds:3}),states=new StateEngine(sessionId),scheduler=new WindowScheduler(realtimeOptions.scheduler),tracker=new SpecialistTracker(),timers=[],asrItems=new Map();
      const liveAnalyzer=realtimeOptions.analyzerFactory?.(config);
      let fastAnalyzer=realtimeOptions.fastAnalyzerFactory?.(config),fastFormatFailures=0,fastRetryAt=0;
      const fastScheduler=new WindowScheduler({hop:.5,concurrency:1,firstEnd:.5});
      const acceptTranscript=value=>{if(closed)return;evidence.transcript(value);emit(value);};
      const localTranscriber=realtimeOptions.localAsr?new LocalTranscriber({snapshot:o=>evidence.snapshot(o),infer:i=>specialists.infer('asr',{audio:i.audio.data}),onTranscript:acceptTranscript,onError:()=>emit({type:'notice',code:'LOCAL_ASR_UNAVAILABLE',message:'本地转写暂不可用，其他分析继续'})}):null;
      let upstream,ready=false,closed=false,configured=false,started=false,samples=0,offset=0,buffered=0,lastCommitEnd=0,pendingCommit=null,finishing=false,drainingTranscription=false;
      let failures=0,fusionUnavailable=false,lastFaceState='',lastFrame=0,wallStart=null,lastVoice=0,lastSpeech=0,expertSequence=0;
      const maxMediaSeconds=Math.max(1,Math.min(900,Number(realtimeOptions.maxSessionSeconds)||125));
      const time=()=>offset+samples/16000;
      const now=()=>wallStart===null?time():Math.max(time(),offset+(performance.now()-wallStart)/1000);
      const emit=value=>{const event={protocol:'anima.perceive.v2',sessionId,...value};json(client,event);if(['state','quality','transcript','session.start','session.end','result','notice'].includes(event.type))publish(event);};
      const personState=()=>{const f=evidence.faces.at(-1);return !f||now()-f.t>=1.5?'unavailable':f.faces>1?'multiple':f.faces===1?'single':'absent';};
      const updatePersonQuality=()=>{const state=personState();if(state===lastFaceState)return;lastFaceState=state;emit({type:'quality',at:time(),quality:{face:state}});if(state!=='single')emit(states.clear(now(),state==='multiple'?'多人画面，暂停个人判断':'当前人物不可见'));};
      const cleanup=(reason='finished')=>{
        if(closed)return;closed=true;timers.forEach(clearTimeout);scheduler.close();fastScheduler.close();liveAnalyzer?.close();fastAnalyzer?.close();localTranscriber?.close();
        emit(states.clear(now(),reason==='finished'?'观察结束':'连接中断'));emit({type:'session.end',reason,at:now()});
        evidence.clear();asrItems.clear();live--;onActive(-1);
        if(upstream?.readyState===WebSocket.OPEN){upstream.close();setTimeout(()=>upstream.terminate(),500).unref();}else if(upstream?.readyState===WebSocket.CONNECTING)upstream.terminate();
        if(client.readyState===WebSocket.OPEN)client.close();
      };
      const fail=message=>{if(closed)return;onError(message);emit({type:'error',error:message});cleanup('error');};
      const expert=async(kind,payload,start,end)=>{
        if(!specialists?.available(kind)||closed||finishing)return;
        const id='s-'+(++expertSequence);
        try{
          const result=await specialists.infer(kind,payload);
          if(closed)return;
          if(kind==='face'&&result.faces>1){emit(states.clear(now(),'多人画面，暂停个人判断'));return;}
          const observation=specialistEvidence(result,kind,{start,end,id});
          if(Object.keys(result.scores||{}).length||result.speechSpans)evidence.pushSpecialist(observation);
          emit({type:'measurement',at:now(),start,end,kind,...result,evidence:observation});
          // These are acoustic observations only. Current-state decisions still
          // come from the multimodal detector, not a medical speech label.
          if(kind==='speech'){
            if(realtimeOptions.speechFast){
              const quality=evidence.snapshot().quality;
              emit(states.update(speechDelivery(result,observation,quality,evidence.activity),{start,end,now:now(),windowId:id,latencyMs:result.latencyMs,lane:'speech',ttl:1.5}));
            }
            return;
          }
          if(personState()!=='single')return;
          const value=tracker.update(result,kind,observation);
          emit(states.update(value,{start,end,now:now(),windowId:id,latencyMs:result.latencyMs,lane:kind,ttl:kind==='face'?1.5:3}));
        }catch(error){if(!closed)emit({type:'notice',code:'SPECIALIST_UNAVAILABLE',kind,reason:/^[a-zA-Z_]{1,64}$/.test(error.message)?error.message:'inference_error',at:now(),message:kind==='face'?'面部分析暂不可用':'声音分析暂不可用'});}
      };
      const commit=(force=false)=>{
        if(localTranscriber){localTranscriber.tick(time());return;}
        if(!ready||closed||pendingCommit||buffered<(force?4800:32000))return;
        pendingCommit={start:lastCommitEnd||offset,end:time(),sent:performance.now()};lastCommitEnd=time();buffered=0;
        json(upstream,{type:'input_audio_buffer.commit'});
      };
      const analyzeFast=async()=>{
        if(!fastAnalyzer||closed||finishing||!ready||samples<6400||performance.now()<fastRetryAt)return;
        const input=evidence.snapshot(),request=fastScheduler.reserve(input.end);
        if(!request)return;
        const {id,controller}=request,began=performance.now(),windowId=`delivery-${id}`;
        const timeout=setTimeout(()=>controller.abort(),6000);
        const output=(value,partial)=>{
          if(closed||controller.signal.aborted)return;
          const latencyMs=Math.round(performance.now()-began);
          // This quick pass is provisional even when its JSON is complete.
          // It never substitutes for the separate, slower evidence check.
          const result={...value,partial,signals:value.signals.filter(s=>(realtimeOptions.fastCodes||['confidence','hesitation']).includes(s.code)).map(s=>({...s,source:realtimeOptions.fastSource||'native_delivery',tentative:true}))};
          const current=personState()==='single'?result:{...result,signals:[]};
          const state=states.update(current,{start:input.start,end:input.end,now:now(),windowId,latencyMs,lane:'native_delivery',ttl:2});
          emit(state);
          if(!partial)emit({type:'fast.result',...result,windowId,start:input.start,end:input.end,receivedAt:now(),model:specialistFusion?perceptionModel(config,'fast'):realtimeOptions.fastModel,latencyMs,stale:state.historical});
        };
        try{const result=await fastAnalyzer.analyze(input,config,controller.signal,{onPartial:v=>output(v,true)});fastFormatFailures=0;fastRetryAt=0;output(result,false);}
        catch(error){if(!closed){
          // A malformed stateless response is discarded, not repaired into an
          // invented judgment. The next request uses fresh media, never a backlog.
          fastFormatFailures++;
          const stateless=realtimeOptions.fastSource==='visual_local_classifier';
          const recover=error.retryable!==false&&(stateless||error.code==='INVALID_SOCIAL_OUTPUT'&&fastFormatFailures<3);
          if(recover&&stateless)fastRetryAt=performance.now()+Math.min(4000,250*2**Math.min(fastFormatFailures-1,4));
          const requestCode=typeof error.code==='string'&&/^[a-zA-Z0-9_.-]{1,80}$/.test(error.code)?error.code:undefined;
          emit({type:'notice',code:recover?'FAST_DELIVERY_WINDOW_DROPPED':'FAST_DELIVERY_UNAVAILABLE',requestCode,status:error.status,reason:controller.signal.aborted?'timeout':error.code==='INVALID_SOCIAL_OUTPUT'?'format':'request_failed',message:recover?'本次快速判断未能读取，下一段继续分析':/insufficient_quota|AllocationQuota/.test(requestCode||'')?'快速模型额度不足，其余分析继续':'快速表达分析暂不可用，其余分析继续'});
          if(!recover){fastAnalyzer?.close();fastAnalyzer=null;}
        }}
        finally{clearTimeout(timeout);fastScheduler.complete(id);}
      };
      const analyze=async(force=false)=>{
        if(closed||!ready||fusionUnavailable||samples<6400)return;
        const input=evidence.snapshot();if(input.duration<.4)return;
        const request=scheduler.reserve(input.end,{force});if(!request)return;
        const {id:windowId,controller}=request,began=performance.now();emit({type:'analyzing',windowId,start:input.start,end:input.end});
        const timeout=setTimeout(()=>controller.abort(),12000);
        const output=(result,partial)=>{
          if(closed||controller.signal.aborted)return;
          const currentResult=personState()==='single'?result:{...result,signals:[],speakerBound:false,unknown:'当前无法确认画面中的人'};
          // A delayed review remains in the record. It must not revive a state
          // several seconds after its evidence was current on screen.
          const latencyMs=Math.round(performance.now()-began),state=states.update(currentResult,{start:input.start,end:input.end,now:now(),windowId,latencyMs,ttl:2});
          emit(state);
          if(!partial)emit({type:'result',...result,windowId,start:input.start,end:input.end,receivedAt:now(),source:'fusion',model:analysisModel,latencyMs,stale:state.historical,inputSummary:{windowSeconds:input.duration,contextSeconds:45,frames:result.nativeInput?.frames??input.frames.length,faceSamples:input.face.length,measurements:input.local.length,specialists:input.local.filter(o=>o.source==='specialist').map(o=>o.model)},localEvidence:input.local});
        };
        try{
          const result=await (liveAnalyzer?liveAnalyzer.analyze.bind(liveAnalyzer):fusionAnalyzer)(input,config,controller.signal,{onPartial:r=>output(r,true)});
          failures=0;onVerified();output(result,false);
        }catch(error){
          if(!closed){
            if(error.retryable===false){
              if(!fusionUnavailable){fusionUnavailable=true;onError(error.message);emit({type:'notice',code:'MODEL_ACCESS_UNAVAILABLE',message:error.message+' 本地观察继续。'});}
            }else{failures++;emit({type:'notice',message:controller.signal.aborted?'状态判断超时，字幕和本地分析继续':'状态判断暂不可用，字幕和本地分析继续',code:'ANALYSIS_UNAVAILABLE'});if(failures>=3)onError('状态分析连续失败，请检查模型权限或网络。');}
          }
        }finally{
          clearTimeout(timeout);scheduler.complete(windowId);
          if(finishing&&!closed&&!drainingTranscription){if(!fusionUnavailable&&time()-scheduler.lastEnd>=.3)analyze(true);else if(!scheduler.running.size)timers.push(setTimeout(()=>cleanup(),700));}
        }
      };
      if(!localTranscriber){try{const url=new URL(endpoints(config.workspace,config.region).realtime);url.searchParams.set('model',config.model);upstream=upstreamFactory(url.href,{headers:{Authorization:`Bearer ${config.key}`},handshakeTimeout:15000,maxPayload:262144,followRedirects:false});}catch{fail('实时连接地址无效。');return;}}
      timers.push(setTimeout(()=>{if(!ready)fail(localTranscriber?'本地语音模型准备超时。':'千问实时连接超时。');},25000));
      timers.push(setInterval(()=>{if(closed||!ready)return;if(pendingCommit&&performance.now()-pendingCommit.sent>10000){fail('实时转写响应超时。');return;}if(!finishing){
        updatePersonQuality();commit();analyze();analyzeFast();
        if(time()-lastVoice>=1&&samples>=16000&&specialists?.available('voice')){
          const input=evidence.snapshot({windowSeconds:3});lastVoice=time();
          if(!input.quality.quiet&&input.quality.speech!==false)expert('voice',{audio:input.audio.data},input.start,input.end);
        }
        if(time()-lastSpeech>=.5&&samples>=16000&&specialists?.available('speech')){
          const input=evidence.snapshot({windowSeconds:3});lastSpeech=time();
          if(!input.quality.quiet)expert('speech',{audio:input.audio.data},input.start,input.end);
        }
      }const state=states.tick(now());if(state)emit(state);},200));
      timers.push(setTimeout(()=>cleanup('time_limit'),(maxMediaSeconds+10)*1000));
      if(localTranscriber){
        const prepare=()=>{
          if(closed||ready)return;
          if(!specialists?.available('asr')){timers.push(setTimeout(prepare,100));return;}
          ready=true;emit({type:'ready',model:'SenseVoiceSmall',analysisModel,specialists:specialists.status()});emit({type:'session.start',at:0,windowSeconds:3,contextSeconds:45,transcription:'local'});
        };prepare();
      }
      upstream?.on('unexpected-response',(_req,res)=>{res.resume();fail(qwenError(res.statusCode));});upstream?.on('error',()=>fail('无法连接千问实时转写服务。'));upstream?.on('close',()=>{if(!closed)fail('实时转写连接已断开。');});
      upstream?.on('message',data=>{
        if(closed)return;let event;try{event=JSON.parse(data);}catch{fail('实时服务返回格式错误。');return;}
        const failure=realtimeErrorCode(event);if(failure){fail(qwenError(0,failure));return;}
        if(event.type==='session.created'&&!configured){configured=true;json(upstream,{type:'session.update',session:{modalities:['text'],instructions:'只转写当前声音，不生成回应。',turn_detection:null,input_audio_transcription:{model:'qwen3-asr-flash-realtime'},audio:{input:{format:{type:'pcm',sample_rate:16000,sample_format:'s16le',channels:1,packing:'interleaved',channel_layout:'mono'}}}}});return;}
        if(event.type==='session.updated'&&!ready){
          const complete=()=>{if(closed||ready)return;ready=true;emit({type:'ready',model:config.model,analysisModel,specialists:specialists?.status()});emit({type:'session.start',at:0,windowSeconds:3,contextSeconds:45});};
          const prerequisites=[];
          if(liveAnalyzer)prerequisites.push(liveAnalyzer.ready);
          if(fastAnalyzer)prerequisites.push(fastAnalyzer.ready.catch(()=>{fastAnalyzer?.close();fastAnalyzer=null;emit({type:'notice',code:'FAST_DELIVERY_UNAVAILABLE',message:'快速表达分析暂不可用，其余分析继续'});}));
          if(prerequisites.length)Promise.all(prerequisites).then(complete,()=>fail('原生状态服务连接失败'));else complete();return;
        }
        if(event.type==='input_audio_buffer.committed'){
          if(pendingCommit){asrItems.set(event.item_id||`chunk-${lastCommitEnd}`,pendingCommit);pendingCommit=null;}
          if(finishing&&buffered>=4800)commit(true);return;
        }
        if(event.type==='conversation.item.input_audio_transcription.delta'||event.type==='conversation.item.input_audio_transcription.completed'){
          const provisional=event.type.endsWith('.delta'),id=event.item_id||`draft-${lastCommitEnd}`;
          const matched=asrItems.get(id);
          const span=matched||{start:lastCommitEnd||offset,end:time()};
          const text=String(provisional?(event.text||'')+(event.stash||event.delta||''):(event.transcript||event.text||'')).slice(0,500);
          if(text){const value={type:'transcript',id,text,start:span.start,end:span.end,provisional,source:config.model,timing:matched?'committed-audio':'receipt-estimate',confirmedText:provisional?String(event.text||''):text};evidence.transcript(value);emit(value);}
          for(const [id,v]of asrItems)if(v.end<time()-45)asrItems.delete(id);
        }
      });
      client.on('error',()=>cleanup('client_error'));client.on('close',()=>cleanup('client_closed'));
      client.on('message',(data,binary)=>{
        if(closed||!ready||finishing)return;
        if(binary){
          if(!data.length||data.length%2||data.length>16000){fail('实时声音格式不正确。');return;}
          if(upstream?.bufferedAmount>262144){fail('实时声音网络积压。');return;}
          if(wallStart===null)wallStart=performance.now();const start=time();samples+=data.length/2;buffered+=data.length/2;if(samples>16000*maxMediaSeconds){cleanup('time_limit');return;}
          evidence.pushAudio(data,start,time());liveAnalyzer?.pushAudio(data,start,time());fastAnalyzer?.pushAudio(data,start,time());if(upstream)json(upstream,{type:'input_audio_buffer.append',audio:data.toString('base64')});return;
        }
        let event;try{event=JSON.parse(data);}catch{fail('实时输入格式不正确。');return;}
        if(event.type==='start'&&!started){started=true;offset=bounded(event.offset,0,30);lastCommitEnd=offset;return;}
        if(event.type==='image'){
          if(typeof event.image!=='string'||event.image.length>262144||!/^[A-Za-z0-9+/]+={0,2}$/.test(event.image)||event.image.length%4){fail('画面格式不正确。');return;}
          if(time()-lastFrame<.4&&lastFrame)return;lastFrame=time();evidence.pushFrame(event.image,time(),{brightness:Number.isFinite(event.brightness)?bounded(event.brightness,0,1):null});liveAnalyzer?.pushFrame(event,time());fastAnalyzer?.pushFrame(event,time());expert('face',{image:event.image},Math.max(offset,time()-.5),time());return;
        }
        if(event.type==='face'){
          const faces=bounded(event.faces,0,2),cues=(Array.isArray(event.cues)?event.cues:[]).slice(0,8).filter(c=>typeof c.name==='string').map(c=>({name:c.name.slice(0,24),coefficient:bounded(c.coefficient,0,1)}));
          evidence.pushFace({faces,cues},time());updatePersonQuality();return;
        }
        if(event.type==='activity'){evidence.activity.push({t:time(),speaking:!!event.speaking});evidence.activity=evidence.activity.slice(-100);localTranscriber?.activity(!!event.speaking,time());return;}
        if(event.type==='commit'){commit(true);analyze();return;}
        if(event.type==='finish'){
          finishing=true;if(samples<6400){cleanup();return;}drainingTranscription=!!localTranscriber;commit(true);
          const flushed=()=>{drainingTranscription=false;if(closed)return;if(!fusionUnavailable&&time()-scheduler.lastEnd>=.3)analyze(true);else if(!scheduler.running.size)timers.push(setTimeout(()=>cleanup(),700));};
          if(localTranscriber)localTranscriber.finish(time()).then(flushed,flushed);else if(!scheduler.running.size)flushed();
          timers.push(setTimeout(()=>cleanup('finish_timeout'),16000));
        }
      });
    });
  });
  server.on('close',()=>{for(const s of sockets.clients)s.terminate();sockets.close();});return sockets;
}
