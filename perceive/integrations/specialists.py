"""Resident, offline inference. JSON on stdout; diagnostics on stderr. No media files."""
import sys, os, json, base64, io, time, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
PROTOCOL = sys.stdout
sys.stdout = sys.stderr
write_lock = threading.Lock()

def send(value):
    with write_lock:
        PROTOCOL.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        PROTOCOL.flush()

import numpy as np
import torch
import cv2
TORCH_THREADS=max(1,min(8,int(os.environ.get("ANIMA_TORCH_THREADS", "3"))))
torch.set_num_threads(TORCH_THREADS)
torch.set_num_interop_threads(1)
cv2.setNumThreads(1)

class FaceModel:
    labels = ["neutral", "happy", "sad", "surprise", "fear", "disgust", "anger", "contempt"]
    # Official demo2.py, lines 190–192; eight DISFA AUs, not the 18-AU OpenFace 2 set.
    aus = ["AU1", "AU2", "AU4", "AU6", "AU9", "AU12", "AU25", "AU26"]
    def __init__(self):
        from openface.face_detection import FaceDetector
        from openface.Pytorch_Retinaface.models.retinaface import RetinaFace
        from openface.multitask_model import MultitaskPredictor
        class MemoryDetector(FaceDetector):
            def _load_retinaface_model(self, path):
                self.cfg = dict(self.cfg, pretrain=False)
                model = RetinaFace(cfg=self.cfg, phase="test")
                weights = torch.load(path, map_location="cpu", weights_only=True)
                weights = weights.get("state_dict", weights)
                model.load_state_dict({k.removeprefix("module."):v for k,v in weights.items()}, strict=True)
                return model.eval()
            def preprocess_image(self, image, resize=1.0):
                img = image.astype(np.float32) - np.array([104,117,123], dtype=np.float32)
                return torch.from_numpy(img.transpose(2,0,1)).unsqueeze(0), image
        self.detector = MemoryDetector(str(ROOT/"models/openface/Alignment_RetinaFace.pth"))
        self.predictor = MultitaskPredictor(str(ROOT/"models/openface/MTL_backbone.pth"), device="cpu")
        self.expression=None
        expression_path=ROOT/"models/emotieff/enet_b2_8.onnx"
        if expression_path.is_file():
            import onnxruntime as ort
            options=ort.SessionOptions()
            options.intra_op_num_threads=2
            options.inter_op_num_threads=1
            self.expression=ort.InferenceSession(str(expression_path),sess_options=options,providers=["CPUExecutionProvider"])
    def infer(self, request):
        image = cv2.imdecode(np.frombuffer(base64.b64decode(request["image"], validate=True), np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0]*image.shape[1]>3000000:
            raise ValueError("invalid frame")
        # Detector is evaluated at at most 640px; preserve the original crop for expression.
        height,width=image.shape[:2]
        scale=min(1.0,640/max(height,width))
        small=cv2.resize(image,(round(width*scale),round(height*scale))) if scale<1 else image
        with torch.inference_mode():
            boxes,_ = self.detector.detect_faces(small)
            boxes = boxes[boxes[:,4] >= .8]
            result={"model":"OpenFace-3.0","faces":len(boxes),"scores":{},"aus":{}}
            if len(boxes)!=1:
                return result
            box=boxes[0,:4]/scale
            x1,y1,x2,y2=[int(v) for v in box]
            x1,y1=max(0,x1),max(0,y1)
            x2,y2=min(width,x2),min(height,y2)
            result["facePixels"]=min(x2-x1,y2-y1)
            if result["facePixels"]<48:
                result["quality"]="small_face"
                return result
            emotion,gaze,aus=self.predictor.predict(image[y1:y2,x1:x2])
            result.update(scores=dict(zip(self.labels,emotion.softmax(-1)[0].tolist())),
                          aus=dict(zip(self.aus,aus[0].tolist())),
                          gaze=gaze[0].tolist(),quality="ok")
            result["expressionModels"]={"OpenFace-3.0":result["scores"]}
            if self.expression:
                # Same RGB preprocessing and class order as EmotiEffLib 1.1.1.
                rgb=cv2.cvtColor(image[y1:y2,x1:x2],cv2.COLOR_BGR2RGB)
                tensor=(cv2.resize(rgb,(260,260))/255-np.array([.485,.456,.406]))/np.array([.229,.224,.225])
                tensor=tensor.transpose(2,0,1).astype(np.float32)[None]
                logits=self.expression.run(None,{self.expression.get_inputs()[0].name:tensor})[0][0]
                scores=np.exp(logits-logits.max());scores/=scores.sum()
                result["scores"]=dict(zip(["anger","contempt","disgust","fear","happy","neutral","sad","surprise"],scores.tolist()))
                result["expressionModels"]["EmotiEffLib-enet-b2-8"]=result["scores"]
                result["model"]="EmotiEffLib-enet-b2-8 + OpenFace-3.0"
            return result

class VoiceModel:
    def __init__(self):
        if not (ROOT/"models/emotion2vec/model.pt").is_file():
            raise FileNotFoundError("emotion2vec weights not installed")
        from funasr import AutoModel
        self.model=AutoModel(model=str(ROOT/"models/emotion2vec"),device="cpu",ncpu=TORCH_THREADS,disable_update=True,disable_pbar=True,
                             scope_map=["d2v_model.", "None"],ignore_init_mismatch=False)
        # FunASR otherwise tolerates missing inference weights. Only the unused
        # pretraining reconstruction decoder may be absent from this checkpoint.
        checkpoint={key.removeprefix("d2v_model."):value for key,value in
                    torch.load(ROOT/"models/emotion2vec/model.pt",map_location="cpu",weights_only=True,mmap=True)["model"].items()}
        missing=[key for key,value in self.model.model.state_dict().items()
                 if ".decoder." not in key and (key not in checkpoint or checkpoint[key].shape!=value.shape)]
        if missing:
            raise ValueError("incomplete inference checkpoint: "+", ".join(missing[:3]))
        self.parameters=sum(p.numel() for p in self.model.model.parameters())
        self.prosody=None
        if os.environ.get('ANIMA_PROSODY')=='1':
            from prosody import ProsodyFeatures
            self.prosody=ProsodyFeatures()
    def infer(self,request):
        import soundfile as sf
        audio,rate=sf.read(io.BytesIO(base64.b64decode(request["audio"], validate=True)),dtype="float32")
        if rate!=16000 or audio.ndim!=1 or not 6400<=len(audio)<=16000*8:
            raise ValueError("expected mono 16kHz WAV, .4–8 seconds")
        db=float(20*np.log10(max(1e-6,np.sqrt(np.mean(audio*audio)))))
        if db < -50:
            return {"model":"emotion2vec-plus-large","scores":{},"quality":"quiet"}
        with torch.inference_mode():
            result=self.model.generate(input=audio,granularity="utterance",extract_embedding=False,disable_pbar=True)[0]
        value={"model":"emotion2vec-plus-large","scores":dict(zip(result["labels"],result["scores"])),"quality":"ok"}
        if self.prosody:
            value['prosody']=self.prosody.extract(audio,rate)
        return value

def main():
    models={}
    constructors=[("face",FaceModel),("voice",VoiceModel)]
    if os.environ.get('ANIMA_DISFLUENCY')=='1':
        from disfluency import DisfluencyModel
        constructors.append(('speech',DisfluencyModel))
    if os.environ.get('ANIMA_LOCAL_ASR')=='1':
        from local_asr import LocalAsrModel
        constructors.append(('asr',LocalAsrModel))
    for kind,constructor in constructors:
        try:
            models[kind]=constructor()
            send({"type":"model","kind":kind,"status":"ready"})
        except Exception as error:
            print(f"{kind} model load: {type(error).__name__}: {error}",file=sys.stderr)
            send({"type":"model","kind":kind,"status":"unavailable","error":type(error).__name__})
    # Model constructors may reset PyTorch's process-wide setting. Apply the
    # intended limit after all loads and report the actual value for diagnosis.
    torch.set_num_threads(TORCH_THREADS)
    send({"type":"ready","models":list(models),"runtime":{"torchThreads":torch.get_num_threads(),"workers":len(constructors)}})
    busy=set()
    busy_lock=threading.Lock()
    def run(request):
        began=time.perf_counter()
        try:
            result=models[request["kind"]].infer(request)
            send({"id":request["id"],"result":result,"latencyMs":round((time.perf_counter()-began)*1000)})
        except Exception as error:
            print(f"inference: {type(error).__name__}: {error}",file=sys.stderr)
            send({"id":request["id"],"error":type(error).__name__})
        finally:
            with busy_lock:busy.discard(request["kind"])
    with ThreadPoolExecutor(max_workers=len(constructors)) as pool:
        for line in sys.stdin:
            if len(line)>1000000:
                continue
            try:
                request=json.loads(line)
                if request.get("kind") not in models:
                    send({"id":request.get("id"),"error":"model_unavailable"})
                    continue
                with busy_lock:
                    if request["kind"] in busy:
                        send({"id":request["id"],"error":"busy"})
                        continue
                    busy.add(request["kind"])
                pool.submit(run,request)
            except Exception:
                send({"error":"invalid_request"})
if __name__=="__main__":
    main()
