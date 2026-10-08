import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join, extname, resolve, sep } from 'node:path';
import { randomBytes } from 'node:crypto';
import { validateInput, SIGNALS } from './perceive.mjs';
import {analyzeQwen,transcribeQwen,endpoints,REALTIME_MODEL,REVIEW_MODEL,DEFAULT_ENDPOINT} from './qwen.mjs';
import {DISPLAY_SIGNALS} from './public/signal-catalog.js';
import {attachRealtime} from './realtime.mjs';
import {analyzeFusion} from './fusion.mjs';
import {reviewEvidence} from './evidence.mjs';
import {Specialists,specialistEvidence} from './specialists.mjs';
import {externalFusion,judgmentModel} from './fusion-provider.mjs';
import {perceptionModel,PERCEPTION_MODELS,modelUsage} from './model-policy.mjs';

const root=fileURLToPath(new URL('./public/',import.meta.url));
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.json':'application/json','.mp4':'video/mp4','.jpg':'image/jpeg','.png':'image/png','.wav':'audio/wav','.wasm':'application/wasm','.onnx':'application/octet-stream','.task':'application/octet-stream'};
export function createApp({config={key:process.env.DASHSCOPE_API_KEY||'',workspace:process.env.DASHSCOPE_WORKSPACE_ID||process.env.DASHSCOPE_BASE_URL||DEFAULT_ENDPOINT,region:process.env.DASHSCOPE_REGION||'cn-beijing',model:REALTIME_MODEL},fetcher,upstreamFactory,fusionAnalyzer,realtimeOptions={},onResearchRun,specialists=new Specialists({enabled:!process.env.NODE_TEST_CONTEXT})}={}) {
  config={region:'cn-beijing',workspace:DEFAULT_ENDPOINT,model:REALTIME_MODEL,fusion:externalFusion(),...config};
  const specialistFusion=realtimeOptions.localAsr||realtimeOptions.specialistFusion;
  const analysisModel=()=>specialistFusion?perceptionModel(config):realtimeOptions.model||judgmentModel(config);
  const fastModel=()=>specialistFusion?perceptionModel(config,'fast'):realtimeOptions.fastModel;
  const token=randomBytes(24).toString('hex');let active=0,apiVerified=false,connectionError=null;
  specialists.start?.();
  const send=(res,status,value)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(value));};
  const server=http.createServer(async(req,res)=>{
    const host=req.headers.host||'';
    if(!/^(127\.0\.0\.1|localhost|\[::1\]):\d+$/.test(host)){send(res,403,{error:'仅限本机访问'});return;}
    let path;try{path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{send(res,400,{error:'地址格式不正确'});return;}
    if(path.startsWith('/api/')) {
      if(req.method==='GET'&&path==='/api/status'){send(res,200,{configured:!!config.key&&!!config.workspace,apiVerified,connectionError,model:realtimeOptions.localAsr?'SenseVoiceSmall':config.model,reviewModel:analysisModel(),fastModel:fastModel(),modelChoices:specialistFusion?PERCEPTION_MODELS:[],usage:modelUsage(),workspace:config.workspace,region:config.region,provider:realtimeOptions.localAsr?'本地声音＋千问视觉':'阿里云千问',realtime:true,protocol:"anima.perceive.v2",build:'perceive-stream-2',specialists:specialists.status(),localRuntime:specialists.runtime,capabilities:{stateWindowSeconds:3,contextSeconds:45,faceMotion:true,audioFeatures:true,stateEvents:true,evidence:true,frameIntervalMs:500,concurrentWindows:realtimeOptions.scheduler?.concurrency||2,maxObservationSeconds:Math.min(600,Math.max(1,(realtimeOptions.maxSessionSeconds||125)-5)),localTranscription:!!realtimeOptions.localAsr},token,signals:specialistFusion?DISPLAY_SIGNALS:SIGNALS});return;}
      if(req.method!=='POST'){send(res,405,{error:'请求方法不正确'});return;}
      if(req.headers.origin!==`http://${host}`||req.headers['x-anima-token']!==token){send(res,403,{error:'请求来源不正确'});return;}
      if(!String(req.headers['content-type']||'').startsWith('application/json')){send(res,415,{error:'请使用 JSON 请求'});return;}
      let body;try{
        const chunks=[];let size=0;
        for await(const chunk of req){size+=chunk.length;if(size>5*1024*1024)throw new Error('输入过大');chunks.push(chunk);}
        body=JSON.parse(Buffer.concat(chunks).toString());
      }catch{send(res,400,{error:'输入格式错误或超过 5 MB'});return;}
      if(path==='/api/research/run'&&onResearchRun){
        try{await onResearchRun(body);send(res,200,{saved:true});}
        catch{send(res,400,{error:'研究记录未保存，请检查格式和本地存储'});}
        return;
      }
      if(path==='/api/config'){
        if(active){send(res,409,{error:'请先停止实验，再调整模型'});return;}
        const key=body.key===''||body.key===undefined?config.key:body.key;
        if(typeof key!=='string'||key.length>300||!key.trim()||/[^\x21-\x7e]/.test(key.trim())){send(res,400,{error:'请填写有效的百炼 API Key'});return;}
        const workspace=body.workspace||config.workspace||DEFAULT_ENDPOINT;
        const proposed={...config,...(body.perceptionModel?{perceptionModel:body.perceptionModel}:{}),...(Object.hasOwn(body,'fastPerceptionModel')?{fastPerceptionModel:body.fastPerceptionModel}:{})};
        let selected;try{selected=perceptionModel(proposed);perceptionModel(proposed,'fast');}catch(e){send(res,400,{error:e.message});return;}
        try{endpoints(workspace,body.region||'cn-beijing');}catch(e){send(res,400,{error:e.message});return;}
        config={...proposed,key:key.trim(),perceptionModel:selected,workspace:workspace.trim(),region:body.region||'cn-beijing',model:REALTIME_MODEL};apiVerified=false;connectionError=null;send(res,200,{configured:true,apiVerified,connectionError,workspace:config.workspace,region:config.region,model:realtimeOptions.localAsr?'SenseVoiceSmall':config.model,reviewModel:analysisModel(),fastModel:fastModel(),provider:realtimeOptions.localAsr?'本地声音＋千问视觉':'阿里云千问'});return;
      }
      if(path==='/api/analyze'||path==='/api/evaluate'){
        const mode=path==='/api/evaluate'?body.mode||'full':'full';if(!['full','baseline','text','audio','video'].includes(mode)){send(res,400,{error:'未知对照模式'});return;}const source=path==='/api/evaluate'?body.input:body;
        let input;try{if(path==='/api/evaluate'&&typeof source?.transcript==='string'&&!source.audio&&!source.frames?.length){input={duration:Math.max(.1,Math.min(30,Number(source.duration)||5)),start:0,audio:null,frames:[],face:[],context:[],transcript:source.transcript.slice(0,500)};}else input=validateInput(source);}catch(e){send(res,400,{error:e.message});return;}
        if(!config.key||!config.workspace){send(res,503,{error:'请先填写千问 API Key。',code:'MODEL_NOT_CONFIGURED'});return;}
        if(active>=2){send(res,429,{error:'分析正在进行，请稍后'});return;}
        active++;
        const controller=new AbortController();
        const timeout=setTimeout(()=>controller.abort(),45000);
        res.on('close',()=>{if(!res.writableEnded)controller.abort();});
        try{
          const begin=performance.now();
          let prepared=reviewEvidence(input);if(mode==='text'){prepared.audio=null;prepared.frames=[];prepared.face=[];prepared.local=[];}if(mode==='audio'){prepared.frames=[];prepared.face=[];prepared.local=prepared.local.filter(x=>x.modality!=='画面');}if(mode==='video'){prepared.audio=null;prepared.transcript='';prepared.context=[];prepared.local=prepared.local.filter(x=>x.modality==='画面');}prepared.quality={...prepared.quality,audio:!!prepared.audio,video:!!prepared.frames.length};
          if(mode!=='baseline'&&mode!=='text'){
            const jobs=[];
            if(prepared.frames.length&&specialists.available('face'))jobs.push((async()=>{
              const counts=[];
              for(const [i,frame] of prepared.frames.entries()){
                if(controller.signal.aborted)break;
                const value=await specialists.infer('face',{image:frame.image});
                if(Number.isInteger(value.faces))counts.push(value.faces);
                if(value.faces===1&&Object.keys(value.scores||{}).length)prepared.local.push(specialistEvidence(value,'face',{start:Math.max(0,frame.t-.25),end:Math.min(prepared.duration,frame.t+.25),id:'sf-'+i}));
                if(value.faces>1)prepared.quality.face='multiple';
              }
              if(counts.length&&prepared.quality.face!=='multiple')prepared.quality.face=counts.at(-1)===1?'single':'absent';
            })());
            if(prepared.audio?.mimeType==='audio/wav'&&specialists.available('voice')){
              // Uploaded clips can exceed the specialist's eight-second bound.
              const wav=Buffer.from(prepared.audio.data,'base64');
              if(wav.length<=256044)jobs.push(specialists.infer('voice',{audio:prepared.audio.data}).then(value=>{if(Object.keys(value.scores||{}).length)prepared.local.push(specialistEvidence(value,'voice',{start:0,end:prepared.duration,id:'sv-1'}));}));
            }
            const attempts=await Promise.allSettled(jobs);
            prepared.specialistFailures=attempts.filter(x=>x.status==='rejected').length;
          }
          let transcriptionModel;
          if(specialistFusion&&mode!=='baseline'&&prepared.audio&&!prepared.transcript&&!prepared.quality.quiet){
            prepared.transcript=await transcribeQwen(prepared.audio,{...config},controller.signal,fetcher);
            transcriptionModel=REVIEW_MODEL;
          }
          const result=mode==='baseline'?await analyzeQwen(prepared,{...config},controller.signal,fetcher):await (fusionAnalyzer||analyzeFusion)(prepared,{...config},controller.signal,{fetcher});
          if(specialistFusion&&mode!=='baseline'){
            result.transcript=prepared.transcript;
            result.transcriptionModel=transcriptionModel;
            result.segments=prepared.transcript?[{start:0,end:prepared.duration,text:prepared.transcript}]:[];
          }
          apiVerified=true;connectionError=null;
          if(!res.destroyed)send(res,200,{...result,source:'model',model:mode==='baseline'?REVIEW_MODEL:analysisModel(),latencyMs:Math.round(performance.now()-begin),specialistEvidence:prepared.local.filter(x=>x.source==='specialist'),specialistFailures:prepared.specialistFailures||0});
        }catch(e){apiVerified=false;connectionError=e.name==='AbortError'||e.name==='TimeoutError'?'本次分析超时，请检查网络后重试。':e.message;if(!res.destroyed)send(res,502,{error:connectionError});}
        finally{active--;clearTimeout(timeout);}
        return;
      }
      send(res,404,{error:'接口不存在'});return;
    }
    if(!['GET','HEAD'].includes(req.method)){send(res,405,{error:'请求方法不正确'});return;}
    const target=resolve(root,path==='/'?'index.html':'.'+path);
    if(!target.startsWith(root.endsWith(sep)?root:root+sep)||path.includes('\0')){send(res,403,{error:'无效文件路径'});return;}
    let info;try{info=await stat(target);if(!info.isFile())throw 0;}catch{send(res,404,{error:'文件不存在'});return;}
    const headers={
      'Content-Type':types[extname(target)]||'application/octet-stream','Accept-Ranges':'bytes',
      'X-Content-Type-Options':'nosniff','Cache-Control':/\.(mp4|jpg|wasm|onnx|task)$/.test(target)?'public, max-age=86400':'no-cache',
      'Content-Security-Policy':"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'self'",
      'Permissions-Policy':'camera=(self), microphone=(self)', 'Referrer-Policy':'no-referrer'
    };
    let start=0,end=info.size-1,status=200;
    if(req.headers.range){
      const m=/^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
      if(!m||(!m[1]&&!m[2])){res.writeHead(416,{'Content-Range':`bytes */${info.size}`});res.end();return;}
      if(!m[1])start=Math.max(0,info.size-Number(m[2]));else {start=Number(m[1]);if(m[2])end=Math.min(end,Number(m[2]));}
      if(start>end||start>=info.size){res.writeHead(416,{'Content-Range':`bytes */${info.size}`});res.end();return;}
      status=206;headers['Content-Range']=`bytes ${start}-${end}/${info.size}`;
    }
    headers['Content-Length']=end-start+1;res.writeHead(status,headers);
    if(req.method==='HEAD'){res.end();return;}
    const stream=createReadStream(target,{start,end});stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);
  });
  attachRealtime(server,{getConfig:()=>({...config}),token,specialists,realtimeOptions,onActive:delta=>{active+=delta;},onVerified:()=>{apiVerified=true;connectionError=null;},onError:message=>{apiVerified=false;connectionError=message;},upstreamFactory,fusionAnalyzer});
  server.on('close',()=>specialists.close());
  return server;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const port=Number(process.env.PORT)||4827;
  createApp().listen(port,'127.0.0.1',()=>console.log(`Anima · http://127.0.0.1:${port}/`));
}
