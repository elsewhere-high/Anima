"""Read-only hardware/runtime inventory and a short transient camera throughput probe."""
import json,importlib.util,platform,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/upgrade_20261001'
import psutil
def main():
    import onnxruntime,torch,cv2
    row={'os':platform.platform(),'physical_cores':psutil.cpu_count(False),'logical_cores':psutil.cpu_count(),
         'ram_total_mb':psutil.virtual_memory().total/1024**2,'ram_available_mb':psutil.virtual_memory().available/1024**2,
         'runtimes':{n:bool(importlib.util.find_spec(n)) for n in ['onnxruntime','tensorrt','openvino','coremltools','rknn','ncnn','mediapipe','sherpa_onnx']},
         'onnx_providers':onnxruntime.get_available_providers(),'torch_cuda':torch.version.cuda,
         'cuda_available':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
         'npu':'not detected via installed runtimes','microphone':'browser mono PCM 16kHz; energy VAD, 1.15s endpoint pause, <=20s chunks; alternating playback/capture',
         'tts':'explicit opt-in Edge online, or browser local installed Chinese voice',
         'camera':{}}
    cam=cv2.VideoCapture(0,cv2.CAP_DSHOW)
    try:
        cam.set(cv2.CAP_PROP_FRAME_WIDTH,640);cam.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        start=time.perf_counter();n=0
        while n<90 and time.perf_counter()-start<10:
            ok,frame=cam.read()
            if not ok:break
            n+=1
        elapsed=time.perf_counter()-start
        row['camera']={'frames':n,'elapsed_seconds':elapsed,'fps':n/elapsed if n else None,'resolution':[frame.shape[1],frame.shape[0]] if n else None,'raw_frames_saved':False,'recognition_run':False}
    finally:cam.release()
    row['nvidia_smi']=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True).stdout.strip()
    (OUT/'hardware.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(row,ensure_ascii=False))
if __name__=='__main__':main()
