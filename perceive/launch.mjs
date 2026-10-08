import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createApp} from './server.mjs';
import {localPerceptionRuntime} from './perception-runtime.mjs';

process.chdir(fileURLToPath(new URL('.',import.meta.url)));
if(existsSync('.env'))process.loadEnvFile('.env');
const localAsr=process.env.ANIMA_LOCAL_ASR==='1';
process.env.ANIMA_TORCH_THREADS??='1';
process.env.ANIMA_FAST_MODEL??='qwen3.7-flash';
process.env.ANIMA_PERCEPTION_MODEL??='qwen3.8-max';
if(process.env.ANIMA_DISFLUENCY===undefined&&existsSync('integrations/models/romana-disfluency'))process.env.ANIMA_DISFLUENCY='1';
const port=Number(process.env.PORT)||4827,url=`http://127.0.0.1:${port}/`;
let running=false;
try{
  const response=await fetch(`${url}api/status`,{signal:AbortSignal.timeout(1200)});
  const result=await response.json();
  running=response.ok&&result.realtime===true&&result.protocol==='anima.perceive.v2'&&Array.isArray(result.signals);
}catch{}
if(running)console.log(`Anima 已在运行，请打开 ${url}`);
else {
  const server=createApp(localPerceptionRuntime({localAsr,reviewHop:2}));
  server.on('error',error=>{console.error(error.code==='EADDRINUSE'?`端口 ${port} 已被其他程序占用。请先关闭该程序，或在 .env 中调整 PORT。`:'Anima 启动失败，请检查本地环境。');process.exitCode=1;});
  server.listen(port,'127.0.0.1',()=>console.log(`Anima 已启动，请打开 ${url}\n停止服务：Control + C`));
}
