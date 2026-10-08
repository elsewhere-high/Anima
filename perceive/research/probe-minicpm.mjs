// Public research media only; no camera, microphone, API key, or cloud service.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {SOCIAL_PROMPT,parseSocial} from '../social.mjs';
const manifestPath=resolve(process.argv[2]||'research/minicpm-probe/elon-musk-wef/manifest.json');
const manifest=JSON.parse(await readFile(manifestPath)),out=dirname(manifestPath),origin='http://127.0.0.1:9060';
await mkdir(out,{recursive:true});
const report={createdAt:new Date().toISOString(),model:'MiniCPM-o4.5-Q4_K_M',engineCommit:'873056743b74e1a4ce5dcf7290e2298428e214db',
  clip:manifest.clip,duration:manifest.duration,scope:'Bounded-prefix local feasibility; serial prefill, not production realtime or held-out accuracy',steps:[]};
const save=()=>writeFile(resolve(out,'result.json'),JSON.stringify(report,null,2));
async function post(path,body,timeout=120000){const began=performance.now(),r=await fetch(origin+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(timeout)});if(!r.ok)throw new Error(path+' HTTP '+r.status+': '+(await r.text()).slice(0,300));const value=await r.json();report.steps.push({path,ms:Math.round(performance.now()-began),value});await save();return value;}
try{
  await post('/v1/stream/omni_init',{media_type:2,use_tts:false,duplex_mode:false,output_dir:out,
    voice_clone_prompt:'<|im_start|>system\n'+SOCIAL_PROMPT+'<|im_end|>\n',assistant_prompt:'<|im_start|>user\n'});
  // In this pinned revision init does not prefill the system prompt. Source
  // inspection (server-omni.cpp / omni.cpp) takes precedence over older docs.
  await post('/v1/stream/prefill',{audio_path_prefix:'',img_path_prefix:'',cnt:0});
  const began=performance.now();
  for(const [i,chunk] of manifest.chunks.entries())await post('/v1/stream/prefill',{
    audio_path_prefix:chunk.audio,img_path_prefix:chunk.image,cnt:i+1,max_slice_nums:1,
    text:i===manifest.chunks.length-1?`Observe the supplied ${manifest.duration} seconds. Return only the requested JSON, with all event times inside 0 to ${manifest.duration}. Do not answer the speaker's spoken question.`:''});
  report.prefillTotalMs=Math.round(performance.now()-began);
  const decodeAt=performance.now(),r=await fetch(origin+'/v1/stream/decode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stream:true,debug_dir:out,round_idx:0}),signal:AbortSignal.timeout(120000)});
  if(!r.ok)throw new Error('decode HTTP '+r.status);
  let buffer='',text='';const decoder=new TextDecoder();
  for await(const bytes of r.body){buffer+=decoder.decode(bytes,{stream:true});let line;
    while((line=buffer.indexOf('\n'))>=0){const row=buffer.slice(0,line).trim();buffer=buffer.slice(line+1);if(!row.startsWith('data:')||row.slice(5).trim()==='[DONE]')continue;const event=JSON.parse(row.slice(5));if(event.content){report.firstContentMs??=Math.round(performance.now()-decodeAt);text+=event.content;report.output=text;}}
  }
  report.output=text;report.decodeMs=Math.round(performance.now()-decodeAt);report.totalInferenceMs=Math.round(performance.now()-began);
  try{report.parsed=parseSocial(text);}catch{report.parseFailed=true;}
}catch(error){report.error=error.message;process.exitCode=1;}
await save();console.log(JSON.stringify({clip:report.clip,prefillMs:report.prefillTotalMs,decodeMs:report.decodeMs,output:report.output,error:report.error}));
