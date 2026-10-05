'use strict';
(() => {
 let step=1,confirmed=false,guest=false,savedMemory=false,entered=false;
 let micReady=false,speakerReady=false,previewPassed=false,serviceReady=false,checking=false;
 let micTest=null,micEpoch=0;
 const panel=$('setupPanel');
 const isVoice=()=>$('modeVoice').checked;
 const needsCloudConsent=()=>isVoice()&&$('voiceChoice').value!=='device'&&!$('cloudVoiceConsent').checked;
 let advancing=false;
 function updateNext(){
  const needsConsent=step===3&&needsCloudConsent();
  $('voiceAlternatives').hidden=step!==3||!isVoice();
  $('confirmSetup').textContent=advancing?'正在处理…':step===4?(isVoice()?'进入对话，开始听你说':'进入对话'):step===3?(needsConsent?'同意在线朗读并继续':'下一步：检查设备'):'下一步';
  if(step===3){$('stepHelp').textContent=needsConsent?'使用在线声音时，回复文字会发送给微软语音服务。点击右侧按钮表示同意；也可以改用本地声音或文字。':!isVoice()?'文字交流不需要麦克风，也不使用在线朗读。':$('voiceChoice').value==='device'?'使用设备本地声音，不发送文字到在线语音服务。':'已允许在线朗读，下一步检查麦克风和声音。'}
  $('confirmSetup').setAttribute('aria-describedby','stepHelp wizardFeedback');
 }
 function feedback(text=''){const el=$('wizardFeedback');el.textContent=text;el.hidden=!text;el.classList.toggle('error',!!text)}
 function showPage(id){for(const name of ['setupPanel','workspace','memoryPage','settingsPage'])$(name).hidden=name!==id;$('openSettings').hidden=id!=='workspace'}
 function stopMicTest(){micEpoch++;micTest?.getTracks().forEach(t=>t.stop());micTest=null;checking=false;$('testMic').disabled=false;}
 function go(next){
  stopMicTest();clearTimeout(noticeTimer);$('notice').hidden=true;feedback();step=next;showPage('setupPanel');
  for(const el of document.querySelectorAll('[data-step]'))el.hidden=Number(el.dataset.step)!==step;
  for(const el of document.querySelectorAll('[data-progress]')){if(Number(el.dataset.progress)===step)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current')}
  $('previousStep').hidden=step===1;$('confirmSetup').hidden=step===1;
  $('confirmSetup').textContent=step===4?(isVoice()?'进入对话，开始听你说':'进入对话'):'下一步';
  $('stepHelp').textContent=['','登录成功后自动进入下一步','只使用你同意的功能','不确定？保留默认偏好即可','设备不可用时，可以改用文字或跳过画面'][step];
  $('stepBody').scrollTop=0;document.querySelector(`[data-step="${step}"] h2`).focus({preventScroll:true});
  if(step===4){$('setupCameraSlot').append($('cameraSurface'));updateDevices();void checkService()}
  sync();updateNext();
 }
 function requireSetup(text='请先完成准备，再开始对话。'){window.voiceConversation?.stop({keepCamera:true});go(token||guest?2:1);$('setupHint').textContent=text}
 function sync(){
  window.personalityController?.render();const name=currentId?(members.find(m=>m.user_id===currentId)?.display_name||currentId):'访客';
  $('loggedIdentity').hidden=!token;$('loginEntry').hidden=!!token;$('loggedIdentityLabel').textContent=`你已登录：${name}。可以继续准备，也可以切换成员。`;
  $('sessionLabel').textContent=entered?`${name} · ${savedMemory?'记忆已开启':'本次聊天'}`:'一步一步，准备好再聊';
  $('setupSummary').textContent=token?`${name}，这些选择随时可以在设置中修改。`:'访客体验：不会保存长期记忆，也不需要登记人脸。';
  $('guestContinue').disabled=!!token;$('consent').disabled=!token;if(!token)$('consent').checked=false;
  $('memoryConsentHint').textContent=token?'保存你告诉我的事实和偏好，下次接着聊。关闭后会删除已有长期记忆。':'访客不保存长期记忆；登录成员后可以开启。';
  $('switchMember').hidden=!!token;$('logout').hidden=!token;
  for(const id of ['deleteFace','forgetAll','deleteMember'])$(id).disabled=!token;
  $('accountHint').textContent=token?'这些操作会影响当前成员的资料，请按需使用。':'访客没有已保存的成员资料。';
  $('enrollHint').textContent=!token?'访客无法登记人脸；可以跳过此项。':!stream?'先开启摄像头，再登记人脸。':!$('faceConsent').checked?'如需登记，请先勾选本人同意。':'准备好了，点击采集即可。';
  const options=$('memberSuggestions');if(options.dataset.ids!==JSON.stringify(members)){options.replaceChildren();for(const m of members){const option=document.createElement('option');option.value=m.user_id;option.label=m.display_name;options.append(option)}options.dataset.ids=JSON.stringify(members)}
  if(step===4&&!panel.hidden)updateDeviceHint();
  $('liveCameraStatus').textContent=stream?'画面仅在本机处理':'摄像头已暂停';$('toggleLiveCamera').textContent=stream?'暂停画面':'开启画面';renderMemory();
 }
 function savedConsent(){savedMemory=$('consent').checked;sync()}
 function signedIn(){guest=false;confirmed=false;savedConsent();$('loginHint').classList.remove('error');go(2)}
 function reset(){stopMicTest();confirmed=false;guest=false;savedMemory=false;entered=false;micReady=speakerReady=false;previewPassed=false;$('setupCameraSlot').append($('cameraSurface'));go(1);renderMemory()}
 function updateMode(){
  $('voiceSettings').hidden=!isVoice();$('cloudConsentRow').hidden=$('voiceChoice').value==='device';
  $('micCheck').hidden=!isVoice();$('speakerCheck').hidden=!isVoice();$('fallbackText').hidden=!isVoice();$('liveVoicePanel').hidden=!isVoice();feedback();updateNext();
 }
 function updateDevices(){
  updateMode();$('cameraChecks').hidden=!$('cameraConsent').checked;$('cameraSkipped').hidden=$('cameraConsent').checked;$('setupCameraSlot').hidden=!$('cameraConsent').checked;
  if(!$('cameraConsent').checked){stopCamera();$('cameraPlaceholder').textContent='这次用声音或文字陪你聊'}else if(!stream)$('cameraPlaceholder').textContent='点击下方“开启摄像头”检查画面';
  $('micCheckStatus').textContent=micReady?'麦克风已连接，进入对话后开始收音。':'点击检查，允许浏览器使用麦克风。';
  $('speakerCheckStatus').textContent=speakerReady?'声音已确认。':'点击试听，再确认你能听见。';updateDeviceHint();
 }
 function missingDevices(){const missing=[];if(!serviceReady)missing.push('等待本地服务就绪');if($('cameraConsent').checked&&!stream)missing.push('开启摄像头，或选择这次不用');if(isVoice()&&!micReady)missing.push('检查麦克风');if(isVoice()&&!speakerReady)missing.push('试听并确认声音');return missing}
 function updateDeviceHint(){const missing=missingDevices();$('deviceHint').textContent=missing.length?'还需要：'+missing.join('；')+'。':'准备好了，可以进入对话。';if(step===4){$('stepHelp').textContent=$('deviceHint').textContent;if(!$('wizardFeedback').hidden)feedback(missing.length?$('deviceHint').textContent:'')}}
 async function checkService(){
  serviceReady=false;$('serviceCheckStatus').textContent='正在连接本地服务…';$('retryService').disabled=true;
  try{const h=await api('/health');if(h.status!=='ready')throw Error('模型正在准备，请稍后重新检查');if(isVoice()){const options=await api('/v1/voice/options');if(!options.recognition_ready)throw Error('语音识别尚未就绪，可先改用文字')}serviceReady=true;$('serviceCheckStatus').textContent='已就绪，可以开始交流。';$('health').textContent='本地服务已就绪'}catch(e){$('serviceCheckStatus').textContent='暂未就绪：'+e.message}finally{$('retryService').disabled=false;updateDeviceHint()}
 }
 async function saveUsage(){
  if(token&&savedMemory!==$('consent').checked){
   if(savedMemory&&!confirm('关闭长期记忆会删除已保存的记忆和提醒，是否继续？'))return false;
   const r=await api('/v1/memory/consent','PUT',{memory_consent:$('consent').checked});savedMemory=r.memory_consent;
   $('memoryState').textContent=savedMemory?'长期记忆已开启':'长期记忆未开启';if(!savedMemory)window.personalityController?.reset();clearConversation();await loadMemory();
  }
  sync();return true;
 }
 function enterWorkspace(){clearTimeout(noticeTimer);$('notice').hidden=true;entered=true;confirmed=true;showPage('workspace');$('liveCameraSlot').append($('cameraSurface'));updateMode();sync();$('speech').focus({preventScroll:true})}
 function open(at=2){if(!token&&!guest){go(1);return}window.voiceConversation?.stop({keepCamera:true});go(at)}
 function renderMemory(){
  const allowed=!!token&&savedMemory,preview=$('memoryPreview');preview.replaceChildren();
  $('memoryControls').hidden=!allowed;$('enableMemory').hidden=allowed;
  $('memoryPageHint').textContent=allowed?'随时查阅、纠正或删除。':token?'你还没有开启长期记忆。开启后，可以记住你愿意分享的生活小事。':'访客模式不保存长期记忆。登录成员后可以开启。';
  const items=allowed?records.filter(r=>r.active&&['fact','preference'].includes(r.kind)).slice(0,3):[];
  const mbti=allowed?window.personalityController?.savedMbti():null;
  if(mbti){const el=document.createElement('article'),label=document.createElement('small'),p=document.createElement('p');label.textContent='长期沟通偏好';p.textContent='我的 MBTI：'+mbti;el.append(label,p);preview.append(el)}
  if(!items.length&&!mbti){const p=document.createElement('p');p.textContent=!token?'访客体验不会保存长期记忆。':!savedMemory?'长期记忆未开启，可以在设置中开启。':'还没有记忆。你可以说：“请记住，我的眼镜放在卧室抽屉。”';preview.append(p)}
  for(const item of items){const el=document.createElement('article'),label=document.createElement('small'),p=document.createElement('p');label.textContent=item.kind==='fact'?'生活小事':'你的偏好';p.textContent=item.text;el.append(label,p);preview.append(el)}
 }
 $('toggleRegister').onclick=()=>{const creating=$('nameField').hidden;$('nameField').hidden=!creating;$('register').hidden=!creating;$('login').hidden=creating;$('toggleRegister').textContent=creating?'已有成员？去登录':'第一次来？新建成员';$('pin').autocomplete=creating?'new-password':'current-password';$('loginHint').textContent=creating?'填写成员 ID、至少 6 位 PIN 和称呼，创建后自动继续。':'输入成员 ID 和 PIN，登录后自动进入下一步。'};
 for(const id of ['uid','pin','name'])$(id).addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();($('login').hidden?$('register'):$('login')).click()}});
 $('guestContinue').onclick=()=>{guest=true;confirmed=false;go(2)};
 $('previousStep').onclick=()=>{window.voiceConversation?.cancelPreview();go(step-1)};
 $('continueIdentity').onclick=()=>go(2);
 $('changeIdentity').onclick=async()=>{try{await api('/v1/logout','POST');leave()}catch(e){notify(e.message,true)}};
 $('confirmSetup').onclick=async()=>{
  if(advancing)return;
  // Consent is granted only by clicking the explicitly labelled action (or checkbox).
  const grantCloud=step===3&&needsCloudConsent()&&$('confirmSetup').textContent==='同意在线朗读并继续';
  advancing=true;$('confirmSetup').disabled=true;$('previousStep').disabled=true;feedback();updateNext();
  try{
   if(!token&&!guest){go(1);return}
   if(step===2){if(await saveUsage())go(3);return}
   if(step===3){await window.personalityController?.persist();if(needsCloudConsent()){if(!grantCloud){feedback('在线声音需要你的许可。请选择“同意在线朗读并继续”，或改用本地声音、文字交流。');return}$('cloudVoiceConsent').checked=true}confirmed=true;go(4);return}
   if(step===4){if(missingDevices().length){updateDeviceHint();feedback($('deviceHint').textContent);return}window.voiceConversation?.cancelPreview();enterWorkspace();if(isVoice())await window.voiceConversation.start()}
  }catch(e){const hint=step===2?'setupHint':step===3?'preferencesHint':'deviceHint';$(hint).textContent=e.message;feedback(e.message+' 请重试。')}finally{advancing=false;$('confirmSetup').disabled=false;$('previousStep').disabled=false;updateNext()}
 };
 $('testMic').onclick=async()=>{
  if(checking)return;checking=true;$('testMic').disabled=true;const run=++micEpoch;micReady=false;$('micCheckStatus').textContent='请在浏览器提示中允许麦克风…';
  let input=null;
  try{if(!navigator.mediaDevices?.getUserMedia)throw Error('当前浏览器不支持麦克风，请用本机 Edge 或 Chrome，或改用文字');input=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});if(run!==micEpoch)return;micTest=input;micReady=input.getAudioTracks().some(t=>t.readyState==='live');$('micCheckStatus').textContent=micReady?'麦克风已连接，进入对话后开始收音。':'没有可用的麦克风，请重新连接。'}
  catch(e){if(run===micEpoch)$('micCheckStatus').textContent=e.name==='NotAllowedError'?'麦克风权限未允许。请在地址栏的网站权限中允许后重试，或改用文字。':e.name==='NotFoundError'?'没有找到麦克风，请连接设备后重试，或改用文字。':e.name==='NotReadableError'?'麦克风被其他程序占用，请关闭占用后重试，或改用文字。':e.message}
  finally{input?.getTracks().forEach(t=>t.stop());if(run===micEpoch){micTest=null;checking=false;$('testMic').disabled=false;updateDeviceHint()}}
 };
 $('heardVoice').onclick=()=>{if(!previewPassed)return;speakerReady=true;$('speakerCheckStatus').textContent='声音已确认。';$('heardVoice').hidden=true;updateDeviceHint()};
 $('retryService').onclick=checkService;$('changeVoice').onclick=()=>{window.voiceConversation?.cancelPreview();go(3)};
 $('fallbackText').onclick=()=>{stopMicTest();window.voiceConversation?.cancelPreview();$('modeText').checked=true;updateDevices();$('confirmSetup').textContent='进入对话';void checkService()};
 $('skipCamera').onclick=()=>{$('cameraConsent').checked=false;stopCamera();updateDevices()};
 for(const id of ['modeVoice','modeText'])$(id).addEventListener('change',updateMode);
 $('chooseLocalVoice').onclick=()=>{$('voiceChoice').value='device';$('voiceChoice').dispatchEvent(new Event('change'));$('cloudVoiceConsent').checked=false;updateNext()};
 $('chooseTextMode').onclick=()=>{$('modeText').checked=true;updateMode()};
 for(const id of ['voiceChoice','voiceRate'])$(id).addEventListener('change',()=>{speakerReady=false;previewPassed=false;$('heardVoice').hidden=true;updateMode();$('preferencesHint').textContent=''});
 for(const id of ['consent','cameraConsent','cloudVoiceConsent'])$(id).addEventListener('change',()=>{confirmed=false;if(id==='cameraConsent'&&!$('cameraConsent').checked)stopCamera();if(id==='cloudVoiceConsent'){speakerReady=false;previewPassed=false}feedback();sync();updateNext()});
 $('openSettings').onclick=()=>{window.voiceConversation?.stop({keepCamera:true});showPage('settingsPage');$('closeSettings').textContent='返回对话';$('closeSettings').onclick=enterWorkspace;sync()};
 $('editUsage').onclick=()=>open(2);$('editDevices').onclick=()=>open(4);$('closeSettings').onclick=enterWorkspace;
 $('manageMemory').onclick=()=>{window.voiceConversation?.stop({keepCamera:true});showPage('memoryPage');renderMemory()};$('closeMemory').onclick=enterWorkspace;
 $('enableMemory').onclick=()=>token?open(2):reset();$('switchMember').onclick=()=>{clearConversation();reset()};
 $('toggleLiveCamera').onclick=async()=>{if(stream){stopCamera();return}if(!$('cameraConsent').checked){open(2);$('setupHint').textContent='勾选使用摄像头后，继续完成设备检查。';return}try{await startCamera()}catch(e){notify(e.message,true);open(4)}};
 $('speech').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('chatForm').requestSubmit()}});
 window.addEventListener('pagehide',stopMicTest);
 window.setupController={sync,signedIn,savedConsent,reset,open,require:requireSetup,renderMemory,
  ready(){if(!confirmed){requireSetup();return false}return true},
  memoryAllowed(){return !!token&&savedMemory&&$('consent').checked},cameraAllowed(){return confirmed&&$('cameraConsent').checked},cloudAllowed(){return confirmed&&$('cloudVoiceConsent').checked},
  previewResult(ok,message){previewPassed=ok;speakerReady=false;$('speakerCheckStatus').textContent=message;$('heardVoice').hidden=!ok;updateDeviceHint()},
  previewStarting(){$('speakerCheckStatus').textContent='正在试听…';$('heardVoice').hidden=true;previewPassed=false;speakerReady=false}
 };
 updateMode();go(1);
})();
