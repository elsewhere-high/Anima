import {mkdir,writeFile,rename} from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {join} from 'node:path';

const suites={interhuman:['yann-lecun-wef','steve-jobs-interview','elon-musk-wef','pep-guardiola-press','mark-zuckerberg-interview'],
  'cremad-neutral':['1001_DFA_NEU_XX','1002_DFA_NEU_XX','1003_DFA_NEU_XX','1004_IEO_NEU_XX','1005_DFA_NEU_XX','1006_DFA_NEU_XX'],
  'app-live':['yann-lecun-wef','yann-continuous']};
// Only the research server installs this hook. Names come from a fixed public suite;
// the caller cannot choose an output path. Each completed clip survives tab closure.
export function runSaver(directory){
  return async body=>{
    const {variant,suite,requestedRounds,control,createdAt,protocol,models,runs}=body||{};
    if(!/^[a-z0-9-]{1,64}$/.test(variant)||!suites[suite]||!Number.isInteger(requestedRounds)||requestedRounds<1||requestedRounds>3||
      ![null,'blank','mute','no-video'].includes(control)||typeof createdAt!=='string'||!Number.isFinite(Date.parse(createdAt))||
      !['candidate-core-aligned-live-with-silero-v6','application-stream-v1'].includes(protocol)||!Array.isArray(runs)||runs.length!==1)throw new Error('Invalid run');
    const run=runs[0];
    if(!suites[suite].includes(run.id)||!Number.isInteger(run.round)||run.round<1||run.round>requestedRounds||
      !Array.isArray(run.events)||!Array.isArray(run.display)||(!Number.isFinite(run.completedAt)&&typeof run.error!=='string'))throw new Error('Incomplete run');
    const record={variant,suite,requestedRounds,control,createdAt,protocol,models,cameraAccess:false,microphoneAccess:false,runs};
    const data=JSON.stringify(record,null,2);if(Buffer.byteLength(data)>5*1024*1024)throw new Error('Run too large');
    const group=createHash('sha256').update(JSON.stringify([createdAt,variant,suite,control])).digest('hex').slice(0,20);
    const target=join(directory,`${group}-${run.round}-${run.id}.json`),temporary=target+'.'+randomUUID()+'.tmp';
    await mkdir(directory,{recursive:true});await writeFile(temporary,data,{mode:0o600});await rename(temporary,target);
  };
}
