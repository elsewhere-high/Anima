"""Real pretrained inference on the existing public demo clips; no device access or training."""
import sys, json, base64, io, time, statistics
from pathlib import Path
import numpy as np
import av, soundfile as sf
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"integrations"))
from specialists import FaceModel,VoiceModel
face,voice=FaceModel(),VoiceModel()
report={"purpose":"运行速度与覆盖检查，无独立人工真值，不计算准确率","device":"M5 MacBook Air / CPU / 3 threads","models":["OpenFace-3.0","EmotiEffLib-enet-b2-8" if face.expression else "no-second-expression-model","emotion2vec-plus-large"],"voiceParameters":voice.parameters,"samples":[]}
inputs={"samples":[]}
def pcm(path):
    data=[]
    with av.open(str(path)) as container:
        resampler=av.AudioResampler(format="fltp",layout="mono",rate=16000)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):data.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):data.append(out.to_ndarray().reshape(-1))
    return np.concatenate(data) if data else np.zeros(0,dtype=np.float32)
for path in sorted((ROOT/"public/assets").glob("*.mp4")):
    audio=pcm(path);frames=[]
    with av.open(str(path)) as container:
        next_t=0
        for frame in container.decode(video=0):
            t=float(frame.time or 0)
            if t+.02<next_t:continue
            next_t=t+.5
            image=frame.to_image();image.thumbnail((640,480));out=io.BytesIO();image.save(out,format="JPEG",quality=78)
            encoded=base64.b64encode(out.getvalue()).decode()
            began=time.perf_counter();result=face.infer({"image":encoded})
            ms=round((time.perf_counter()-began)*1000,1)
            frames.append({"t":round(t,3),"image":encoded})
            report["samples"].append({"clip":path.stem,"kind":"face","at":round(t,3),"latencyMs":ms,**result})
    duration=len(audio)/16000
    for start in np.arange(0,max(.1,duration-1),1):
        end=min(duration,start+3)
        if end-start<.4:continue
        out=io.BytesIO();sf.write(out,audio[int(start*16000):int(end*16000)],16000,format="WAV",subtype="PCM_16")
        encoded=base64.b64encode(out.getvalue()).decode()
        began=time.perf_counter();result=voice.infer({"audio":encoded});ms=round((time.perf_counter()-began)*1000,1)
        report["samples"].append({"clip":path.stem,"kind":"voice","start":float(start),"end":end,"latencyMs":ms,**result})
        if start==0:
            inputs["samples"].append({"id":path.stem,"input":{"duration":end,"start":0,"audio":{"mimeType":"audio/wav","data":encoded},"frames":[f for f in frames if f["t"]<end],"face":[],"context":[]}})
    print(path.stem+" complete",file=sys.stderr,flush=True)
    (ROOT/"research/specialist-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
for kind in ["face","voice"]:
    values=sorted(x["latencyMs"] for x in report["samples"] if x["kind"]==kind)
    report[kind]={"requests":len(values),"p50Ms":statistics.median(values),"p95Ms":values[min(len(values)-1,int(len(values)*.95))],"maxMs":max(values)}
(ROOT/"research/specialist-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
(ROOT/"research/public-clip-inputs.json").write_text(json.dumps(inputs,ensure_ascii=False))
print(json.dumps({k:v for k,v in report.items() if k!="samples"},ensure_ascii=False),file=sys.__stdout__,flush=True)
