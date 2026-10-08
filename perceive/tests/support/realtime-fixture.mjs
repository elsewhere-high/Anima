import WebSocket,{WebSocketServer} from 'ws';
import {createApp} from '../../server.mjs';
import {normalizeFusion} from '../../fusion.mjs';

// Local protocol fixture. It never calls a cloud model or opens a physical device.
export async function realtimeFixture({realtimeOptions={},fusionDelay=80,fusionError}={}){
  const upstream=new WebSocketServer({port:0,host:'127.0.0.1'});await new Promise(resolve=>upstream.once('listening',resolve));
  const report={audioChunks:0,audioBytes:0,images:0,commits:0,responses:0,events:[],requests:[]};
  upstream.on('connection',socket=>{
    socket.send(JSON.stringify({type:'session.created',session:{id:'fixture'}}));
    socket.on('message',data=>{
      const event=JSON.parse(data);report.events.push(event.type);
      if(event.type==='session.update'){if(event.session.audio)report.session=event.session;else{try{report.meta=JSON.parse(event.session.instructions.split('本轮观察元数据：').at(-1));}catch{}}socket.send(JSON.stringify({type:'session.updated'}));}
      if(event.type==='input_audio_buffer.append'){report.audioChunks++;report.audioBytes+=Buffer.from(event.audio,'base64').length;}
      if(event.type==='input_image_buffer.append')report.images++;
      if(event.type==='input_audio_buffer.commit'){report.commits++;const item_id='item-'+report.commits;socket.send(JSON.stringify({type:'input_audio_buffer.committed',item_id}));socket.send(JSON.stringify({type:'conversation.item.input_audio_transcription.delta',item_id,text:'我拿不准这个数字',stash:''}));socket.send(JSON.stringify({type:'conversation.item.input_audio_transcription.completed',item_id,transcript:'我拿不准这个数字'}));}
      if(event.type==='conversation.item.create'){try{report.meta=JSON.parse(event.item.content[0].text);}catch{}}
      if(event.type==='response.create'){
        const id='response-'+(++report.responses);
        socket.send(JSON.stringify({type:'response.created',response:{id}}));
        const result={transcript:'我拿不准这个数字',segments:[],signals:[{label:'不确定',start:0,end:Math.min(2,report.meta?.duration||2),anchor:'拿不准',target:'数字',evidence:'原话表达把握不足',modalities:['语意'],tentative:true,confidence:.7}],scene:'',unknown:''};
        const text=JSON.stringify(result),split=text.indexOf(',');
        socket.send(JSON.stringify({type:'response.text.delta',response_id:id,delta:text.slice(0,split)}));
        setTimeout(()=>{if(socket.readyState!==WebSocket.OPEN)return;socket.send(JSON.stringify({type:'response.text.delta',response_id:id,delta:text.slice(split)}));socket.send(JSON.stringify({type:'response.text.done',response_id:id,text}));socket.send(JSON.stringify({type:'response.done',response:{id,status:'completed',output:[]}}));},80);
      }
    });
  });
  const app=createApp({realtimeOptions,fusionAnalyzer:async(input,config,signal,{onPartial})=>{report.fusionInputs??=[];report.fusionInputs.push(input);if(fusionError)throw fusionError;const raw={speakerBound:true,transcript:'我拿不准这个数字',observations:[{id:'o1',modality:'语意',text:'我拿不准这个数字',start:0,end:input.duration}],signals:[{label:'不确定',target:'数字',start:0,end:input.duration,refs:['o1'],evidence:'本人明确表示拿不准',scope:'current_self',basis:'explicit',confidence:.8,tentative:false}]};const result=normalizeFusion(raw,input);await new Promise(resolve=>setTimeout(resolve,fusionDelay));onPartial({...result,partial:true});return result;},config:{key:'fixture-only-key',workspace:'test-space'},upstreamFactory:(url,options)=>{
    report.requests.push({url,keyPresent:options.headers.Authorization==='Bearer fixture-only-key'});
    return new WebSocket(`ws://127.0.0.1:${upstream.address().port}`);
  }});
  await new Promise(resolve=>app.listen(0,'127.0.0.1',resolve));
  return {app,report,origin:`http://127.0.0.1:${app.address().port}`,close:async()=>{
    for(const socket of upstream.clients)socket.terminate();
    await Promise.all([new Promise(resolve=>upstream.close(resolve)),new Promise(resolve=>app.close(resolve))]);
  }};
}
