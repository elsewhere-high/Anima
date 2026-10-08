// Captions and inferred states have independent lifetimes. ASR cannot erase states.
export class LiveViewState {
  constructor(){this.caption=null;this.states=[];this.summary='';this.version=0;this.blocked=false;}
  accept(event){
    if(event.type==='transcript'){
      const same=event.id&&event.id===this.caption?.id;
      if(same&&this.caption.provisional===false&&event.provisional)return;
      // The committed audio span can correct an earlier receipt-based draft
      // timestamp. Keep that same utterance's final text without reviving an
      // older, different utterance.
      if(!this.caption||same||event.end>=this.caption.end)this.caption=event;
    }
    if(event.type==='state'&&event.version>=this.version){this.version=event.version;this.states=this.blocked?[]:event.current;this.summary=event.summary;}
    if(event.type==='quality'&&event.quality?.face){this.blocked=event.quality.face!=='single';if(this.blocked)this.states=[];}
    if(event.type==='session.end'){this.states=[];}
  }
  view(now){
    const supported=this.blocked?[]:this.states.filter(s=>s.expiresAt>now);
    // Separate detectors can support the same state. Show it once, retaining
    // a confirmed judgment over a tentative acoustic proposal when both exist.
    const unique=new Map();
    for(const s of supported){const k=(s.code||s.label)+'|'+(s.target||''),old=unique.get(k);if(!old||old.tentative&&!s.tentative)unique.set(k,s);}
    const signals=[...unique.values()].slice(0,3);
    const text=this.caption&&now-this.caption.end<6?this.caption.text:'';
    // Never attach an old claim to words from a different evidence window.
    return {text,signals:signals.map(s=>({...s,anchor:this.caption&&this.caption.start<=s.end&&this.caption.end>=s.start?s.anchor:''})),summary:signals.length?this.summary:''};
  }
}

export function replayView(log,now){
  const view=new LiveViewState();
  for(const event of log)if(!event.afterStop&&event.receivedAt<=now)view.accept(event);
  return view.view(now);
}
