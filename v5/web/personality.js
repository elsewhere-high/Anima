'use strict';
(() => {
 let catalog=null, loading=null, loaded=false, saved=null, queue=Promise.resolve(), revision=0;
 const mbti=$('userMbti'), support=$('supportMode');
 function selection(){return {mbti:mbti.value||null,support:support.value}}
 function value(){return loaded?selection():undefined}
 function savedMbti(){return saved?.mbti||null}
 function persist(){
  if(!loaded||!window.setupController?.memoryAllowed())return Promise.resolve();
  const owner=token,selected=selection();
  queue=queue.catch(()=>{}).then(async()=>{
   if(token!==owner)return;
   if(JSON.stringify(saved)===JSON.stringify(selected))return;
   $('personalityReceipt').textContent='正在保存到你的成员档案…';
   await api('/v1/dialogue/preferences','PUT',selected);
   if(token!==owner)return;
   saved=selected;window.setupController?.renderMemory();
   if(JSON.stringify(selected)===JSON.stringify(selection()))$('personalityReceipt').textContent='已长期保存到你的成员档案，每次登录和对话都会沿用。';
  });
  return queue;
 }
 function render(){
  const selected=catalog?.types.find(t=>t.mbti===mbti.value);
  $('personalityHint').textContent=selected?selected.hints.join(' '):'不了解 MBTI 也没关系，直接选当下需要，或自然聊天。';
  $('openingPreview').textContent=selected?.opening||catalog?.default_opening||'你好，我在这里。想从什么聊起？';
  $('personalityState').textContent=`沟通偏好：${mbti.value||'暂不设定 MBTI'} · ${support.selectedOptions[0].textContent}`;
  $('savePersonality').disabled=!window.setupController?.memoryAllowed();
 }
 function changed(){
  revision++;loaded=true;render();
  $('personalityReceipt').textContent='当前选择已生效；未开启长期记忆时仅本次使用。';
  persist().catch(error=>{$('personalityReceipt').textContent='尚未保存：'+error.message+'。请点击重试保存。'});
 }
 function reset(){revision++;loaded=false;saved=null;mbti.value='';support.value='auto';$('personalityReceipt').textContent='可跳过；不会根据摄像头或聊天内容猜测你的类型。';render()}
 async function loadCatalog(){
  if(catalog)return;
  if(loading)return loading;
  loading=(async()=>{
   try{
    catalog=await api('/v1/dialogue/styles');
    const previous=mbti.value;
    mbti.replaceChildren(new Option('不了解 / 暂不设定',''));
    for(const t of catalog.types)mbti.add(new Option(t.mbti,t.mbti));
    mbti.value=previous;
    const group=$('starterChoices');group.replaceChildren();
    for(const scenario of catalog.scenarios){
     const button=document.createElement('button');button.type='button';button.textContent=scenario.label;
     button.onclick=()=>{$('speech').value=scenario.speech;$('speech').focus();$('chatState').textContent='已填入开场白，可以改写后发送。'};
     group.append(button);
    }
    $('retryPersonality').hidden=true;render();
   }catch(error){$('personalityReceipt').textContent='暂时无法加载类型和试聊话题，仍可直接聊天。'+error.message;$('retryPersonality').hidden=false}
   finally{loading=null}
  })();
  return loading;
 }
 async function signedIn(){
  reset();const owner=token,version=revision;
  await loadCatalog();
  try{
   const stored=await api('/v1/dialogue/preferences');
   if(token!==owner||revision!==version)return;
   saved=stored;loaded=true;
   if(saved.mbti&&![...mbti.options].some(o=>o.value===saved.mbti))mbti.add(new Option(saved.mbti,saved.mbti));
   mbti.value=saved.mbti||'';support.value=saved.support;render();window.setupController?.renderMemory();
   $('personalityReceipt').textContent=saved.mbti||saved.support!=='auto'?'已载入你的沟通偏好，可随时修改。':'尚未保存沟通偏好，可以跳过。';
  }catch(error){if(token===owner)$('personalityReceipt').textContent='未能载入已保存的偏好：'+error.message}
 }
 mbti.addEventListener('change',changed);support.addEventListener('change',changed);
 $('consent').addEventListener('change',render);
 $('retryPersonality').onclick=loadCatalog;
 $('savePersonality').onclick=async()=>{
  if(!loaded){await signedIn();return}
  $('savePersonality').disabled=true;
  try{await persist()}catch(error){$('personalityReceipt').textContent='尚未保存：'+error.message+'。请重试。'}finally{render()}
 };
 $('skipPersonality').onclick=()=>{mbti.value='';changed()};
 window.personalityController={value,reset,signedIn,render,loadCatalog,persist,savedMbti};
 render();loadCatalog();
})();
