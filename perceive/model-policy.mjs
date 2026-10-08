// User's free-quota preference. Availability and remaining quota are account
// properties: inclusion here does not claim that a model is callable or free.
export const PERCEPTION_MODELS=['qwen3.7-flash','qwen3.7-flash-2026-07-15','qwen3.8-27b','qwen3.8-max','qwen3.8-max-0902','qwen3.8-flash'];
export const DEFAULT_PERCEPTION_MODEL='qwen3.7-flash';
export function perceptionModel(config={},lane='review'){
  const model=(lane==='fast'&&(config.fastPerceptionModel||process.env.ANIMA_FAST_MODEL))||config.perceptionModel||process.env.ANIMA_PERCEPTION_MODEL||DEFAULT_PERCEPTION_MODEL;
  if(!PERCEPTION_MODELS.includes(model))throw new Error('请选择支持图像理解的感知模型。');
  return model;
}
const totals=new Map();
export function recordModelUsage(model,usage){
  const row=totals.get(model)||{requests:0,reportedRequests:0,promptTokens:0,completionTokens:0,totalTokens:0};
  row.requests++;
  if(usage&&['prompt_tokens','completion_tokens','total_tokens'].every(k=>Number.isSafeInteger(usage[k])&&usage[k]>=0)){
    row.reportedRequests++;row.promptTokens+=usage.prompt_tokens;row.completionTokens+=usage.completion_tokens;row.totalTokens+=usage.total_tokens;
  }
  totals.set(model,row);
}
export function modelUsage(){return {scope:'current-server-process',remainingFreeTokens:null,models:Object.fromEntries([...totals].map(([k,v])=>[k,{...v}]))};}
