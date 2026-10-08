// At most two in flight. Always take recent media; never build an unbounded queue.
export class WindowScheduler {
  constructor({hop=.8,concurrency=2,firstEnd=hop}={}){this.hop=hop;this.concurrency=concurrency;this.firstEnd=firstEnd;this.running=new Map();this.lastEnd=0;this.serial=0;}
  reserve(end,{force=false}={}){
    if(this.running.size>=this.concurrency||end-this.lastEnd<(force ? .3 : this.serial===0?this.firstEnd:this.hop)||end<.4)return null;
    const request={id:++this.serial,end,controller:new AbortController()};this.lastEnd=end;this.running.set(request.id,request);return request;
  }
  complete(id){this.running.delete(id);}
  close(){for(const r of this.running.values())r.controller.abort();this.running.clear();}
}
