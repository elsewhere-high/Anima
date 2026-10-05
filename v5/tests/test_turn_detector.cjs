const assert=require('node:assert/strict');
const Detector=require('../web/turn_detector.js');
const speech=Array(8).fill(.95),silence=Array(8).fill(.01);
let d=new Detector();
assert.equal(d.update(speech,.256,'listening'),'start');
for(let i=0;i<6;i++)assert.equal(d.update(silence,.256,'listening'),'record');
assert.equal(d.update(speech,.256,'listening'),'record'); // 1.5s pause must not cut slow speaker
for(let i=0;i<7;i++)assert.equal(d.update(silence,.256,'listening'),'record');
assert.equal(d.update(silence,.256,'listening'),'end');
d=new Detector();assert.equal(d.update(speech,.256,'speaking'),'wait');
assert.equal(d.update(speech,.256,'speaking'),'interrupt');
d=new Detector();
for(let i=0;i<100;i++)assert.equal(d.update(Array(8).fill(.6),.256,'speaking'),'wait');
assert.equal(d.update(speech,.256,'thinking'),'wait');
d=new Detector({maxSeconds:1});d.update(speech,.256,'listening');d.update(speech,.256,'listening');d.update(speech,.256,'listening');
assert.equal(d.update(speech,.256,'listening'),'continue');
d=new Detector();for(let i=0;i<100;i++)assert.equal(d.update(silence,.256,'listening'),'wait');
console.log('turn detector: slow pauses, silence, interruption hysteresis, phase gate, bounded continuation passed');
