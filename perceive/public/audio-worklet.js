import {PcmEncoder} from './pcm.js';
class AnimaAudio extends AudioWorkletProcessor{
  constructor(){super();this.encoder=new PcmEncoder(sampleRate);}
  process(inputs){
    const channels=inputs[0];if(!channels?.length)return true;
    const mono=new Float32Array(channels[0].length);
    for(const channel of channels)for(let i=0;i<mono.length;i++)mono[i]+=channel[i]/channels.length;
    for(const bytes of this.encoder.push(mono))this.port.postMessage(bytes,[bytes]);
    return true;
  }
}
registerProcessor('anima-audio',AnimaAudio);
