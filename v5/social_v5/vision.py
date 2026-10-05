"""YuNet + SFace + EmotiEffNet on CPU. Frames are never written to disk."""
import base64, hashlib, io, json, secrets, threading, time
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, UnidentifiedImageError
from . import ROOT

LABELS=['anger','contempt','disgust','fear','happiness','neutral','sadness','surprise']
ZH=['愤怒表情','轻蔑表情','厌恶表情','恐惧表情','开心表情','中性表情','悲伤表情','惊讶表情']

def decode_image(encoded):
    if encoded.startswith('data:'):
        prefix,encoded=encoded.split(',',1)
        if prefix not in {'data:image/jpeg;base64','data:image/png;base64','data:image/webp;base64'}:raise ValueError('只接受 JPEG/PNG/WebP')
    if len(encoded)>5500000:raise ValueError('图像超过 4 MB')
    try:raw=base64.b64decode(encoded,validate=True)
    except Exception as e:raise ValueError('图像 Base64 无效') from e
    if len(raw)>4000000:raise ValueError('图像超过 4 MB')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {'JPEG','PNG','WEBP'}:raise ValueError('图像格式不支持')
            w,h=image.size
            if w*h>12000000 or min(w,h)<32 or max(w,h)>5000:raise ValueError('图像尺寸不支持')
            from PIL import ImageOps
            image=ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((960,720))
            return cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as e:raise ValueError('无法解码图像') from e

def iou(a,b):
    x=max(a[0],b[0]);y=max(a[1],b[1]);r=min(a[0]+a[2],b[0]+b[2]);d=min(a[1]+a[3],b[1]+b[3])
    inter=max(0,r-x)*max(0,d-y);return inter/max(1,a[2]*a[3]+b[2]*b[3]-inter)

