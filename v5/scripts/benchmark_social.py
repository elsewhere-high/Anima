"""Actual model/process benchmarks, isolated by candidate. No accuracy claims."""
import argparse, base64, importlib.util, json, os, sys, time, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np, psutil
OUT=ROOT/'reports/upgrade_20261001';OUT.mkdir(exist_ok=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('candidate',choices=['old_face','new_face','pose','whisper','sensevoice']);ap.add_argument('--n',type=int,default=12);args=ap.parse_args()
    proc=psutil.Process();base=proc.memory_info().rss;start=time.perf_counter();extra={}
    if args.candidate.endswith('face'):
        import cv2,onnxruntime as ort
        image=cv2.imdecode(np.frombuffer((ROOT/'tests/assets/astronaut.png').read_bytes(),np.uint8),1)
        if args.candidate=='old_face':
            from social_v5.vision import Vision
            spec=importlib.util.spec_from_file_location('social_v5.old_vision',OUT/'before/social_v5/vision.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            model=mod.Vision(type('Memory',(),{'faces':lambda self:[]})());encoded=base64.b64encode(cv2.imencode('.jpg',image)[1]).decode()
            run=lambda:model.analyze(encoded,'benchmark','benchmark')
        else:
            from social_v5.vision import Vision
            model=Vision(type('Memory',(),{'faces':lambda self:[]})());encoded=base64.b64encode(cv2.imencode('.jpg',image)[1]).decode()
            run=lambda:model.analyze(encoded,'benchmark','benchmark')
    elif args.candidate=='pose':
        import cv2
        from social_v5.body import BodyEncoder
        model=BodyEncoder();image=cv2.imdecode(np.frombuffer((ROOT/'tests/assets/astronaut.png').read_bytes(),np.uint8),1)
        run=lambda:model.analyze(image,'benchmark')
    else:
        import soundfile as sf
        samples,sr=sf.read(ROOT/'models/sensevoice/test_wavs/zh.wav',dtype='float32');extra['audio_seconds']=len(samples)/sr
        if args.candidate=='whisper':
            from faster_whisper import WhisperModel
            model=WhisperModel(str(ROOT/'models/whisper-base'),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
            def run():
                segments,_=model.transcribe(samples,language='zh',beam_size=3,vad_filter=True,condition_on_previous_text=False)
                return ''.join(s.text for s in segments)
        else:
            import sherpa_onnx
            model=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(ROOT/'models/sensevoice/model.int8.onnx'),tokens=str(ROOT/'models/sensevoice/tokens.txt'),num_threads=2,language='zh',use_itn=True)
            def run():
                stream=model.create_stream();stream.accept_waveform(sr,samples);model.decode_stream(stream)
                return str(stream.result)
    cold=time.perf_counter()-start;lat=[];cpu=proc.cpu_times();wall=time.perf_counter();peak=proc.memory_info().rss
    for i in range(args.n+1):
        t=time.perf_counter();result=run();elapsed=(time.perf_counter()-t)*1000
        if i:lat.append(elapsed)
        else:extra['first_inference_ms']=elapsed
        peak=max(peak,proc.memory_info().rss)
    used=proc.cpu_times();elapsed=time.perf_counter()-wall
    row={'candidate':args.candidate,'n':args.n,'cold_start_seconds':cold,'latency_ms':{'p50':float(np.percentile(lat,50)),'p95':float(np.percentile(lat,95))},
         'ram_rss_mb':peak/1024**2,'ram_increment_mb':(peak-base)/1024**2,'cpu_one_core_percent':100*(used.user+used.system-cpu.user-cpu.system)/elapsed,
         'vram_mb':0,'gpu_utilization_percent':0,'fixture':'NASA astronaut public fixture' if args.candidate.endswith('face') or args.candidate=='pose' else 'SenseVoice published zh.wav',
         'scope':'engineering fixture latency, NOT field accuracy or live camera FPS',**extra}
    if 'audio_seconds' in extra:row['realtime_factor']=row['latency_ms']['p50']/1000/extra['audio_seconds'];row['output']=str(result)[:1500]
    else:row['processed_fps']=1000/row['latency_ms']['p50'];row['output']=str(result)[:500]
    (OUT/(args.candidate+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(row,ensure_ascii=False))
    if hasattr(model,'close'):model.close()
if __name__=='__main__':main()
