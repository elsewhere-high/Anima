import {SOCIAL_SIGNALS} from './signal-catalog.js';
export const labels=SOCIAL_SIGNALS;
import analyzed from './case-results.js';
export const cases = [
  {
    "id": "yann-lecun-wef",
    "name": "Yann LeCun",
    "duration": 6.934,
    "position": "center"
  },
  {
    "id": "steve-jobs-interview",
    "name": "Steve Jobs",
    "duration": 12.621,
    "position": "center"
  },
  {
    "id": "elon-musk-wef",
    "name": "Elon Musk",
    "duration": 4.013,
    "position": "center"
  },
  {
    "id": "pep-guardiola-press",
    "name": "Pep Guardiola",
    "duration": 5,
    "position": "center"
  },
  {
    "id": "mark-zuckerberg-interview",
    "name": "Mark Zuckerberg",
    "duration": 5.167,
    "position": "center"
  }
].map(c=>{
 const result=analyzed.results.find(r=>r.id===c.id);
 return {...c,source:'model_case',cues:result?[{start:0,end:c.duration,text:result.transcript,signals:result.signals.map(s=>({...s,source:'model_case',latencyMs:result.latencyMs}))}]:[]};
});
export const totalDuration=cases.reduce((s,c)=>s+c.duration,0);
export function locateTime(globalTime,list=cases){let offset=0;for(let i=0;i<list.length;i++){if(globalTime<offset+list[i].duration||i===list.length-1)return {index:i,time:Math.max(0,Math.min(list[i].duration,globalTime-offset)),offset};offset+=list[i].duration;}return {index:0,time:0,offset:0};}
