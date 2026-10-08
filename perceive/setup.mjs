import { mkdir, cp, stat, writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

const root = fileURLToPath(new URL('.', import.meta.url));
const publicDir = join(root, 'public');
const clips = ['yann-lecun-wef','steve-jobs-interview','elon-musk-wef','pep-guardiola-press','mark-zuckerberg-interview'];
const assets = clips.flatMap(id => [
  {path:`assets/${id}.mp4`,url:`https://www.interhuman.ai/videos/v3demo/${id}.mp4`},
  {path:`assets/${id}.jpg`,url:`https://www.interhuman.ai/images/v3demo/reel-posters/${id}.jpg`}
]);
assets.push({path:'models/face_landmarker.task',url:'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'});
for (const dir of ['assets','models','vendor/vision','vendor/vad','vendor/ort']) await mkdir(join(publicDir,dir),{recursive:true});
const downloads = await Promise.allSettled(assets.map(async asset => {
  const target = join(publicDir,asset.path);
  if (!(await stat(target).catch(()=>null))?.size) {
    const response = await fetch(asset.url,{signal:AbortSignal.timeout(120000)});
    if (!response.ok) throw new Error(`${asset.path}: HTTP ${response.status}`);
    await writeFile(target,Buffer.from(await response.arrayBuffer()));
  }
  const bytes = await readFile(target);
  return {...asset,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
}));
await cp(join(root,'node_modules/@mediapipe/tasks-vision/vision_bundle.mjs'),join(publicDir,'vendor/vision/vision_bundle.mjs'));
await cp(join(root,'node_modules/@mediapipe/tasks-vision/vision_bundle.js'),join(publicDir,'vendor/vision/vision_bundle.js'));
await cp(join(root,'node_modules/@mediapipe/tasks-vision/wasm'),join(publicDir,'vendor/vision/wasm'),{recursive:true});
await cp(join(root,'node_modules/@ricky0123/vad-web/dist'),join(publicDir,'vendor/vad'),{recursive:true});
await cp(join(root,'node_modules/onnxruntime-web/dist'),join(publicDir,'vendor/ort'),{recursive:true});
await writeFile(join(root,'asset-manifest.json'),JSON.stringify(downloads.filter(r=>r.status==='fulfilled').map(r=>r.value),null,2)+'\n');
for (const r of downloads) if (r.status==='rejected') console.error(r.reason.message);
if (downloads.some(r=>r.status==='rejected')) process.exitCode=1;
else console.log('5 个案例与本地感知模型已就绪。');
