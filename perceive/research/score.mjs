import {readFile,writeFile} from 'node:fs/promises';
import {validateManifest,measure,groupedDifference} from './metrics.mjs';
const [manifestFile,fullFile,baselineFile,output='research-result.json']=process.argv.slice(2);
if(!manifestFile||!fullFile||!baselineFile){console.error('用法：node research/score.mjs manifest.json full.json baseline.json output.json');process.exit(1);}
const read=async file=>JSON.parse(await readFile(file,'utf8'));
const manifest=validateManifest(await read(manifestFile)),full=await read(fullFile),baseline=await read(baselineFile),heldout=manifest.samples.filter(s=>s.split==='heldout');
const result={scope:manifest.scope||'用户提供的人工标注',heldout:heldout.length,full:measure(heldout,full),baseline:measure(heldout,baseline),comparison:groupedDifference(heldout,full,baseline),warning:'引用可追溯不等于依据正确；证据正确性和时间需人工标注。禁止把模型输出当作真值。'};
await writeFile(output,JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
