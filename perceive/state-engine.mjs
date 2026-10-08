const key=s=>(s.source||'fusion')+'|'+s.label+'|'+(s.target||'').replace(/[\s，。！？、]/g,'');
export class StateEngine {
  constructor(sessionId){this.sessionId=sessionId;this.version=0;this.serial=0;this.active=new Map();this.latest=new Map();this.history=new Map();}
  update(result,{start,end,now,windowId,latencyMs=0,lane='fusion',ttl=6}){
    const stale=end<(this.latest.get(lane)??-1)||now-end>=ttl;
    if(!stale)this.latest.set(lane,end);
    const changes=[],found=new Set();
    for(const signal of result.signals||[]){
      const k=key(signal);found.add(k);
      const absolute={...signal,start:start+signal.start,end:start+signal.end,observations:(signal.observations||[]).map(o=>({...o,start:start+o.start,end:start+o.end}))};
      const last=this.history.get(k),overlaps=last&&absolute.start<=last.end+.4&&absolute.end>=last.start;
      const previous=overlaps?last:null;
      const next={...absolute,id:previous?.id||`${this.sessionId}:${++this.serial}`,firstObservedAt:previous?.firstObservedAt??absolute.start,detectedAt:previous?.detectedAt??now,updatedAt:now,expiresAt:absolute.end+ttl,windowId,lane,latencyMs};
      // Late observations belong in the record; they cannot overwrite current state.
      if(stale||next.expiresAt<=now){
        if(!previous)changes.push({type:'observed',at:now,signal:next,reason:'片段已结束，保留识别记录'});
        if(!last||next.end>=last.end)this.history.set(k,next);
        continue;
      }
      this.active.set(k,next);this.history.set(k,next);
      changes.push({type:previous?'updated':'detected',at:now,signal:next});
    }
    if(!stale&&!result.partial)for(const [k,s]of this.active){
      if(s.lane!==lane)continue;
      if(!found.has(k)&&s.windowId===windowId){this.active.delete(k);this.history.delete(k);changes.push({type:'retracted',at:now,signal:s,reason:'最终结果修正初步判断'});}
      else if(!found.has(k)&&end>=s.end+Math.min(2,ttl)){this.active.delete(k);changes.push({type:'ended',at:now,signal:s,reason:'新窗口未再支持'});}
    }
    for(const [k,s]of this.history)if(now-s.end>60)this.history.delete(k);
    changes.push(...this.expire(now));
    const event=this.event(now,changes,stale?{}:{...result,behaviors:(result.behaviors||[]).map(b=>({...b,start:start+b.start,end:start+b.end}))});
    return {...event,historical:stale};
  }
  expire(now){const events=[];for(const [k,s]of this.active)if(s.expiresAt<=now){this.active.delete(k);events.push({type:'ended',at:now,signal:s,reason:'依据已过期'});}return events;}
  tick(now){const events=this.expire(now);return events.length?this.event(now,events):null;}
  clear(now,reason='会话结束',lane){const changes=[];for(const [k,signal]of this.active)if(!lane||signal.lane===lane){changes.push({type:'ended',at:now,signal,reason});this.active.delete(k);}return this.event(now,changes);}
  event(now,changes,result={}){
    // The UI limits presentation; the state stream keeps every supported state.
    const current=[...this.active.values()].sort((a,b)=>b.updatedAt-a.updatedAt||b.confidence-a.confidence);
    return {type:'state',sessionId:this.sessionId,version:++this.version,at:now,current,changes,summary:current.map(s=>`${s.target?`对${s.target}`:''}${s.label}${s.tentative?'（初步）':''}`).join('；'),unknown:result.unknown||'',unknownFamilies:result.unknownFamilies||[],behaviors:result.behaviors||[],consistency:result.consistency||[],quality:result.quality};
  }
}
