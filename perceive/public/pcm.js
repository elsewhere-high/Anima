// Stateful area-average resampling preserves sample counts across AudioWorklet blocks.
export class PcmEncoder{
  constructor(rate=48000,target=16000,size=1600){this.ratio=rate/target;this.size=size;this.bytes=new ArrayBuffer(size*2);this.view=new DataView(this.bytes);this.count=0;this.weight=0;this.sum=0;}
  push(samples){
    const output=[];
    for(const sample of samples){
      let remaining=1;
      while(remaining>1e-8){
        const take=Math.min(remaining,this.ratio-this.weight);this.sum+=sample*take;this.weight+=take;remaining-=take;
        if(this.weight>=this.ratio-1e-8){
          const value=Math.max(-1,Math.min(1,this.sum/this.ratio));this.view.setInt16(this.count++*2,Math.round(value<0?value*32768:value*32767),true);this.sum=0;this.weight=0;
          if(this.count===this.size){output.push(this.bytes);this.bytes=new ArrayBuffer(this.size*2);this.view=new DataView(this.bytes);this.count=0;}
        }
      }
    }
    return output;
  }
}
