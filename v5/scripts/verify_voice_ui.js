async (page) => {
 const sampleResponse=await page.request.post('http://127.0.0.1:8768/v1/voice/speak',{data:{text:'你好，我今天有点累，想和你聊聊天。',voice:'zh-CN-XiaoxiaoNeural'}});
 if(!sampleResponse.ok())throw Error('Synthetic fixture unavailable');
 const sample=(await sampleResponse.body()).toString('base64');
 const assert=(v,m)=>{if(!v)throw Error(m)};
 await page.setViewportSize({width:1440,height:1000});
 await page.waitForFunction(()=>window.voiceConversation);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'desktop overflow');
 await page.screenshot({path:'output/playwright/voice-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile overflow');
 await page.screenshot({path:'output/playwright/voice-mobile.png',fullPage:true});
 await page.setViewportSize({width:1440,height:1000});
 await page.getByRole('button',{name:'暂不登录，以访客体验',exact:true}).click();
 await page.locator('#cloudVoiceConsent').check();
 await page.getByRole('button',{name:'确认以上选择，进入对话',exact:true}).click();
 await page.context().grantPermissions(['microphone','camera']);
 const hardware=await page.evaluate(async()=>{const s=await navigator.mediaDevices.getUserMedia({audio:true});const tracks=s.getAudioTracks().map(t=>({label:t.label,state:t.readyState}));s.getTracks().forEach(t=>t.stop());return tracks});
 console.log('MIC_HARDWARE',JSON.stringify(hardware));
 await page.evaluate(async encoded=>{
  const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  window.testAudioContext=new AudioContext();await window.testAudioContext.resume();
  const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));const buffer=await window.testAudioContext.decodeAudioData(bytes.buffer);
  navigator.mediaDevices.getUserMedia=async constraints=>{
   if(!constraints.audio)return original(constraints);
   const dest=window.testAudioContext.createMediaStreamDestination();const source=window.testAudioContext.createBufferSource();source.buffer=buffer;source.connect(dest);
   const wait=setInterval(()=>{if(window.voiceConversation.phase==='listening'){clearInterval(wait);setTimeout(()=>source.start(),700)}},100);
   return dest.stream;
  };
 },sample);
 await page.getByRole('button',{name:'开始语音对话',exact:true}).click();
 await page.waitForFunction(()=>window.voiceConversation.phase==='speaking',null,{timeout:60000});
 assert((await page.locator('#voiceCaption').textContent()).includes('累'),'transcript missing');
 // Let this reply finish to verify automatic return to listening.
 await page.waitForFunction(()=>window.voiceConversation.phase==='listening',null,{timeout:30000});
 await page.getByRole('button',{name:'结束对话',exact:true}).click();
 assert(await page.evaluate(()=>!window.voiceConversation.active),'stop failed');
 await page.evaluate(()=>{stopCamera();window.testAudioContext.close()});
 return ({desktop_mobile_overflow:false,voice_turn:true,automatic_resume:true,stop:true,reply:await page.locator('#latestReply').textContent()});
}
