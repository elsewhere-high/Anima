// All times are media times. These measurements describe input, never emotions.
export function audioFeatures(pcm, sampleRate=16000) {
  let sum=0, peak=0, clipped=0;
  const n=pcm.length/2;
  for(let i=0;i<n;i++){const x=pcm.readInt16LE(i*2)/32768;sum+=x*x;peak=Math.max(peak,Math.abs(x));if(Math.abs(x)>.995)clipped++;}
  const rms=Math.sqrt(sum/Math.max(n,1));
  // Normalized autocorrelation: report pitch only for a sufficiently periodic signal.
  let pitchHz=null,periodicity=0;
  if(rms>.008&&n>=640){
    const count=Math.min(n,1600), step=2;
    for(let lag=40;lag<=267;lag+=step){let ab=0,aa=0,bb=0;
      for(let i=lag;i<count;i+=step){const a=pcm.readInt16LE(i*2),b=pcm.readInt16LE((i-lag)*2);ab+=a*b;aa+=a*a;bb+=b*b;}
      const corr=ab/Math.sqrt(aa*bb||1);if(corr>periodicity){periodicity=corr;pitchHz=Math.round(sampleRate/lag);}
    }
    if(periodicity<.65)pitchHz=null;
  }
  return {rmsDb:Math.round(20*Math.log10(Math.max(rms,1e-6))),peak:Math.round(peak*1000)/1000,clippedRatio:clipped/Math.max(1,n),pitchHz,periodicity:Math.round(periodicity*100)/100};
}

export function wavFromPcm(pcm){
  const h=Buffer.alloc(44);h.write('RIFF');h.writeUInt32LE(36+pcm.length,4);h.write('WAVEfmt ',8);h.writeUInt32LE(16,16);h.writeUInt16LE(1,20);h.writeUInt16LE(1,22);h.writeUInt32LE(16000,24);h.writeUInt32LE(32000,28);h.writeUInt16LE(2,32);h.writeUInt16LE(16,34);h.write('data',36);h.writeUInt32LE(pcm.length,40);return Buffer.concat([h,pcm]);
}
const median=values=>{const a=values.filter(Number.isFinite).sort((a,b)=>a-b);return a.length?a[Math.floor(a.length/2)]:null;};

