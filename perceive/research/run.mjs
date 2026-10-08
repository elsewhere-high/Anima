import {readFile,writeFile} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
const [file,mode='full',output='predictions.json']=process.argv.slice(2);
if(!file){console.error('用法：node research/run.mjs inputs.json [full|baseline|text|audio|video] output.json');process.exit(1);}
const manifest=JSON.parse(await readFile(file,'utf8')),origin='http://127.0.0.1:4827',status=await(await fetch(origin+'/api/status')).json();
if(!status.configured)throw new Error('先在 Anima 页面配置模型');
const result=[];
for(const sample of manifest.samples){
  const input=sample.inputFile?JSON.parse(await readFile(resolve(dirname(file),sample.inputFile),'utf8')):sample.input;
  try{
    const response=await fetch(origin+'/api/evaluate',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json','X-Anima-Token':status.token},body:JSON.stringify({input,mode}),signal:AbortSignal.timeout(50000)}),data=await response.json();
    result.push({id:sample.id,mode,...data});console.log(sample.id,response.ok?'完成':'失败');
  }catch{result.push({id:sample.id,mode,error:'请求失败'});console.log(sample.id,'失败');}
  await writeFile(output,JSON.stringify(result,null,2));
}
