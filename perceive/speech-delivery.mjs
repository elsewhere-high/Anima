// A fast, tentative speaking-pattern estimate from a published acoustic model.
// No claim about knowledge, sincerity, diagnosis, or a person's usual fluency.
// Only the two best-supported published classes (filled pauses/repetitions) are
// used for this tentative estimate. Repair/partial-word recognition is weaker.
// A filler must interrupt established speech; an opening filler is insufficient.
export function speechDelivery(result,observation,quality,activity=[]){
  if(result.quality!=='ok'||quality?.face!=='single'||quality?.quiet||quality?.speech===false)return {signals:[]};
  const duration=observation.end-observation.start;
  const recentActivity=activity.filter(a=>a.t<=observation.end).sort((a,b)=>a.t-b.t);
  const afterEstablishedSpeech=s=>{
    const onset=observation.start+s.start;let began=null;
    for(const a of [...recentActivity,{t:onset,speaking:false}]){
      if(a.t>onset)continue;
      if(a.speaking){began??=a.t;continue;}
      if(began!==null&&a.t-began>=.5&&onset-a.t<=1)return true;
      began=null;
    }
    return false;
  };
  const spans=(result.speechSpans||[]).filter(s=>
    s.meanScore>=.5&&
    Number.isFinite(s.start)&&Number.isFinite(s.end)&&s.start>=.04&&s.end<=duration&&
    duration-s.end<1.5&&
    (s.label==='repetition'&&s.end-s.start>=.12||s.label==='filled_pause'&&s.end-s.start>=.25&&afterEstablishedSpeech(s)));
  if(!spans.length)return {signals:[]};
  const start=Math.min(...spans.map(s=>s.start)),end=Math.max(...spans.map(s=>s.end));
  const labels={repetition:'重复',filled_pause:'话说到一半出现持续填充音'};
  const cue=[...new Set(spans.map(s=>labels[s.label]))].join('、');
  const local={...observation,start,end,text:`声音模型检测到${cue}；这是言语结构线索，不代表内心不确定`,details:{...observation.details,speechSpans:spans}};
  return {signals:[{code:'hesitation',label:'犹豫',family:'认知',start,end,confidence:.6,support:'low',tentative:true,
    source:'speech_delivery',scope:'current_self',basis:'acoustic_visual',target:'',anchor:'',
    evidence:`言语迟疑初步判断：${cue}。单一声学模型，分数未校准；尚未做跨模态确认。`,refs:[local.id],observations:[local],modalities:['声音']}]};
}
