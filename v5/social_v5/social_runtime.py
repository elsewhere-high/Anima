"""Sensor orchestration with owner-bound references and independent perception lanes."""
import secrets, threading, time
from .body import BodyEncoder
from .human_state import HumanState
from .profiles import select_profile
from .scheduler import PerceptionScheduler, BusyError
from .temporal import HumanStateBuffer
from .vision import decode_image

class SocialRuntime:
    def __init__(self,memory,vision):
        self.profile=select_profile();self.memory=memory;self.vision=vision
        self.buffer=HumanStateBuffer(memory);self.scheduler=PerceptionScheduler();self.body=BodyEncoder()
        self.geometry=None
        if self.profile.name in {'balanced','best_edge'}:
            from .face_geometry import FaceGeometry
            self.geometry=FaceGeometry()
        self.lock=threading.RLock();self.audio_refs={};self.sampling={};self.owners={}
    def close(self):
        self.scheduler.close();self.body.close()
        if self.geometry:self.geometry.close()
    def _consent(self,uid):
        p=self.memory.profile(uid) if uid else None
        return bool(p and p['memory_consent'])
    def _track(self,owner,uid):
        with self.lock:
            now=time.monotonic();self.owners={k:v for k,v in self.owners.items() if now-v[1]<3600}
            if len(self.owners)>=512:self.owners.pop(next(iter(self.owners)))
            self.owners[owner]=(uid,now)
    def clear(self,uid=None,owner=None):
        with self.lock:
            owners=[owner] if owner else [k for k,v in self.owners.items() if v[0]==uid]
            for o in owners:
                self.buffer.clear(o);self.owners.pop(o,None)
                self.audio_refs={k:v for k,v in self.audio_refs.items() if v['owner']!=o}
                self.sampling={k:v for k,v in self.sampling.items() if k[0]!=o}
    def visual(self,encoded,owner,session,uid=None):
        self._track(owner,uid);key=(owner,session);now=time.monotonic()
        with self.lock:
            self.sampling={k:v for k,v in self.sampling.items() if now-v['time']<10}
            if len(self.sampling)>=128:self.sampling.pop(next(iter(self.sampling)))
            old=self.sampling.get(key)
            interval=old['interval'] if old else self.profile.visual_interval
            if old and old.get('active_until',0)>now:interval=self.profile.active_interval
            if old and now-old['time']<interval:
                out=dict(old['result']);out['sampling']={'cached':True,'next_sample_ms':round(1000*(interval-(now-old['time'])))};return out
        def face_work():
            visual=self.vision.analyze(encoded,key,owner)
            if self.geometry and len(visual['faces'])==1 and 'social_signal' in visual['faces'][0]:
                visual['faces'][0]['social_signal'].update(self.geometry.analyze(decode_image(encoded)))
            return visual
        face_future=self.scheduler.submit('face',face_work)
        body_future=None
        if not old or now-old.get('body_at',0)>=self.profile.body_interval:
            try:body_future=self.scheduler.submit('body',lambda:self.body.analyze(decode_image(encoded),key))
            except BusyError:pass
        visual=face_future.result();body=body_future.result() if body_future else None
        faces=visual['faces'];face={'source':'no_unique_usable_face','confidence':0}
        # A frame with multiple faces/bodies cannot silently become the logged-in user.
        binding=True;candidate=None
        if len(faces)==1:
            candidate=faces[0]['identity'].get('candidate_user_id')
            binding=not candidate or candidate==uid
            if binding:
                face=dict(faces[0].get('social_signal',face))
                face['_tracking_continuous']=faces[0].get('expression',{}).get('frames_smoothed',0)>1
        if len(faces)>1 or not binding:
            body={'source':'ambiguous_person_binding','confidence':0};self.buffer.clear(owner)
        # Login alone does not identify the person in front of a shared camera.
        state=self.buffer.update(key,face=face,body=body,uid=uid,consent=self._consent(uid) and bool(uid) and candidate==uid)
        active=state.event!='stable_or_insufficient_evidence' or bool(body and body.get('sudden_posture_change')) or bool(old and old.get('active_until',0)>now)
        out={**visual,'human_state':state.model_dump(),'sampling':{'cached':False,'next_sample_ms':round(1000*(self.profile.active_interval if active else self.profile.visual_interval))}}
        with self.lock:self.sampling[key]={'time':now,'body_at':now if body_future else old.get('body_at',0) if old else 0,'interval':out['sampling']['next_sample_ms']/1000,'active_until':old.get('active_until',0) if old else 0,'result':out}
        return out
    def audio(self,encoded,owner,session,uid=None):
        from .voice import transcribe
        self._track(owner,uid)
        result=self.scheduler.submit('audio',transcribe,encoded).result();now=time.monotonic()
        state=self.buffer.update((owner,session),voice=result['voice'],uid=uid,consent=self._consent(uid))
        ref=secrets.token_urlsafe(18)
        with self.lock:
            if (owner,session) in self.sampling and (result['voice'].get('voice_activity',0)>.1 or result['voice'].get('audio_events')):
                self.sampling[(owner,session)]['active_until']=now+4
            self.audio_refs={k:v for k,v in self.audio_refs.items() if now-v['time']<30}
            if len(self.audio_refs)>=128:self.audio_refs.pop(next(iter(self.audio_refs)))
            self.audio_refs[ref]={'owner':owner,'session':session,'time':now,'result':result}
        return {**result,'audio_frame_id':ref,'human_state':state.model_dump()}
    def state(self,owner,session,text='',uid=None,audio_ref=None):
        if audio_ref:
            with self.lock:
                row=self.audio_refs.get(audio_ref)
                if not row or row['owner']!=owner or row['session']!=session or time.monotonic()-row['time']>30:raise ValueError('语音线索已过期或不属于当前会话')
        self._track(owner,uid)
        if uid and text and self._consent(uid):self.memory.observe_communication_feedback(uid,text)
        return self.buffer.update((owner,session),text=text,uid=uid,consent=self._consent(uid))
