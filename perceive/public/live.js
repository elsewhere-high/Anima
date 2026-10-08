export class LiveConnection{
  constructor(status,{onEvent=()=>{},onError=()=>{},offset=()=>0}={}){this.status=status;this.onEvent=onEvent;this.onError=onError;this.offset=offset;this.closed=false;this.sentAudio=false;}
  async connect(){
    const url=new URL('/api/realtime',location.href);url.protocol=location.protocol==='https:'?'wss:':'ws:';
    this.socket=new WebSocket(url,['anima',this.status.token]);
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{reject(new Error('实时连接超时，请检查网络和业务空间。'));this.close();},28000);
      this.socket.onmessage=({data})=>{
        let event;try{event=JSON.parse(data);}catch{return;}
        if(event.type==='ready'){this.ready=true;clearTimeout(timer);resolve();return;}
        if(event.type==='error'){
          const error=new Error(event.error||'实时连接失败');clearTimeout(timer);this.failed=true;
          if(!this.ready)reject(error);else this.onError(error);return;
        }
        this.onEvent(event);
      };
      this.socket.onerror=()=>{if(!this.ready){clearTimeout(timer);reject(new Error('实时连接失败，请检查百炼配置。'));}};
      this.socket.onclose=()=>{
        clearTimeout(timer);this.resolveFinish?.();
        if(!this.ready)reject(new Error(this.closed?'实验已结束':'实时连接失败，请检查百炼配置。'));
        else if(!this.closed&&!this.finishing&&!this.failed)this.onError(new Error('实时连接中断，请重新开始。'));
      };
    });
  }
  send(value){if(!this.closed&&this.socket?.readyState===WebSocket.OPEN)this.socket.send(JSON.stringify(value));}
  async startAudio(stream,{paused=false}={}){
    this.context=new AudioContext();await (paused?this.context.suspend():this.context.resume());await this.context.audioWorklet.addModule('/audio-worklet.js');
    if(this.closed){await this.context.close();return;}
    this.source=this.context.createMediaStreamSource(stream);
    this.node=new AudioWorkletNode(this.context,'anima-audio',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});
    this.silent=this.context.createGain();this.silent.gain.value=0;
    this.node.port.onmessage=({data})=>{
      if(this.closed||this.finishing||this.socket.readyState!==WebSocket.OPEN)return;
      if(this.socket.bufferedAmount>262144){this.onError(new Error('实时传输积压，请检查网络后重新开始。'));this.close();return;}
      if(!this.sentAudio){this.send({type:'start',offset:Math.max(0,this.offset()-.1)});this.sentAudio=true;}
      this.audioSamples=(this.audioSamples||0)+data.byteLength/2;
      this.socket.send(data);
    };
    this.source.connect(this.node);this.node.connect(this.silent);this.silent.connect(this.context.destination);
  }
  resumeAudio(){return this.context.resume();}
  image(frame){if(this.sentAudio)this.send({type:'image',image:frame.image,t:frame.t,brightness:frame.brightness});}
  face(value){this.send({type:'face',faces:value.faces,cues:value.cues,t:value.t});}
  commit(){this.send({type:'commit'});}
  stopAudio(){this.node?.disconnect();this.source?.disconnect();this.silent?.disconnect();this.context?.close().catch(()=>{});}
  async finish(){
    if(this.closed)return;this.finishing=true;this.stopAudio();
    if(this.socket?.readyState===WebSocket.OPEN){
      await new Promise(resolve=>{const timer=setTimeout(resolve,18000);this.resolveFinish=()=>{clearTimeout(timer);resolve();};this.send({type:'finish'});});
    }
    this.close();
  }
  close(){if(this.closed)return;this.closed=true;this.stopAudio();this.socket?.close();this.resolveFinish?.();}
}
