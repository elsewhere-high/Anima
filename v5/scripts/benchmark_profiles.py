"""Whole-system replay on real weights and GPU. Run each profile in a fresh process."""
import argparse,base64,importlib.util,json,os,sys,tempfile,threading,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));OUT=ROOT/'reports/upgrade_20261001'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('profile',choices=['old','ultra_light','balanced','best_edge']);ap.add_argument('--n',type=int,default=5);args=ap.parse_args()
    os.environ['SOCIAL_PROFILE']='ultra_light' if args.profile=='old' else args.profile
    import psutil,numpy as np
    proc=psutil.Process();rss=[];gpu=[];running=threading.Event();running.set()
    def monitor():
        ticks=0
        while running.is_set():
            rss.append(proc.memory_info().rss);ticks+=1
            if ticks%10==0:
                try:
                    value=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,creationflags=0x08000000 if os.name=='nt' else 0)
                    gpu.append(float(value.stdout.strip().splitlines()[0]))
                except Exception:pass
            time.sleep(.1)
    watcher=threading.Thread(target=monitor,daemon=True);watcher.start();start=time.perf_counter()
    import social_v5
    from social_v5.memory import MemoryStore
    from social_v5.embedding import Embedding
    from social_v5.schema import Observation
    from social_v5.predictor import Predictor
    from social_v5.engine import SocialEngine
    from social_v5.vision import Vision
    from social_v5.voice import transcribe
    import torch
    def old_module(name):
        spec=importlib.util.spec_from_file_location('social_v5.old_'+name,OUT/'before/social_v5'/f'{name}.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
    if args.profile=='old':
        Vision=old_module('vision').Vision;SocialEngine=old_module('engine').SocialEngine;Predictor=old_module('predictor').Predictor;transcribe=old_module('voice').transcribe
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);memory=MemoryStore(p/'m.db',p/'key',Embedding());vision=Vision(memory)
        social=None
        if args.profile!='old':
            from social_v5.social_runtime import SocialRuntime
            social=SocialRuntime(memory,vision)
        engine=SocialEngine(Predictor('cuda'),memory)
        cold=time.perf_counter()-start
        image=base64.b64encode((ROOT/'tests/assets/astronaut.png').read_bytes()).decode()
        audio=base64.b64encode((ROOT/'models/sensevoice/test_wavs/zh.wav').read_bytes()).decode()
        memory.register('bench','benchmark','benchmark-pin',True)
        times=[];audio_times=[];face_times=[];replies=[];fusion=[]
        cpu0=proc.cpu_times();work_start=time.perf_counter()
        for i in range(args.n):
            started=time.perf_counter();session='bench'+str(i)
            t=time.perf_counter()
            if social:visual=social.visual(image,'benchmark',session,'bench')
            else:visual=vision.analyze(image,session,'benchmark')
            face_times.append((time.perf_counter()-t)*1000)
            t=time.perf_counter()
            speech=social.audio(audio,'benchmark',session,'bench') if social else transcribe(audio)
            audio_times.append((time.perf_counter()-t)*1000)
            text=['我今天有点累，只想让你听我说。','我没事。','烦死了。','我今天很开心。','我有点犹豫，不知道怎么办。'][i%5]
            kwargs={}
            if social:
                t=time.perf_counter();state=social.state('benchmark',session,text,'bench',speech['audio_frame_id']);fusion.append((time.perf_counter()-t)*1000);kwargs['human_state']=state
            result=engine.step(Observation(speech=text,user_id='bench',identity_verified=True,memory_consent=True,session_id=session),visual,**kwargs)
            times.append((time.perf_counter()-started)*1000)
            replies.append({'input':text,'response':result['response'],'status':result['dialogue']['status'],'human_state_event':result.get('human_state',{}).get('event')})
            print(args.profile,i,result['dialogue']['status'],round(times[-1]),flush=True)
        cpu=proc.cpu_times();work=time.perf_counter()-work_start
        percentile=lambda xs:{'p50':float(np.percentile(xs,50)),'p95':float(np.percentile(xs,95))} if xs else None
        row={'profile':args.profile,'n':args.n,'cold_start_seconds_excluding_lazy_asr':cold,
            'first_turn_ms_including_asr_load':times[0],'face_and_body_ms':percentile(face_times),
            'audio_ms':percentile(audio_times[1:]),'temporal_fusion_ms':percentile(fusion),
            'end_to_end_ms':percentile(times[1:]),'ram_peak_mb':max(rss)/1024**2,
            'vram_peak_allocated_mb':torch.cuda.max_memory_allocated()/1024**2,
            'vram_reserved_mb':torch.cuda.max_memory_reserved()/1024**2,
            'cpu_one_core_percent':100*(cpu.user+cpu.system-cpu0.user-cpu0.system)/work,
            'qwen_parameters':sum(p.numel() for p in engine.predictor.model.parameters()),
            'audio_realtime_factor':float(np.median(audio_times[1:]))/5592,
            'camera_fps':None,'gpu_utilization_percent':{'mean':float(np.mean(gpu)),'max':max(gpu),'scope':'system-wide sampled including load'} if gpu else None,'replies':replies,
            'scope':'Local GPU Qwen + real published image/audio replay; p95 small-sample descriptive, not production SLA; audio capture wait and TTS excluded'}
        (OUT/('profile_'+args.profile+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(row,ensure_ascii=False),flush=True)
        if social:social.close()
        memory.db.close()
    running.clear();watcher.join(1)
if __name__=='__main__':main()
