"""Optional best-edge geometry. Blendshapes are not FACS AUs or inner emotions."""
import math,threading
import cv2,numpy as np
from .assets import checked_asset

class FaceGeometry:
    def __init__(self):
        import mediapipe as mp
        self.mp=mp;self.lock=threading.Lock()
        self.model=mp.tasks.vision.FaceLandmarker.create_from_options(mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=checked_asset('social/face_landmarker.task').read_bytes()),
            num_faces=2,output_face_blendshapes=True,output_facial_transformation_matrixes=True))
    def close(self):self.model.close()
    def analyze(self,image):
        with self.lock:r=self.model.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=cv2.cvtColor(image,cv2.COLOR_BGR2RGB)))
        if len(r.face_landmarks)!=1:return {}
        mesh=np.array([[p.x,p.y,p.z] for p in r.face_landmarks[0]],float)
        matrix=np.asarray(r.facial_transformation_matrixes[0]);rotation=matrix[:3,:3]
        # Euler angles from MediaPipe's canonical transform; not calibrated gaze.
        sy=math.sqrt(rotation[0,0]**2+rotation[1,0]**2)
        pose={'pitch_degrees':math.degrees(math.atan2(rotation[2,1],rotation[2,2])),
              'yaw_degrees':math.degrees(math.atan2(-rotation[2,0],sy)),
              'roll_degrees':math.degrees(math.atan2(rotation[1,0],rotation[0,0])),
              'method':'mediapipe_canonical_face_transform'}
        gaze={}
        for name,iris,left,right in [('right_eye',468,33,133),('left_eye',473,362,263)]:
            if len(mesh)>iris:
                axis=mesh[right,:2]-mesh[left,:2]
                gaze[name+'_iris_horizontal_fraction']=round(float((mesh[iris,:2]-mesh[left,:2])@axis/max(axis@axis,1e-8)),4)
        gaze['gaze_to_robot_available']=False;gaze['method']='uncalibrated_iris_geometry_not_attention'
        return {'face_mesh':np.round(mesh,5).tolist(),'facial_blendshapes':{c.category_name:round(c.score,5) for c in r.face_blendshapes[0]},
                'head_pose':pose,'gaze':gaze}
