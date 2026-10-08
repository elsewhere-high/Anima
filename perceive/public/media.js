export function encodeWav(samples,rate=16000){
  const bytes=new ArrayBuffer(44+samples.length*2),v=new DataView(bytes);
  const text=(at,s)=>[...s].forEach((c,i)=>v.setUint8(at+i,c.charCodeAt(0)));
  text(0,'RIFF');v.setUint32(4,bytes.byteLength-8,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,samples.length*2,true);
  samples.forEach((x,i)=>{const n=Math.max(-1,Math.min(1,x));v.setInt16(44+i*2,n<0?n*32768:n*32767,true)});return new Blob([bytes],{type:'audio/wav'});
}
export const toBase64=blob=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('无法读取声音'));reader.readAsDataURL(blob)});
export function flattenAudio(chunks,maxSamples=128000){
  const size=Math.min(maxSamples,chunks.reduce((n,c)=>n+c.length,0)),result=new Float32Array(size);let remaining=size,at=size;
  for(let i=chunks.length-1;i>=0&&remaining>0;i--){const chunk=chunks[i].subarray(Math.max(0,chunks[i].length-remaining));at-=chunk.length;result.set(chunk,at);remaining-=chunk.length;}return result;
}
export async function audioFromVideo(blob){
  const ctx=new AudioContext();let decoded;try{decoded=await ctx.decodeAudioData(await blob.arrayBuffer());}catch{throw new Error('视频音轨无法读取，请改用 MP4 或 WebM。');}finally{await ctx.close();}
  const offline=new OfflineAudioContext(1,Math.ceil(decoded.duration*16000),16000);const source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start();const rendered=await offline.startRendering();return rendered.getChannelData(0);
}
export function frameData(video,t){
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=Math.round(640*(video.videoHeight||480)/(video.videoWidth||640));const ctx=canvas.getContext('2d');ctx.drawImage(video,0,0,canvas.width,canvas.height);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;let light=0,count=0;for(let i=0;i<pixels.length;i+=128){light+=(pixels[i]+pixels[i+1]+pixels[i+2])/765;count++;}return {image:canvas.toDataURL('image/jpeg',.68).split(',')[1],t,brightness:light/count};
}
