async page => {
 const checks=[],errors=[];const assert=(ok,msg)=>{if(!ok)throw Error(msg);checks.push(msg)};
 page.on('pageerror',e=>errors.push(e.message));
 await page.reload();await page.waitForFunction(()=>window.voiceConversation);
 // Synthetic browser media only: never opens the user's physical camera or microphone.
 await page.evaluate(()=>{
  const streams=[],contexts=[];window.mediaTest={streams,contexts};
  navigator.mediaDevices.getUserMedia=async constraints=>{
   let stream;if(constraints.video){const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;const ctx=canvas.getContext('2d');ctx.fillStyle='#d7e2dc';ctx.fillRect(0,0,640,480);stream=canvas.captureStream(5)}else{const ctx=new AudioContext();contexts.push(ctx);stream=ctx.createMediaStreamDestination().stream}streams.push(stream);return stream;
  };
  window.SpeechSynthesisUtterance=class {constructor(text){this.text=text}};
  speechSynthesis.getVoices=()=>[{localService:true,lang:'zh-CN'}];
  speechSynthesis.speak=utterance=>setTimeout(()=>utterance.onend(),20);speechSynthesis.cancel=()=>{};
 });
 await page.route('**/v1/vision/analyze',route=>route.fulfill({json:{frame_id:'ui-synthetic-frame',frame_size:[640,480],faces:[],latency_ms:1,sampling:{next_sample_ms:1500}}}));
 const click=id=>page.locator('#'+id).click();
 await click('guestContinue');await click('confirmSetup');await click('confirmSetup');await page.locator('[data-step="4"]').waitFor({state:'visible'});await page.waitForFunction(()=>document.getElementById('serviceCheckStatus').textContent.includes('已就绪'));
 await page.getByText('摄像头连接选项',{exact:true}).click();await page.locator('#cameraMode').selectOption('browser');await page.getByText('摄像头连接选项',{exact:true}).click();await click('cameraOn');await page.waitForFunction(()=>window.cameraController.active&&document.getElementById('video').videoWidth>0);assert(await page.evaluate(()=>window.cameraController.active),'camera checked during preparation');
 await click('testMic');await page.waitForFunction(()=>document.getElementById('micCheckStatus').textContent.includes('已连接'));assert(await page.evaluate(()=>mediaTest.streams.filter(s=>s.getAudioTracks().length).every(s=>s.getTracks().every(t=>t.readyState==='ended'))),'microphone probe releases all tracks');
 await click('voicePreview');await page.locator('#heardVoice').waitFor({state:'visible'});await click('heardVoice');await click('confirmSetup');await page.locator('#workspace').waitFor({state:'visible'});await page.waitForFunction(()=>window.voiceConversation.phase==='listening');
 assert(await page.evaluate(()=>document.getElementById('video').closest('#workspace')!==null&&window.cameraController.active),'live preview preserved on transition');assert(await page.locator('#voiceStart').isHidden(),'running voice hides start');assert(await page.locator('#voiceInterrupt').isHidden(),'interrupt only appears while speaking');assert(await page.locator('#voiceStop').isVisible(),'pause always reachable while listening');
 for(const [width,height,label] of [[1440,900,'desktop'],[390,844,'mobile'],[1366,768,'laptop'],[390,660,'short-mobile']]){
  await page.setViewportSize({width,height});const rect=await page.locator('#voiceStop').boundingBox();const send=await page.locator('#send').boundingBox();assert(rect.y>=0&&rect.y+rect.height<=height&&send.y+send.height<=height,label+' voice and composer fit');await page.screenshot({path:'output/playwright/guided-voice-'+label+'.png'});
 }
 await click('voiceStop');assert(await page.evaluate(()=>!voiceConversation.active&&cameraController.active),'pausing voice preserves camera');await click('openSettings');await click('editDevices');await page.locator('[data-step="4"]').waitFor({state:'visible'});assert(await page.evaluate(()=>document.getElementById('video').closest('#setupCameraSlot')!==null),'preview returns to device settings');
 await page.evaluate(async()=>{voiceConversation.stop();await Promise.all(mediaTest.contexts.map(c=>c.close()))});assert(await page.evaluate(()=>mediaTest.streams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))),'all synthetic media released');assert(errors.length===0,'no media flow runtime errors');await page.unroute('**/v1/vision/analyze');await page.reload();return {checks,synthetic_media:true,physical_devices_used:false,errors};
}
