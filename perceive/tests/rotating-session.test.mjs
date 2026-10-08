import test from 'node:test';
import assert from 'node:assert/strict';
import {RotatingSession} from '../rotating-session.mjs';

function fixture(){
 const sessions=[];
 const factory=()=>{let resolve,reject;const s={ready:new Promise((a,b)=>{resolve=a;reject=b;}),resolve:()=>resolve(),reject:()=>reject(Error('fixture')),media:[],requests:[],closeCount:0,pushAudio(pcm,start,end){this.media.push({type:'audio',start,end});},pushFrame(frame,t){this.media.push({type:'image',t});},async analyze(input){this.requests.push(input);return {signals:[]};},close(){this.closeCount++;}};sessions.push(s);return s;};
 return {sessions,stream:new RotatingSession(factory,{rotationSeconds:2,overlapSeconds:1})};
}
test('rotation replays only recent causal media, preserves order and switches between requests',async()=>{
 const {sessions,stream}=fixture();sessions[0].resolve();await stream.ready;
 for(let i=0;i<20;i++){stream.pushAudio(Buffer.alloc(3200),i/10,(i+1)/10);if(i%5===4)stream.pushFrame({image:'test'},(i+1)/10);}
 await stream.analyze({end:2});assert.equal(sessions.length,2);assert.equal(sessions[0].closeCount,0);
 sessions[1].resolve();await Promise.resolve();
 const media=sessions[1].media;assert.ok(media.filter(e=>e.type==='audio').every(e=>e.start>=1));
 for(const [i,e]of media.entries())if(e.type==='image')assert.ok(media.slice(0,i).some(a=>a.type==='audio'&&a.end>=e.t));
 stream.pushAudio(Buffer.alloc(3200),2,2.1);await stream.analyze({end:2.1});
 assert.equal(sessions[0].closeCount,1);assert.equal(sessions[1].requests.length,1);
 stream.close();stream.close();assert.equal(sessions[1].closeCount,1);assert.equal(stream.audio.length,0);
});
test('replacement connection failure preserves active inference and cleanup',async()=>{
 const {sessions,stream}=fixture();sessions[0].resolve();await stream.ready;stream.pushAudio(Buffer.alloc(3200),1.9,2);
 await stream.analyze({end:2});sessions[1].reject();await Promise.resolve();await Promise.resolve();
 await stream.analyze({end:2.1});assert.equal(sessions[0].requests.length,2);assert.equal(sessions[0].closeCount,0);assert.equal(sessions.length,2);
 stream.close();assert.equal(sessions[0].closeCount,1);
});