class Vision:
    def __init__(self,memory,model_dir=None):
        folder=model_dir or ROOT/'models/vision'; self.memory=memory;self.lock=threading.RLock();self.streams={};self.frames={}
        for r in json.loads((folder/'manifest.json').read_text()):
            if hashlib.sha256((folder/r['file']).read_bytes()).hexdigest()!=r['sha256']:raise RuntimeError('Vision model hash mismatch')
        cv2.setNumThreads(2)
        # OpenCV narrow-character paths fail in the Chinese project directory on
        # Windows. The supported buffer overload avoids copying to a shadow path.
        self.detector=cv2.FaceDetectorYN.create('onnx',np.frombuffer((folder/'yunet.onnx').read_bytes(),np.uint8),np.array([],np.uint8),(320,320),.85,.3,500)
        self.recognizer=cv2.FaceRecognizerSF.create('onnx',np.frombuffer((folder/'sface.onnx').read_bytes(),np.uint8),np.array([],np.uint8))
        from .profiles import select_profile
        options=ort.SessionOptions();options.intra_op_num_threads=select_profile().threads;options.inter_op_num_threads=1
        social_model=ROOT/'models/social/emotieff_va.onnx'
        self.multitask=social_model.is_file() and model_dir is None
        if self.multitask:
            from .assets import checked_asset
            self.expression=ort.InferenceSession(str(checked_asset('social/emotieff_va_features.onnx')),options,providers=['CPUExecutionProvider'])
        else:self.expression=ort.InferenceSession(str(folder/'expression.onnx'),options,providers=['CPUExecutionProvider'])
        self.input_name=self.expression.get_inputs()[0].name
    def detect(self,image):
        h,w=image.shape[:2];self.detector.setInputSize((w,h));_,faces=self.detector.detect(image)
        return [] if faces is None else sorted(faces,key=lambda f:float(f[2]*f[3]),reverse=True)[:8]
    def quality(self,image,face):
        h,w=image.shape[:2];x,y,fw,fh=face[:4];x1=max(0,int(x));y1=max(0,int(y));x2=min(w,int(x+fw));y2=min(h,int(y+fh))
        crop=image[y1:y2,x1:x2]
        if not crop.size:return {'usable':False,'reasons':['empty_crop']},crop
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY);blur=float(cv2.Laplacian(gray,cv2.CV_64F).var());light=float(gray.mean())
        reasons=[]
        if min(fw,fh)<70:reasons.append('face_too_small')
        if blur<25:reasons.append('blurred')
        if light<35 or light>230:reasons.append('poor_lighting')
        if x<0 or y<0 or x+fw>w or y+fh>h:reasons.append('partial_face')
        eyes=face[4:8].reshape(2,2);nose=face[8:10]
        if abs(float(eyes[0,1]-eyes[1,1]))>fh*.2 or abs(float(nose[0]-eyes[:,0].mean()))>fw*.22:reasons.append('nonfrontal')
        return {'usable':not reasons,'reasons':reasons,'blur':round(blur,2),'brightness':round(light,2)},crop
    def embedding(self,image,face):
        v=self.recognizer.feature(self.recognizer.alignCrop(image,face)).reshape(-1).astype(np.float32)
        return v/max(float(np.linalg.norm(v)),1e-9)
    def predict_expression(self,crop):
        x=cv2.cvtColor(cv2.resize(crop,(224,224)),cv2.COLOR_BGR2RGB).astype(np.float32)/255.
        x=(x-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
        outputs=self.expression.run(None,{self.input_name:x.transpose(2,0,1)[None]})
        scores=outputs[0].reshape(-1)
        if len(scores) not in (8,10) or not np.isfinite(scores).all():raise RuntimeError('Unexpected expression output')
        logits=scores[:8];p=np.exp(logits-logits.max())
        self.last_social={'source':'emotieff_b0_multitask' if self.multitask else 'emotieff_b0_expression',
            'valence':float(np.clip(scores[8],-1,1)) if len(scores)==10 else None,
            'arousal':float(np.clip(scores[9],-1,1)) if len(scores)==10 else None,
            'facial_embedding':np.round(outputs[1].reshape(-1),5).tolist() if len(outputs)>1 else []}
        return p/p.sum()
    def match(self,embedding):
        scores=[]
        for uid,data in self.memory.faces():
            vectors=np.asarray(data['embeddings'],np.float32)
            # Median prevents one anomalous template dominating the match.
            scores.append((float(np.median(vectors@embedding)),uid))
        scores.sort(reverse=True)
        if not scores:return {'status':'no_registered_members','identity_verified':False}
        score,uid=scores[0];margin=score-(scores[1][0] if len(scores)>1 else 0)
        candidate=score>=.5 and margin>=.08
        return {'status':'candidate_requires_confirmation' if candidate else 'unknown','candidate_user_id':uid if candidate else None,'cosine_similarity':round(score,4),'margin':round(margin,4),'identity_verified':False,'liveness_verified':False}
    def analyze(self,encoded,stream_id,owner=None):
        start=time.monotonic();image=decode_image(encoded)
        with self.lock:
            now=time.monotonic();self.streams={k:v for k,v in self.streams.items() if now-v['time']<10};self.frames={k:v for k,v in self.frames.items() if now-v['time']<10}
            if len(self.streams)>128:self.streams.clear()
            if len(self.frames)>128:self.frames.clear()
            faces=self.detect(image);results=[];previous=self.streams.get(stream_id)
            for i,face in enumerate(faces):
                quality,crop=self.quality(image,face);bbox=[round(float(v),1) for v in face[:4]]
                result={'index':i,'bbox':bbox,'detection_score':float(face[-1]),'quality':quality,'expression':{'status':'unknown','reason':'quality_gate'},'identity':{'status':'not_evaluated','identity_verified':False}}
                if quality['usable']:
                    embedding=self.embedding(image,face);identity=self.match(embedding);p=self.predict_expression(crop);n=1
                    # Only smooth a single spatially and biometrically continuous face.
                    if len(faces)==1 and previous and iou(bbox,previous['bbox'])>.4 and float(embedding@previous['embedding'])>.6:
                        p=.55*p+.45*previous['p'];n=previous['n']+1
                    order=np.argsort(p);best=int(order[-1]);confidence=float(p[best]);uncertain=confidence<.55 or confidence-float(p[order[-2]])<.15
                    result['expression']={'status':'uncertain' if uncertain else 'expression_hypothesis','label':'unknown' if uncertain else LABELS[best],'label_zh':'表情不确定' if uncertain else ZH[best],'top_label':LABELS[best],'score':round(confidence,4),'distribution':{label:round(float(s),5) for label,s in zip(LABELS,p)},'frames_smoothed':n,'calibrated_probability':False,'inner_emotion_inferred':False}
                    result['identity']=identity
                    result['social_signal']={**self.last_social,'emotion_distribution':result['expression']['distribution'],
                        'confidence':round(confidence,4),'detection_confidence':float(face[-1]),
                        'landmarks':face[4:14].reshape(5,2).round(2).tolist(),
                        'head_pose':{'roll_degrees':round(float(np.degrees(np.arctan2(face[7]-face[5],face[6]-face[4]))),2),'method':'eye_line_only'},
                        'calibrated':False}
                    if len(faces)==1:self.streams[stream_id]=dict(time=now,bbox=bbox,p=p,embedding=embedding,n=n)
                results.append(result)
            if len(faces)!=1 or not results[0]['quality']['usable']:self.streams.pop(stream_id,None)
            frame_id=secrets.token_urlsafe(18)
            out={'frame_id':frame_id,'status':'no_face' if not faces else 'ok','faces':results,'frame_size':[image.shape[1],image.shape[0]],'latency_ms':round((time.monotonic()-start)*1000,2),'raw_image_stored':False,'source':'yunet_sface_emotieffnet_cpu','field_validated':False}
            self.frames[frame_id]={'time':now,'owner':owner,'result':out}
            return out
    def frame(self,frame_id,owner):
        with self.lock:
            r=self.frames.get(frame_id)
            if not r or r['owner']!=owner or time.monotonic()-r['time']>10:raise ValueError('图像结果已过期或不属于当前会话，请重新采集')
            return r['result']
    def enroll(self,uid,images):
        with self.lock:
            vectors=[];hashes=set()
            for encoded in images:
                image=decode_image(encoded);digest=hashlib.sha256(image.tobytes()).hexdigest()
                if digest in hashes:raise ValueError('请拍摄三个不同帧，不要重复上传同一张照片')
                hashes.add(digest);faces=self.detect(image)
                if len(faces)!=1:raise ValueError('登记画面必须恰好有一张人脸')
                quality,_=self.quality(image,faces[0])
                if not quality['usable']:raise ValueError('登记图像质量不足：'+','.join(quality['reasons']))
                vectors.append(self.embedding(image,faces[0]))
            matrix=np.stack(vectors)
            if float(np.min(matrix@matrix.T))<.5:raise ValueError('登记图片身份不一致，请重新拍摄')
            for other,data in self.memory.faces():
                if other!=uid and float(np.median(np.asarray(data['embeddings'])@matrix.T))>.5:raise ValueError('这张人脸与其他已登记成员相似，请先核对成员')
            self.memory.save_face(uid,matrix.tolist())
            return {'enrolled':True,'samples':len(vectors),'raw_images_stored':False,'liveness_verified':False,'requires_pin_for_private_memory':True}
