/* Pure turn state machine. VAD confidence means speech presence, not correctness. */
(function(root){
 class TurnDetector{
  constructor({pauseSeconds=2,maxSeconds=20}={}){this.pauseSeconds=pauseSeconds;this.maxSeconds=maxSeconds;this.reset()}
  reset(){this.recording=false;this.voice=0;this.quiet=0;this.total=0;this.barge=0}
  update(probabilities,seconds,phase){
   if(phase==='speaking'){
    for(const p of probabilities)this.barge=p>=.8?this.barge+.032:0;
    if(this.barge>=.384){this.barge=0;return 'interrupt'}
    return 'wait';
   }
   this.barge=0;
   if(phase!=='listening')return 'wait';
   const speech=probabilities.some(p=>p>=.55),activity=probabilities.filter(p=>p>=.4).length*.032;
   if(!this.recording){
    this.voice=speech?this.voice+activity:0;
    if(this.voice>=.128){this.recording=true;this.total=seconds;this.quiet=0;return 'start'}
    return 'wait';
   }
   this.total+=seconds;
   if(activity>0){this.voice+=activity;this.quiet=0}else this.quiet+=seconds;
   if(this.quiet>=this.pauseSeconds){this.reset();return 'end'}
   if(this.total>=this.maxSeconds){this.reset();return 'continue'}
   return 'record';
  }
 }
 if(typeof module!=='undefined'&&module.exports)module.exports=TurnDetector;else root.TurnDetector=TurnDetector;
})(typeof window!=='undefined'?window:globalThis);
