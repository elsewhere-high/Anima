// Isolated research server; keeps the user's production session and key intact.
import {createApp} from '../server.mjs';
import {stat,appendFile} from 'node:fs/promises';
import {NativeSocialSession} from '../native-social.mjs';
import {REALTIME_MODEL} from '../qwen.mjs';
import {NATIVE_DELIVERY_PROMPT} from '../social.mjs';
import {DELIVERY_CLASSIFIER_PROMPT,normalizeDeliveryClasses,SOCIAL_CLASSIFIER_PROMPT,normalizeSocialClasses,SOCIAL_CLASS_ORDER} from '../delivery-classifier.mjs';
import {analyzeSpecialistSocial,SPECIALIST_FUSION_MODEL} from '../specialist-social.mjs';
import {runSaver} from './save-run.mjs';
import {fileURLToPath} from 'node:url';
const port=Number(process.env.PORT)||4830;
const specialistFusion=process.env.ANIMA_LOCAL_ASR==='1'||process.env.ANIMA_VISUAL_FUSION==='1';
const trace=new URL('./candidate-trace.jsonl',import.meta.url);
// Research-only port: reload only when the candidate file changes, between test runs.
async function analyze(input,config,signal,options){
  const path=new URL('../social.mjs',import.meta.url),stamp=(await stat(path)).mtimeMs;
  const {analyzeSocial,analyzeSocialHeads}=await import(path.href+'?version='+stamp);
  const run=specialistFusion?analyzeSpecialistSocial:process.env.ANIMA_HEADS==='1'?analyzeSocialHeads:analyzeSocial;
  try{return await run(input,config,signal,{...options,onTrace:value=>appendFile(trace,JSON.stringify({at:new Date().toISOString(),...value})+'\n').catch(()=>{})});}
  catch(error){await appendFile(trace,JSON.stringify({at:new Date().toISOString(),start:input.start,end:input.end,error:error.message})+'\n');throw error;}
}
const native=['1','rolling'].includes(process.env.ANIMA_NATIVE);
const realtimeOptions=native?{scheduler:{hop:.5,concurrency:1,firstEnd:.5},model:REALTIME_MODEL,
  analyzerFactory:config=>new NativeSocialSession(config,{rolling:process.env.ANIMA_NATIVE==='rolling',onTrace:value=>appendFile(trace,JSON.stringify({at:new Date().toISOString(),...value})+'\n').catch(()=>{})})
}:{scheduler:{hop:.5,concurrency:3,firstEnd:.5},speechFast:process.env.ANIMA_SPEECH_FAST==='1'};
if(specialistFusion){realtimeOptions.specialistFusion=true;realtimeOptions.localAsr=process.env.ANIMA_LOCAL_ASR==='1';realtimeOptions.model=SPECIALIST_FUSION_MODEL;realtimeOptions.scheduler={hop:Number(process.env.ANIMA_REVIEW_HOP)||.8,concurrency:2,firstEnd:.5};realtimeOptions.maxSessionSeconds=660;}
if(process.env.ANIMA_LOCAL_FAST==='1'){
  realtimeOptions.fastModel=SPECIALIST_FUSION_MODEL;realtimeOptions.fastSource='visual_local_classifier';realtimeOptions.fastCodes=SOCIAL_CLASS_ORDER;
  const frameLimit=Number(process.env.ANIMA_FAST_FRAMES)||0;
  realtimeOptions.fastAnalyzerFactory=()=>({ready:Promise.resolve(),pushAudio(){},pushFrame(){},close(){},
    analyze:(input,config,signal,options)=>analyzeSpecialistSocial(frameLimit?{...input,frames:input.frames.slice(-frameLimit)}:input,config,signal,{...options,compact:process.env.ANIMA_LOCAL_SPARSE==='1'?'sparse':true,onTrace:value=>appendFile(trace,JSON.stringify({at:new Date().toISOString(),lane:'visual_local_classifier',frameLimit:frameLimit||null,...value})+'\n').catch(()=>{})})});
}
if(process.env.ANIMA_NATIVE_DELIVERY==='1'){
  realtimeOptions.fastModel=REALTIME_MODEL;
  const compact=process.env.ANIMA_NATIVE_COMPACT==='1';
  const all=process.env.ANIMA_NATIVE_ALL==='1';
  if(all)realtimeOptions.fastCodes=SOCIAL_CLASS_ORDER;
  realtimeOptions.fastAnalyzerFactory=config=>new NativeSocialSession(config,{prompt:all?SOCIAL_CLASSIFIER_PROMPT:compact?DELIVERY_CLASSIFIER_PROMPT:NATIVE_DELIVERY_PROMPT,...(compact||all?{decode:all?normalizeSocialClasses:normalizeDeliveryClasses,streamRows:false,timingMode:'current'}:{}),onTrace:value=>appendFile(trace,JSON.stringify({at:new Date().toISOString(),lane:'native_delivery',compact,all,...value})+'\n').catch(()=>{})});
}
createApp({fusionAnalyzer:analyze,realtimeOptions,onResearchRun:runSaver(fileURLToPath(new URL('./autosaved/',import.meta.url)))}).listen(port,'127.0.0.1',()=>console.log(`Anima candidate ready on ${port}; native=${native}`));
