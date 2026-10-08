import test from 'node:test';
import assert from 'node:assert/strict';
import {externalFusion,fusionRequest} from '../fusion-provider.mjs';
test('MiniCPM 推理保留原声和画面，绝不把千问密钥转发给另一个模型服务',()=>{
  const fusion=externalFusion({ANIMA_FUSION_BASE_URL:'http://127.0.0.1:8000/v1',ANIMA_FUSION_API_KEY:'separate-key'});
  const r=fusionRequest({key:'qwen-secret',fusion},[{type:'input_audio',input_audio:{data:'data:;base64,YQ=='}},{type:'image_url',image_url:{url:'data:image/jpeg;base64,Yg=='}}],'prompt');
  assert.equal(r.url,'http://127.0.0.1:8000/v1/chat/completions');assert.equal(r.key,'separate-key');
  assert.equal(r.body.messages[1].content[0].audio_url.url,'data:audio/wav;base64,YQ==');
  assert.equal(JSON.stringify(r).includes('qwen-secret'),false);
});
test('未配置候选模型就明确使用现有模型，拒绝携带密码或明文远程地址',()=>{
  assert.equal(externalFusion({}),null);
  for(const url of ['http://remote.test/v1','https://user:secret@host/v1','https://host/v1?key=x'])assert.throws(()=>externalFusion({ANIMA_FUSION_BASE_URL:url}));
});
