import {readFile,writeFile} from 'node:fs/promises';
const [input,output]=process.argv.slice(2);
const log=JSON.parse(await readFile(input,'utf8'));
if(log.suite!=='cremad-neutral')throw Error('Expected the frozen CREMA-D neutral suite');
const rows=JSON.parse(await readFile(new URL('./cremad/neutral-selection.json',import.meta.url),'utf8')).rows;
const neutral=name=>/neutral|中立/.test(name);
const runs=log.runs.map(r=>{
 const reference=rows.find(x=>x.FileName===r.id);if(!reference)throw Error('Unregistered evaluation sample');
 const aggregate=kind=>{const events=r.events.filter(e=>e.type==='measurement'&&e.kind===kind&&e.quality==='ok'),scores={};for(const e of events)for(const [name,score]of Object.entries(e.scores||{}))scores[name]=(scores[name]||0)+score/events.length;const top=Object.entries(scores).sort((a,b)=>b[1]-a[1])[0];return {windows:events.length,meanScores:scores,top:top?.[0],neutralMatch:top?neutral(top[0]):null};};
 const displayed=[...new Set(r.display.flatMap(d=>d.signals.map(s=>s.label)))];
 return {id:r.id,reference:{audio:reference.VoiceVote,visual:reference.FaceVote,audiovisual:reference.MultiModalVote},displayed,
   nonneutralExpressionLabels:displayed.filter(s=>/表情|语调/.test(s)),voice:aggregate('voice'),face:aggregate('face'),notices:r.notices.length,error:r.error||null};
});
const report={createdAt:new Date().toISOString(),input,scope:'Six frozen new-speaker neutral clips; crowd-plurality basic-emotion check, not ten-social-signal accuracy or unseen-by-pretraining guarantee.',rules:'Confidence may coexist with neutral affect. Nonneutral expression labels conflict with neutral clip-level votes but need temporal review; social labels are listed without inventing social ground truth.',runs};
await writeFile(output,JSON.stringify(report,null,2));console.log(JSON.stringify(runs.map(r=>({id:r.id,displayed:r.displayed,voiceNeutral:r.voice.neutralMatch,faceNeutral:r.face.neutralMatch,notices:r.notices}))));
