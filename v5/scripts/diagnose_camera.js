async page => {
 await page.context().grantPermissions(['camera','microphone']);
 return await page.evaluate(async()=>{
 const devices=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput').map(d=>({id:d.deviceId,label:d.label}));
 const attempts=[];
 for(const video of [{width:{ideal:960},height:{ideal:720}},{width:{exact:640},height:{exact:480}},true]){
  try {const s=await navigator.mediaDevices.getUserMedia({video,audio:false});const settings=s.getVideoTracks()[0].getSettings();s.getTracks().forEach(t=>t.stop());attempts.push({video,ok:true,settings});}
  catch(e){attempts.push({video,ok:false,name:e.name,message:e.message})}
 }
 return {devices,attempts};
 });
}