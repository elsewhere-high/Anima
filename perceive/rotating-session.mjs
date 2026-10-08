// Bound native conversation history without interrupting an in-flight result.
// New connections warm from a short causal media buffer; no generated answers
// or reference labels are copied into the replacement conversation.
export class RotatingSession {
  constructor(factory,{rotationSeconds=30,overlapSeconds=3,onTrace=()=>{}}={}){
    this.factory=factory;this.rotationSeconds=rotationSeconds;this.overlapSeconds=overlapSeconds;this.onTrace=onTrace;
    this.closed=false;this.audio=[];this.frames=[];this.end=0;this.retryAt=0;this.serial=0;
    this.current=this.create();this.ready=this.current.session.ready;
  }
  create(){return {session:this.factory(),bornAt:this.end,ready:false,id:++this.serial};}
  pushAudio(pcm,start,end){
    if(this.closed)return;
    this.end=end;this.audio.push({pcm:Buffer.from(pcm),start,end});
    const cutoff=end-this.overlapSeconds;
    this.audio=this.audio.filter(a=>a.end>cutoff);this.frames=this.frames.filter(f=>f.t>=cutoff);
    this.current.session.pushAudio(pcm,start,end);
    if(this.next?.ready)this.next.session.pushAudio(pcm,start,end);
  }
  pushFrame(frame,t){
    if(this.closed)return;
    this.frames.push({frame,t});this.frames=this.frames.filter(f=>f.t>=this.end-this.overlapSeconds);
    this.current.session.pushFrame(frame,t);if(this.next?.ready)this.next.session.pushFrame(frame,t);
  }
  prepare(){
    if(this.closed||this.next||this.end<this.retryAt)return;
    const next=this.create();this.next=next;
    next.session.ready.then(()=>{
      if(this.closed||this.next!==next){next.session.close();return;}
      // Interleave images with their original audio timestamps. Replaying all
      // audio before all images would incorrectly move every frame to the end.
      const frames=this.frames.filter(f=>f.t<=this.end);let index=0;
      for(const chunk of this.audio){
        next.session.pushAudio(chunk.pcm,chunk.start,chunk.end);
        while(index<frames.length&&frames[index].t<=chunk.end){const f=frames[index++];next.session.pushFrame(f.frame,f.t);}
      }
      next.ready=true;next.bornAt=this.end;
      this.onTrace({type:'native_rotation_ready',at:this.end,connection:next.id,replayedSeconds:this.audio.length?this.end-this.audio[0].start:0});
    }).catch(()=>{
      next.session.close();if(this.next!==next)return;this.next=null;this.retryAt=this.end+10;
      this.onTrace({type:'native_rotation_failed',at:this.end});
    });
  }
  async analyze(input,config,signal,options){
    await this.ready;
    if(this.closed)throw new Error('原生状态连接已关闭');
    if(this.inFlight)throw new Error('原生状态请求尚未完成');
    if(this.next?.ready){
      const old=this.current;this.current=this.next;this.next=null;old.session.close();
      this.onTrace({type:'native_rotated',at:input.end,connection:this.current.id});
    }
    if(input.end-this.current.bornAt>=this.rotationSeconds)this.prepare();
    this.inFlight=true;
    try{return await this.current.session.analyze(input,config,signal,options);}
    finally{this.inFlight=false;}
  }
  close(){
    if(this.closed)return;this.closed=true;this.current.session.close();this.next?.session.close();this.next=null;this.audio=[];this.frames=[];
  }
}
