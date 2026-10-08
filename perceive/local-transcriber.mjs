// Causal rolling transcription. Each utterance keeps one ID so corrections
// replace its draft instead of duplicating text. The worker receives only PCM
// already captured; neither stored transcripts nor reference answers enter it.
export class LocalTranscriber {
  constructor({snapshot,infer,onTranscript,onError=()=>{},hop=.8,maxSeconds=12}){
    Object.assign(this,{snapshot,infer,onTranscript,onError,hop,maxSeconds});
    this.queue=[];this.serial=0;this.committedEnd=0;this.closed=false;this.pending=null;
  }
  activity(speaking,at){
    if(this.closed)return;
    if(speaking&&!this.active){
      if(this.queue.length>=3){this.onError(new Error('local_asr_backlog'));return;}
      const start=Math.max(this.committedEnd,at-.6,0);
      this.active={id:`local-asr-${++this.serial}`,start,end:at,lastEnd:start,final:false};
      this.queue.push(this.active);
    }else if(!speaking&&this.active){
      this.active.end=at;this.active.final=true;this.committedEnd=at;this.active=null;
    }
  }
  tick(at){
    if(this.closed)return;
    if(this.active){
      this.active.end=at;
      if(at-this.active.start>=this.maxSeconds){this.activity(false,at);this.activity(true,at);}
    }
    if(this.pending)return;
    const item=this.queue[0];if(!item)return;
    if(item.end-item.start<.3){if(item.final)this.queue.shift();return;}
    if(!item.final&&item.end-item.lastEnd<this.hop)return;
    const end=item.end,final=item.final,input=this.snapshot({end,windowSeconds:end-item.start});
    item.lastEnd=end;
    this.pending=Promise.resolve().then(()=>this.infer(input)).then(result=>{
      if(this.closed)return;
      const text=String(result.transcript||'').trim().slice(0,1000);
      if(text)this.onTranscript({type:'transcript',id:item.id,text,start:item.start,end,provisional:!final,source:result.model||'local_asr'});
    }).catch(error=>{if(!this.closed)this.onError(error);}).finally(()=>{
      if(final&&this.queue[0]===item)this.queue.shift();
      this.pending=null;
    });
  }
  async finish(at){
    this.activity(false,at);
    // A finite drain: at most the retained utterances plus the in-flight draft.
    for(let count=0;count<8&&this.queue.length&&!this.closed;count++){
      this.tick(at);if(this.pending)await this.pending;else if(this.queue.length)break;
    }
  }
  close(){this.closed=true;this.queue=[];this.active=null;}
}
