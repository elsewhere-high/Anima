import WebSocket from 'ws';
const origin='http://127.0.0.1:4827';
const {token}=await(await fetch(origin+'/api/status')).json();
const socket=new WebSocket(origin.replace('http','ws')+'/api/events',['anima',token],{origin});
socket.on('message',data=>{const event=JSON.parse(data);if(['state','quality','session.start','session.end'].includes(event.type))console.log(JSON.stringify(event));});
socket.on('error',()=>{console.error('无法订阅本机 Anima，请先启动应用。');process.exitCode=1;});
process.on('SIGINT',()=>socket.close());
