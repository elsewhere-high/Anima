'use strict';
(() => {
 let current=null,seen=new Set(),polling=false,owner='',settingsOwner='',requestId=null;
 const $c=id=>document.getElementById(id);
 const careApi=(path,method,data)=>api(path,method,data,12000);
 const failure=e=>{message(e.message);notify(e.message,true)};
 const message=text=>$c('careStatus').textContent=text;
 function clear(){current=null;seen.clear();owner=token;$c('careNotice').hidden=true;$c('careItems').replaceChildren();settingsOwner='';requestId=null}
 async function load(){
  if(!token){message('请先登录成员，并开启长期记忆。');return}
  const selected=token;
  try{
   const [prefs,items]=await Promise.all([careApi('/v1/care/settings'),careApi('/v1/care/reminders')]);if(selected!==token)return;
   if(settingsOwner!==selected){$c('careProactive').checked=prefs.proactive_enabled;$c('careInterval').value=prefs.interval_minutes;$c('careQuietStart').value=prefs.quiet_start;$c('careQuietEnd').value=prefs.quiet_end;settingsOwner=selected}
   const list=$c('careItems');list.replaceChildren();
   if(!items.length){const p=document.createElement('p');p.className='muted';p.textContent='还没有待办提醒。也可以直接说“五分钟后提醒我给花浇水”。';list.append(p)}
   for(const item of items){
    const row=document.createElement('div');row.className='care-item';const p=document.createElement('p');p.textContent=item.text;const small=document.createElement('small');small.textContent=new Date(item.due_unix*1000).toLocaleString('zh-CN')+(item.repeat_seconds?' · 每 24 小时重复':'')+(item.overdue_seconds?' · 已到期，尚未确认':'');
    const cancel=document.createElement('button');cancel.textContent='取消提醒';cancel.onclick=()=>resolve(item,'cancel').catch(failure);row.append(p,small,cancel);list.append(row)
   }
   message(window.setupController.memoryAllowed()?'提醒会保存在本机。需要服务和接收页面保持运行；用药提醒请按既定医嘱填写。':'长期记忆未开启，暂时不能保存提醒或陪护设置。');
  }catch(e){message('加载失败：'+e.message)}
 }
 async function resolve(item,action){
  const selected=token;await careApi(`/v1/care/reminders/${item.id}/resolve`,'POST',{action,occurrence:item.occurrence,minutes:10});if(selected!==token)return;
  seen.delete(item.occurrence);if(current?.occurrence===item.occurrence){current=null;$c('careNotice').hidden=true}await load();void poll();
 }
 async function poll(){
  if(owner!==token)clear();if(!token||polling||document.hidden)return;
  const selected=token;polling=true;
  try{
   const workspace=!$c('workspace').hidden;
   // Presence is unknown without a fresh single-face result. No automatic audio.
   const present=workspace&&!!lastFrame&&Date.now()-frameAt<5000&&$c('latency').textContent.includes('1 张人脸');
   const out=await careApi('/v1/care/poll','POST',{person_present:present,interaction_busy:chatBusy||!!window.voiceConversation?.active||!workspace});if(selected!==token)return;
   if(current&& !out.reminders.some(x=>x.occurrence===current.occurrence)){current=null;$c('careNotice').hidden=true}
   if(!workspace||current)return;
   const item=out.reminders.find(x=>!seen.has(x.occurrence));
   if(item){current=item;seen.add(item.occurrence);$c('careNoticeText').textContent='提醒：'+item.text+(item.kind==='medication'?'（请按既定医嘱核对；点击确认不代表已服药）':'');$c('careAck').hidden=false;$c('careSnooze').hidden=false;$c('careNotice').hidden=false}
   else if(out.check_in){$c('careNoticeText').textContent=out.check_in.text;$c('careAck').hidden=true;$c('careSnooze').hidden=true;$c('careNotice').hidden=false}
  }catch(e){if(selected===token&&e.status===401){$c('careNoticeText').textContent='登录已过期，提醒暂时无法读取。请重新登录。';$c('careAck').hidden=true;$c('careSnooze').hidden=true;$c('careNotice').hidden=false}}
  finally{polling=false}
 }
 $c('openCare').onclick=()=>{void load()};
 $c('careRefresh').onclick=load;
 $c('careSaveSettings').onclick=async()=>{
  const button=$c('careSaveSettings');button.disabled=true;
  try{await careApi('/v1/care/settings','PUT',{proactive_enabled:$c('careProactive').checked,interval_minutes:Number($c('careInterval').value),quiet_start:Number($c('careQuietStart').value),quiet_end:Number($c('careQuietEnd').value),utc_offset_minutes:-new Date().getTimezoneOffset()});message('陪护偏好已保存。主动关怀只在确认有人、闲暇且不在安静时段时显示。')}
  catch(e){message(e.message)}finally{button.disabled=false}
 };
 $c('careAdd').onclick=async()=>{
  const button=$c('careAdd');button.disabled=true;
  try{
   const text=$c('careText').value.trim(),due=$c('careTime').value;if(!text||!due)throw Error('请填写提醒内容和时间');
   const date=new Date(due);if(!Number.isFinite(date.getTime())||date<=new Date())throw Error('请选择未来的提醒时间');
   requestId=requestId||crypto.randomUUID();await careApi('/v1/care/reminders','POST',{text,due_at:date.toISOString(),request_id:requestId,repeat:$c('careRepeat').value,kind:$c('careKind').value});requestId=null;$c('careText').value='';await load();message('提醒已保存，可以在下方查看或取消。')
  }catch(e){message(e.message)}finally{button.disabled=false}
 };
 for(const id of ['careText','careTime','careRepeat','careKind'])$c(id).addEventListener('input',()=>requestId=null);
 $c('careAck').onclick=()=>{if(current)void resolve(current,'ack').catch(failure)};
 $c('careSnooze').onclick=()=>{if(current)void resolve(current,'snooze').catch(failure)};
 $c('careDismiss').onclick=()=>{current=null;$c('careNotice').hidden=true};
 const timer=setInterval(poll,5000);window.addEventListener('pagehide',()=>clearInterval(timer));window.careController={load,poll,clear};
})();
