import {endpoints,REVIEW_MODEL} from './qwen.mjs';
export function externalFusion(env=process.env){
  if(!env.ANIMA_FUSION_BASE_URL)return null;
  const url=new URL(env.ANIMA_FUSION_BASE_URL);
  const local=['localhost','127.0.0.1','[::1]'].includes(url.hostname);
  if(url.username||url.password||url.search||url.hash||(!local||url.protocol!=='http:')&&url.protocol!=='https:')throw new Error('模型地址须为本机 HTTP 或 HTTPS，不在地址中携带凭证。');
  return {provider:'minicpm-vllm',endpoint:url.href.replace(/\/$/,'')+'/chat/completions',model:env.ANIMA_FUSION_MODEL||'openbmb/MiniCPM-o-4_5',key:env.ANIMA_FUSION_API_KEY||''};
}
export const judgmentModel=config=>config.fusion?.model||REVIEW_MODEL;
export function fusionRequest(config,content,prompt){
  if(config.fusion){
    const native=content.map(item=>item.type==='input_audio'?{type:'audio_url',audio_url:{url:'data:audio/wav;base64,'+item.input_audio.data.split(',').at(-1)}}:item);
    return {url:config.fusion.endpoint,key:config.fusion.key,body:{model:config.fusion.model,stream:true,temperature:.1,max_tokens:2200,stop_token_ids:[151643,151645],messages:[{role:'system',content:prompt},{role:'user',content:native}]}};
  }
  return {url:endpoints(config.workspace,config.region).review,key:config.key,body:{model:REVIEW_MODEL,reasoning_effort:'none',stream:true,modalities:['text'],temperature:.1,max_tokens:2200,messages:[{role:'system',content:prompt},{role:'user',content}]}};
}