export class EvidenceBuffer {
  constructor({windowSeconds=5,contextSeconds=45}={}){this.windowSeconds=windowSeconds;this.contextSeconds=contextSeconds;this.audio=[];this.frames=[];this.faces=[];this.specialists=[];this.transcripts=new Map();this.activity=[];this.end=0;}
  prune(){const min=this.end-this.contextSeconds;for(const key of ['audio','frames','faces','specialists'])this[key]=this[key].filter(x=>(x.end??x.t)>=min);for(const [id,t]of this.transcripts)if(t.end<min)this.transcripts.delete(id);
    // VAD emits transitions, not repeated samples. Preserve the last transition
    // before the retained window so a long utterance keeps its current state.
    const prior=this.activity.filter(a=>a.t<min).at(-1);
    this.activity=[...(prior?[prior]:[]),...this.activity.filter(a=>a.t>=min)];
  }
  pushAudio(pcm,start,end){this.end=end;this.audio.push({start,end,pcm:Buffer.from(pcm),features:audioFeatures(pcm)});this.prune();}
  pushFrame(image,t,quality={}){this.frames.push({image,t,quality});this.frames=this.frames.slice(-180);}
  pushSpecialist(observation){this.specialists.push(observation);this.specialists=this.specialists.slice(-200);this.prune();}
  pushFace(value,t){this.faces.push({...value,t});this.faces=this.faces.slice(-500);}
  transcript(event){if(event.text)this.transcripts.set(event.id,{id:event.id,start:event.start,end:event.end,transcript:event.confirmedText??event.text,provisional:event.provisional});this.prune();}
  snapshot({windowSeconds=this.windowSeconds,end=this.end}={}){
    end=Math.min(end,this.end);
    const start=Math.max(this.audio[0]?.start||0,end-windowSeconds),duration=end-start;
    const chunks=this.audio.filter(a=>a.end>start&&a.start<end).map(a=>{const from=Math.max(0,Math.round((start-a.start)*16000))*2,to=Math.min(a.pcm.length,Math.round((end-a.start)*16000)*2);return a.pcm.subarray(from,to);});
    const audio=chunks.length?{mimeType:'audio/wav',data:wavFromPcm(Buffer.concat(chunks)).toString('base64')}:null;
    const candidates=this.frames.filter(f=>f.t>=start&&f.t<=end);
    const frames=(candidates.length<=6?candidates:Array.from({length:6},(_,i)=>candidates[Math.round(i*(candidates.length-1)/5)])).map(f=>({...f,t:f.t-start}));
    const faces=this.faces.filter(f=>f.t>=start&&f.t<=end),measurements=this.audio.filter(a=>a.start>=start&&a.end<=end);
    const local=[];
    const add=(id,modality,text,details)=>local.push({id,modality,text,start:0,end:duration,source:'measurement',details});
    if(measurements.length){
      const db=measurements.map(a=>a.features.rmsDb),pitch=measurements.map(a=>a.features.pitchHz);
      add('a-level','声音',`音量中位数 ${median(db)} dBFS，范围 ${Math.min(...db)}～${Math.max(...db)} dBFS；设备自动增益可能影响比较`,{rmsDb:median(db),pitchHz:median(pitch),clippedRatio:median(measurements.map(a=>a.features.clippedRatio))});
      if(pitch.filter(Number.isFinite).length>=3)add('a-pitch','声音',`周期性声音基频中位数约 ${median(pitch)} Hz（非情绪判断）`,{pitchHz:median(pitch)});
    }
    if(faces.length){
      const single=faces.filter(f=>f.faces===1),names=[...new Set(single.flatMap(f=>f.cues.map(c=>c.name)))];
      for(const [i,name]of names.entries()){
        const values=single.map(f=>f.cues.find(c=>c.name===name)?.coefficient).filter(Number.isFinite);
        const max=Math.max(...values),min=Math.min(...values);
        const delta=values.at(-1)-values[0];
        if(max>.32)add(`f-${i}`,'画面',`${name}动作系数 ${min.toFixed(2)}～${max.toFixed(2)}，窗口首尾变化 ${delta.toFixed(2)}；不等于心理状态`,{min,max,delta,samples:values.length});
      }
    }
    const latestFace=faces.at(-1),faceFresh=latestFace&&end-latestFace.t<1.5;
    const current=this.transcripts.values();
    const context=[...current].filter(t=>!t.provisional&&t.end>=end-this.contextSeconds&&t.end<start).slice(-12);
    const transcript=[...this.transcripts.values()].filter(t=>t.end>=start&&t.start<=end).map(t=>t.transcript).join(' ').slice(-500);
    const speech=this.activity.filter(a=>a.t>=start&&a.t<=end).slice(-12);
    const quality={audio:!!audio,video:frames.length>0,face:faceFresh?(latestFace.faces===1?'single':latestFace.faces>1?'multiple':'absent'):'unavailable',faceSamples:faces.length,clipping:measurements.some(a=>a.features.clippedRatio>.08),dark:frames.length>0&&frames.every(f=>Number.isFinite(f.quality?.brightness)&&f.quality.brightness<.06),speech:this.activity.filter(a=>a.t<=end).at(-1)?.speaking??null};
    quality.quiet=measurements.length>0&&measurements.every(a=>a.features.rmsDb< -55);
    const specialist=this.specialists.filter(o=>o.end>start&&o.end<=end).slice(-12).map(o=>{
      const relative={...o,start:Math.max(0,o.start-start),end:o.end-start};
      // Event spans belong to the specialist's original audio window. Shift
      // before clipping; clipping the parent start first would move old cues.
      if(o.details?.speechSpans)relative.details={...o.details,speechSpans:o.details.speechSpans
        .map(s=>({...s,start:s.start+o.start-start,end:s.end+o.start-start}))
        .filter(s=>s.end>0&&s.start<duration)
        .map(s=>({...s,start:Math.max(0,s.start),end:Math.min(duration,s.end)}))};
      return relative;
    });
    return {start,end,duration,audio,frames,face:faces.filter((_,i)=>i%Math.max(1,Math.ceil(faces.length/12))===0).map(f=>({...f,t:f.t-start})),context,transcript,local:[...specialist,...local.slice(0,10)],quality,speech};
  }
  clear(){this.audio=[];this.frames=[];this.faces=[];this.specialists=[];this.transcripts.clear();this.activity=[];}
}

export function reviewEvidence(input){
  const buffer=new EvidenceBuffer(),start=Number(input.start)||0;
  if(input.audio?.mimeType==='audio/wav'){
    const bytes=Buffer.from(input.audio.data,'base64');
    if(bytes.length>=44&&bytes.toString('ascii',0,4)==='RIFF'&&bytes.toString('ascii',36,40)==='data'&&bytes.readUInt16LE(20)===1&&bytes.readUInt16LE(22)===1&&bytes.readUInt32LE(24)===16000&&bytes.readUInt16LE(34)===16){
      for(let i=44;i+1<bytes.length;i+=3200){const chunk=bytes.subarray(i,Math.min(i+3200,bytes.length));buffer.pushAudio(chunk,(i-44)/32000,(i-44+chunk.length)/32000);}
    }
  }
  buffer.end=input.duration;
  for(const frame of input.frames)buffer.pushFrame(frame.image,frame.t,frame.quality);
  for(const face of input.face)buffer.pushFace(face,face.t);
  const value=buffer.snapshot({windowSeconds:input.duration});
  return {...input,context:input.context.filter(c=>c.end>0&&c.end<=start&&c.end>=start-45),start,end:start+input.duration,local:value.local,quality:{...value.quality,audio:!!input.audio,quiet:input.audio?.mimeType==='audio/wav'?value.quality.quiet:false},transcript:input.transcript||''};
}
