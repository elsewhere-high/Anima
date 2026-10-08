import test from 'node:test';
import assert from 'node:assert/strict';
import {speechDelivery} from '../speech-delivery.mjs';
import {LiveViewState} from '../public/live-state.js';
const observation={id:'s1',start:3,end:6,details:{}},quality={face:'single',speech:true,quiet:false};
const repetition={label:'repetition',start:1.9,end:2.2,meanScore:.8};
test('fast delivery keeps single fillers, unknown speakers and silent input out of mental-state labels',()=>{
  const r={quality:'ok',speechSpans:[repetition]};
  assert.equal(speechDelivery(r,observation,quality).signals[0].tentative,true);
  for(const q of [{...quality,face:'absent'},{...quality,face:'multiple'},{...quality,quiet:true},{...quality,speech:false}])assert.equal(speechDelivery(r,observation,q).signals.length,0);
  for(const s of [{...repetition,label:'filled_pause'},{...repetition,start:0,end:.2},{...repetition,end:4},{...repetition,start:2.15}])assert.equal(speechDelivery({...r,speechSpans:[s]},observation,quality).signals.length,0);
});
test('the live presentation merges duplicate states without promoting an acoustic estimate to confirmed',()=>{
  const view=new LiveViewState(),base={code:'hesitation',label:'犹豫',target:'',expiresAt:8};
  view.accept({type:'state',version:1,current:[{...base,id:'fast',tentative:true,source:'speech_delivery'},{...base,id:'confirmed',tentative:false,source:'fusion'}]});
  assert.deepEqual(view.view(5).signals.map(s=>s.id),['confirmed']);
  view.accept({type:'state',version:2,current:[{...base,id:'fast',tentative:true}]});
  assert.equal(view.view(5).signals[0].tentative,true);
});
test('sustained mid-utterance fillers require preceding speech; opening fillers and future activity cannot establish it',()=>{
  const r={quality:'ok',speechSpans:[{label:'filled_pause',start:1.9,end:2.25,meanScore:.9}]};
  assert.equal(speechDelivery(r,observation,quality,[{t:3,speaking:true}]).signals.length,1);
  assert.equal(speechDelivery(r,observation,quality,[{t:4.8,speaking:true}]).signals.length,0);
  assert.equal(speechDelivery(r,observation,quality,[{t:7,speaking:true}]).signals.length,0);
  assert.equal(speechDelivery(r,observation,quality,[{t:2,speaking:true},{t:3,speaking:false}]).signals.length,0);
});
