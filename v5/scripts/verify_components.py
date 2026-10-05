"""Actual CPU vision + embedding checks on public fixtures, not accuracy claims."""
import base64,hashlib,json,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import cv2,numpy as np
from social_v5.memory import MemoryStore
from social_v5.vision import Vision
from social_v5.embedding import Embedding

def enc(image):return base64.b64encode(cv2.imencode('.jpg',image)[1]).decode()

def main():
    start=time.monotonic(); results={}
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp);embedding=Embedding();memory=MemoryStore(p/'test.db',p/'key',embedding)
        vision=Vision(memory)
        raw=(ROOT/'tests/assets/astronaut.png').read_bytes();image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        frames=[enc(image),enc(cv2.convertScaleAbs(image,alpha=.97,beta=2)),enc(cv2.convertScaleAbs(image,alpha=1.03,beta=-2))]
        first=vision.analyze(frames[0],'fixture','owner');results['face_before_enrollment']=first
        assert len(first['faces'])==1,first
        assert first['faces'][0]['quality']['usable'],first
        assert first['faces'][0]['expression']['distribution']
        memory.register('fixture','public_fixture','fixture-pin',False)
        results['enroll']=vision.enroll('fixture',frames)
        results['face_after_enrollment']=vision.analyze(frames[1],'fixture','owner')
        assert results['face_after_enrollment']['faces'][0]['identity']['candidate_user_id']=='fixture'
        assert not results['face_after_enrollment']['faces'][0]['identity']['identity_verified']
        assert results['face_after_enrollment']['faces'][0]['expression']['frames_smoothed']>=2
        try:vision.frame(first['frame_id'],'other');raise AssertionError('Frame owner bypass')
        except ValueError:results['wrong_frame_owner_rejected']=True
        try:vision.enroll('fixture',[frames[0]]*3);raise AssertionError('duplicate accepted')
        except ValueError:results['duplicate_enrollment_rejected']=True
        results['blank']=vision.analyze(enc(np.zeros((320,320,3),np.uint8)),'blank')
        assert results['blank']['status']=='no_face'
        results['two_faces']=vision.analyze(enc(np.concatenate([image,image],axis=1)),'multiple')
        assert len(results['two_faces']['faces'])==2
        vision.memory.delete_face('fixture')
        assert vision.analyze(frames[0],'deleted')['faces'][0]['identity']['status']=='no_registered_members'
        results['biometric_delete_verified']=True
        memory.put('a','preference','闲暇活动','我喜欢在阳台养兰花，每天给花浇水。')
        memory.put('a','fact','位置','公交卡在门口抽屉。')
        memory.put('a','preference','运动','我每周游泳两次。')
        rows=memory.search('a','有什么适合我的园艺活动？')
        results['semantic_query']=[{'text':r['text'],'kind':r['kind']} for r in rows]
        assert rows and '兰花' in rows[0]['text'],rows
        assert not any('_embedding' in r for r in rows)
        memory.db.close()
    results.update(elapsed_seconds=time.monotonic()-start,fixture='scikit-image v0.19.3 astronaut.png, NASA public domain; temporary fixture identity only',fixture_sha256=hashlib.sha256(raw).hexdigest(),scope='engineering smoke test, NOT face/emotion accuracy or liveness validation',passed=True)
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/components.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'elapsed_seconds':results['elapsed_seconds'],'vision_latency_ms':results['face_after_enrollment']['latency_ms'],'expression':results['face_after_enrollment']['faces'][0]['expression'],'semantic_query':results['semantic_query']},ensure_ascii=False))

if __name__=='__main__':main()
