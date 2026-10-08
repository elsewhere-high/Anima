import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,readdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {runSaver} from '../research/save-run.mjs';
import {createApp} from '../server.mjs';

test('研究存档只允许已知公共案例，完成后落盘，重试不会产生重复文件',async()=>{
  const directory=await mkdtemp(join(tmpdir(),'anima-runs-'));
  try{
    const save=runSaver(directory),record={variant:'local-sparse',suite:'interhuman',requestedRounds:1,control:null,createdAt:'2026-10-08T00:00:00.000Z',protocol:'candidate-core-aligned-live-with-silero-v6',runs:[{id:'yann-lecun-wef',round:1,events:[],display:[],completedAt:9}]};
    await save(record);await save(record);
    const files=await readdir(directory);assert.equal(files.length,1);
    assert.equal(JSON.parse(await readFile(join(directory,files[0]),'utf8')).runs[0].completedAt,9);
    await assert.rejects(()=>save({...record,variant:'../../escape'}));
    await assert.rejects(()=>save({...record,runs:[{...record.runs[0],completedAt:undefined}]}));
  }finally{await rm(directory,{recursive:true,force:true});}
});

test('研究保存接口遵守来源与令牌限制，普通应用不启用该接口',async()=>{
  let count=0;
  for(const enabled of [false,true]){
    const server=createApp({onResearchRun:enabled?async()=>{count++;}:undefined,specialists:{start(){},close(){},status(){return{};}}});
    server.listen(0,'127.0.0.1');await once(server,'listening');
    const base=`http://127.0.0.1:${server.address().port}`;
    try{
      const {token}=await(await fetch(base+'/api/status')).json();
      const headers={'Content-Type':'application/json',Origin:base,'X-Anima-Token':token};
      assert.equal((await fetch(base+'/api/research/run',{method:'POST',headers:{...headers,'X-Anima-Token':'wrong'},body:'{}'})).status,403);
      assert.equal((await fetch(base+'/api/research/run',{method:'POST',headers,body:'{}'})).status,enabled?200:404);
    }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
  }
  assert.equal(count,1);
});
