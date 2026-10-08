import {analyzeSpecialistSocial,SPECIALIST_FUSION_MODEL} from './specialist-social.mjs';
import {SOCIAL_CLASS_ORDER} from './delivery-classifier.mjs';

// Shared by the launched application and integration QA. The local branch
// never forwards raw audio to the image/text model. Cloud transcription uses
// its separate audio socket only when localAsr is false.
export function localPerceptionRuntime({frameLimit=2,maxSessionSeconds=660,localAsr=true,reviewHop=.8}={}){
  return {fusionAnalyzer:analyzeSpecialistSocial,realtimeOptions:{
    localAsr,specialistFusion:true,model:SPECIALIST_FUSION_MODEL,speechFast:true,maxSessionSeconds,
    scheduler:{hop:reviewHop,concurrency:2,firstEnd:.5},
    fastModel:SPECIALIST_FUSION_MODEL,fastSource:'visual_local_classifier',fastCodes:SOCIAL_CLASS_ORDER,
    fastAnalyzerFactory:()=>({ready:Promise.resolve(),pushAudio(){},pushFrame(){},close(){},
      analyze:(input,config,signal,options)=>analyzeSpecialistSocial({...input,frames:input.frames.slice(-frameLimit)},config,signal,{...options,compact:'sparse'})})
  }};
}
