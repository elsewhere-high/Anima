import test from 'node:test';
import assert from 'node:assert/strict';
import {intervalsFromSteps,overlap,compareEpisodes} from '../research/compare-timeline.mjs';
test('timeline counts actual visible overlap, not repeated updates or early labels as extra detections',()=>{
 const r=intervalsFromSteps([{at:2,codes:['confidence']},{at:3,codes:['confidence']},{at:5,codes:[]}],6);
 assert.deepEqual(r.get('confidence'),[[2,5]]);
 const c=intervalsFromSteps([{at:1,codes:['confidence']},{at:3,codes:[]},{at:4,codes:['confidence']}],6);
 assert.deepEqual(c.get('confidence'),[[1,3],[4,6]]);assert.equal(overlap(r.get('confidence'),c.get('confidence')),2);
});
test('timeliness requires an actually overlapping display, not an unrelated earlier appearance',()=>{
 const [earlyGone]=compareEpisodes([[2,4]],[[.5,1]]);assert.equal(earlyGone.timely,false);assert.equal(earlyGone.firstOverlappingDisplayAt,null);
 const [stillVisible]=compareEpisodes([[2,4]],[[1,3]]);assert.equal(stillVisible.timely,true);assert.equal(stillVisible.alreadyVisibleAtReferenceOnset,true);
 const [late]=compareEpisodes([[2,4]],[[2.6,3]]);assert.equal(late.timely,false);assert.equal(late.delayFromReferenceMs,600);
 const [ended]=compareEpisodes([[2,4]],[[4,5]]);assert.equal(ended.timely,false);
});
