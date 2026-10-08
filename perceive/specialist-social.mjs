// Explicit research fallback: this model receives images, local ASR and
// acoustic measurements. It never receives or claims to hear the waveform.
import {fetch,Agent} from 'undici';
import {endpoints,completionText,qwenFailure} from './qwen.mjs';
import {SOCIAL_PROMPT,SOCIAL_SIGNALS,compactEvidence,normalizeSocial,parseSocial} from './social.mjs';
import {completedArray} from './fusion.mjs';
import {perceptionModel,DEFAULT_PERCEPTION_MODEL,recordModelUsage} from './model-policy.mjs';
export const SPECIALIST_FUSION_MODEL=DEFAULT_PERCEPTION_MODEL;
const agent=new Agent({connect:{timeout:10000}});
const observationPrompt=SOCIAL_PROMPT.split('Return only compact JSON')[0]
  .replace('in the supplied audio and time-ordered video','using the supplied video, local transcript and measurements')
  .replace('use [] if unsupported','leave the signal output empty if unsupported');
const prompt=observationPrompt+`
INPUT LIMITATION: You receive time-ordered video images, local speech transcription and separate acoustic classifiers/measurements. You DO NOT receive the raw waveform. Never claim you heard a tone, pitch, word or pause directly. Acoustic classifier scores are uncalibrated guesses and may disagree with meaning or expression. A short-window happy score alone does not establish a happy current state. Word-search events do not establish uncertainty about knowledge. Use only supported observations; do not fill absent evidence.
Return only a compact JSON object with both keys p and s, including empty results: {"p":0,"s":[]} or {"p":1,"s":[]}. Never return a top-level array. p=1 only for one visible person bound to the communication, 0 if unclear, 2 for multiple people. s is an array of at most four rows, each exactly [signal_code,onset_seconds,end_seconds,support_level,used_modalities,observed_cue]. Times are relative to this window and bounded by duration. support_level is low, medium or high. observed_cue cites a supplied observation in at most 12 words. For used_modalities use only visual, text, acoustic, or + combinations. acoustic means an interpretation of supplied local acoustic evidence, NOT direct listening. Without relevant acoustic evidence do not use acoustic. Without a transcript do not use text. Never use audio as a modality. Emit p then s; no prose or transcript rewrite.`;
const classifierPrompt=observationPrompt+`
You have images, local transcription and acoustic measurements, NOT the raw waveform. Judge CURRENT signals at the latest endpoint; earlier states may have ended. Do not claim direct listening. Local classifier scores are uncertain evidence, not psychological truth. Return only JSON {"p":1,"s":[],"m":[]}. p=1 if the visible person is bound to the current communication, 0 if unclear, 2 for multiple people. s MUST have exactly ten integers in order [${SOCIAL_SIGNALS.map(s=>s.code).join(',')}]. 0=unsupported, 1=weak, 2=moderate, 3=strong support. Evaluate independently, no forced positives. m MUST have exactly ten integer evidence masks in the same order: 0=none, 1=provided acoustic measurements, 2=visible frames, 4=provided transcript; add bits for combinations. Positive s requires nonzero m. Do not use bit 1 without an acoustic measurement or bit 4 without a transcript. No timestamps or rationale. Earlier assistant judgments are not evidence.`;
const sparsePrompt=classifierPrompt.split('Return only JSON')[0]+`
Return only a JSON object with exactly p and s. Always include both fields, including when no signals are supported: {"p":0,"s":[]} for unclear person binding or {"p":1,"s":[]} for a bound person without supported signals. p=1 if the visible person is bound to current communication, 0 if unclear, 2 for multiple people. s contains zero to four supported signals, each exactly three integers [code,level,evidence], never named-field objects. Codes: ${SOCIAL_SIGNALS.map((s,i)=>i+'='+s.code).join(', ')}. level: 1=weak, 2=moderate, 3=strong. evidence is a bit mask: 1=provided acoustic measurements, 2=visible frames, 4=provided transcript; add bits for combinations. Do not use 1 without acoustic evidence or 4 without a transcript. Independently evaluate all ten signals; omit unsupported signals. No forced minimum. No timestamps, rationale or extra fields. Earlier assistant judgments are not evidence.`;
const formatError=()=>Object.assign(new Error('快速融合分类返回格式不完整'),{code:'INVALID_SOCIAL_OUTPUT'});
export function normalizeSpecialistReview(raw,input,{partial=false}={}){
  if(![0,1,2].includes(raw?.p)||!Array.isArray(raw?.s))throw Object.assign(new Error('融合分析返回格式不完整'),{code:'INVALID_SOCIAL_OUTPUT'});
  const s=raw.s.map(row=>{
    const fields=Array.isArray(row)?[...row]:row&&typeof row==='object'?
      ('code' in row?[row.code,row.onset,row.end,row.level,row.modalities,row.cue]:
        [row.signal_code,row.onset_seconds,row.end_seconds,row.support_level,row.used_modalities,row.observed_cue]):[];
    // Complete equivalent modality arrays carry the same evidence. Missing
    // binding, fields, time spans or modalities are never invented.
    if(Array.isArray(fields[4])&&fields[4].every(m=>typeof m==='string'))fields[4]=fields[4].join('+');
    if(typeof fields[4]==='string')fields[4]=fields[4].split(/[+,]/).map(s=>s.trim()).join('+');
    return fields;
  });
  return {...normalizeSocial({...raw,s},{...input,audio:null},{partial,allowAcousticSummary:true}),method:'visual-text-local-acoustic-fusion',rawAudioReceived:false};
}
export function normalizeSpecialistSparse(raw,input){
  if(![0,1,2].includes(raw?.p)||!Array.isArray(raw?.s)||raw.s.length>4)throw formatError();
  const s=Array(10).fill(0),m=Array(10).fill(0),seen=new Set();
  // A lone complete triplet sometimes loses its outer array. This is an
  // unambiguous singleton row; extra values and missing fields remain invalid.
  const rows=raw.s.length===3&&raw.s.every(Number.isInteger)?[raw.s]:raw.s;
  for(const value of rows){
    // Some providers return the same three fields as an object. Accept only
    // the complete equivalent representation, never infer missing values.
    const row=Array.isArray(value)?value:value&&typeof value==='object'&&Object.keys(value).length===3&&['code','level','evidence'].every(k=>Object.hasOwn(value,k))?[value.code,value.level,value.evidence]:[];
    if(!Array.isArray(row)||row.length!==3||row.some(n=>!Number.isInteger(n))||row[0]<0||row[0]>9||row[1]<1||row[1]>3||row[2]<1||row[2]>7||seen.has(row[0]))throw formatError();
    seen.add(row[0]);s[row[0]]=row[1];m[row[0]]=row[2];
  }
  return normalizeSpecialistClasses({p:raw.p,s,m},input);
}
export function normalizeSpecialistClasses(raw,input){
  if(![0,1,2].includes(raw?.p)||!Array.isArray(raw?.s)||raw.s.length!==10||!Array.isArray(raw?.m)||raw.m.length!==10||
    raw.s.some(n=>!Number.isInteger(n)||n<0||n>3)||raw.m.some(n=>!Number.isInteger(n)||n<0||n>7))throw formatError();
  const rows=SOCIAL_SIGNALS.map((def,i)=>({def,level:raw.s[i],mask:raw.m[i]})).filter(v=>v.level&&v.mask)
    .sort((a,b)=>b.level-a.level).map(({def,level,mask})=>[def.code,0,input.duration,['','low','medium','high'][level],
      [...(mask&1?['acoustic']:[]),...(mask&2?['visual']:[]),...(mask&4?['text']:[])].join('+'),'图文与本地声音证据的快速估计，等待复核']);
  const result=normalizeSocial({p:raw.p,s:rows},{...input,audio:null},{partial:true,allowAcousticSummary:true});
  return {...result,temporalResolution:'window',rawAudioReceived:false,method:'compact-visual-local-classifier',signals:result.signals.map(s=>({...s,tentative:true,temporalResolution:'window'}))};
}
export async function analyzeSpecialistSocial(input,config,signal,{fetcher=fetch,onPartial=()=>{},onTrace=()=>{},compact=false}={}){
  const model=perceptionModel(config,compact?'fast':'review');
  const began=performance.now(),safeInput={...input,audio:null};
  const decode=(raw,partial=false)=>compact?(compact==='sparse'?normalizeSpecialistSparse:normalizeSpecialistClasses)(raw,safeInput):normalizeSpecialistReview(raw,safeInput,{partial});
  const evidence={...compactEvidence(input),rawAudioReceived:false,
    acousticSummaries:(input.local||[]).filter(o=>o.modality==='声音'&&o.source==='specialist').slice(-4).map(o=>({start:o.start,end:o.end,model:o.model,cue:o.text,details:o.details})),
  };
  // Classifier scores and movement coefficients are uncalibrated. Millisecond
  // and three-decimal precision retain the observations without spending
  // context on many meaningless floating-point digits. Media is untouched.
  const content=[{type:'text',text:JSON.stringify(evidence,(_key,value)=>typeof value==='number'&&Number.isFinite(value)?Math.round(value*1000)/1000:value)}];
  for(const f of input.frames||[])content.push({type:'text',text:`${f.t.toFixed(2)}s`},{type:'image_url',image_url:{url:`data:image/jpeg;base64,${f.image}`}});
  const r=await fetcher(endpoints(config.workspace,config.region).review,{method:'POST',signal,dispatcher:agent,redirect:'error',headers:{Authorization:`Bearer ${config.key}`,'Content-Type':'application/json'},body:JSON.stringify({model,messages:[{role:'system',content:compact==='sparse'?sparsePrompt:compact?classifierPrompt:prompt},{role:'user',content}],response_format:{type:'json_object'},reasoning_effort:'none',temperature:0,max_tokens:compact?180:400,stream:true,stream_options:{include_usage:true}})});
  if(!r.ok){const e=await r.json().catch(()=>null);throw qwenFailure(r.status,e?.error?.code||e?.code);}
  let seen='',firstTokenMs=null,usage=null;
  const text=await completionText(r,t=>{if(t)firstTokenMs??=Math.round(performance.now()-began);if(compact||!/"p"\s*:\s*1\b/.test(t))return;const s=completedArray(t,'s'),key=JSON.stringify(s);if(s.length&&key!==seen){seen=key;onPartial(decode({p:1,s},true));}},value=>{usage=value;});
  recordModelUsage(model,usage);
  onTrace({start:input.start,end:input.end,firstTokenMs,totalMs:Math.round(performance.now()-began),model,output:text,usage,rawAudioReceived:false});
  let raw;try{raw=parseSocial(text);}catch(error){if(compact)throw formatError();throw error;}
  return decode(raw);
}
