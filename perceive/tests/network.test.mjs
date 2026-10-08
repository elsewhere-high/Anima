import test from 'node:test';
import assert from 'node:assert/strict';
import {systemProxyOptions,modelProxyOptions} from '../network.mjs';
import {analyzeGemini,validateInput} from '../perceive.mjs';

test('仅沿用已经启用的系统代理，不启用关闭或无效的配置',()=>{
  assert.deepEqual(systemProxyOptions('HTTPEnable : 0\nHTTPProxy : 127.0.0.1\nHTTPPort : 7897\nHTTPSEnable : 1\nHTTPSProxy : 127.0.0.1\nHTTPSPort : 7897'),{httpsProxy:'http://127.0.0.1:7897/'});
  assert.deepEqual(systemProxyOptions('HTTPEnable : 1\nHTTPProxy : localhost\nHTTPPort : 99999'),{});
});
test('显式代理设置优先；保留绕过列表，系统设置读取失败仍能启动',()=>{
  const result=modelProxyOptions({HTTPS_PROXY:'http://localhost:8000',NO_PROXY:'localhost,example.test'},'darwin',()=>{throw new Error('不应读取系统设置');});
  assert.equal(result.httpsProxy,'http://localhost:8000');assert.equal(result.noProxy,'localhost,example.test');
  assert.deepEqual(modelProxyOptions({},'darwin',()=>{throw new Error('不可用');}),{noProxy:'localhost,127.0.0.1,::1'});
});
test('区分密钥与配额错误，避免回显上游敏感响应',async()=>{
  const input=validateInput({duration:1,frames:[{image:'aW1hZ2U=',t:0}]});
  await assert.rejects(()=>analyzeGemini(input,{key:'test-secret',model:'m'},undefined,async()=>Response.json({error:{message:'API key not valid: test-secret',details:[{reason:'API_KEY_INVALID'}]}},{status:400})),error=>error.message.includes('密钥无效')&&!error.message.includes('test-secret'));
  await assert.rejects(()=>analyzeGemini(input,{key:'test-secret',model:'m'},undefined,async()=>Response.json({error:{message:'test-secret'}},{status:429})),error=>error.message.includes('配额')&&!error.message.includes('test-secret'));
});
