"""MediaPipe Lite 33-point pose + image-plane kinematics, not a body emotion model."""
import math, threading, time
import numpy as np
import cv2
from . import ROOT

class BodyEncoder:
    def __init__(self):
        import mediapipe as mp
        from .assets import checked_asset
        self.mp=mp;self.lock=threading.Lock();self.history={}
        options=mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=checked_asset('social/pose_landmarker_lite.task').read_bytes()),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,num_poses=2,
            min_pose_detection_confidence=.5,min_pose_presence_confidence=.5,min_tracking_confidence=.5)
        self.model=mp.tasks.vision.PoseLandmarker.create_from_options(options)
    def close(self):self.model.close()
    def analyze(self,image,key):
        now=time.monotonic()
        with self.lock:
            result=self.model.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=cv2.cvtColor(image,cv2.COLOR_BGR2RGB)))
            self.history={k:v for k,v in self.history.items() if now-v['time']<10}
            if len(self.history)>=128:self.history.pop(next(iter(self.history)))
            if len(result.pose_landmarks)!=1:
                self.history.pop(key,None)
                return {'source':'mediapipe_pose_lite_no_unique_body','confidence':0}
            landmarks=result.pose_landmarks[0]
            points=np.array([[p.x,p.y,p.z,p.visibility] for p in landmarks],float)
            out=pose_features(points,self.history.get(key),now)
            if out['confidence']>=.5:
                down=out.get('head_down_proxy',-1)>-.15
                self.history[key]={'points':points,'time':now,'head_down_since':now-out.get('prolonged_head_down_seconds',0),'down':down}
            else:self.history.pop(key,None)
            return out

def pose_features(p,previous=None,now=0.):
    # Must see shoulders and hips. Occluded wrists never imply folded arms.
    confidence=float(np.min(p[[11,12,23,24],3]))
    out={'source':'mediapipe_pose_lite_image_plane_geometry','confidence':round(confidence,4),
         'pose':np.round(p,4).tolist()}
    if confidence<.5:return out
    shoulder=(p[11,:2]+p[12,:2])/2;hip=(p[23,:2]+p[24,:2])/2
    torso=max(.05,float(np.linalg.norm(shoulder-hip)));width=float(np.linalg.norm(p[11,:2]-p[12,:2]))
    out.update(shoulder_openness=round(width/torso,4),torso_lean=round(math.degrees(math.atan2(shoulder[0]-hip[0],hip[1]-shoulder[1])),2),
        body_orientation={'shoulder_depth_difference':round(float(p[11,2]-p[12,2]),4),'metric_distance_available':False},
        gesture={'arms_crossed':'unknown','fidgeting':'unknown','repeated_movement':'unknown'})
    if p[0,3]>.5:
        out['head_down_proxy']=round(float((p[0,1]-shoulder[1])/torso),4)
        down=out['head_down_proxy']>-.15
        out['prolonged_head_down_seconds']=round(now-previous['head_down_since'],2) if down and previous and previous.get('down',True) else 0
    if previous and .05<now-previous['time']<3:
        old=previous['points'];dt=now-previous['time'];visible=(p[:,3]>.6)&(old[:,3]>.6)
        if visible.sum()>=8:
            motion=float(np.median(np.linalg.norm(p[visible,:2]-old[visible,:2],axis=1))/dt/torso)
            out.update(movement_intensity=round(motion,4),sudden_posture_change=motion>1.5)
        if visible[[15,16]].all():out['hand_movement_intensity']=round(float(np.linalg.norm(p[[15,16],:2]-old[[15,16],:2],axis=1).mean()/dt/torso),4)
        old_width=float(np.linalg.norm(old[11,:2]-old[12,:2]));out['approach_avoidance']=round((width-old_width)/dt,4)
    # Pose labels are only geometric hypotheses and need both knees visible.
    if np.min(p[[23,24,25,26,27,28],3])>.65:
        angles=[]
        for hip_i,knee,ankle in [(23,25,27),(24,26,28)]:
            a=p[hip_i,:2]-p[knee,:2];b=p[ankle,:2]-p[knee,:2]
            angles.append(math.degrees(math.acos(float(np.clip(a@b/max(np.linalg.norm(a)*np.linalg.norm(b),1e-8),-1,1)))))
        out['posture']='standing_geometry' if min(angles)>155 else 'bent_knees_geometry' if max(angles)<125 else 'unknown'
    return out
