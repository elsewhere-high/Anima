"""Isolated research candidate. Official weights, safe tensor-only load, real waveform."""
import json,sys,time,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/upgrade_20261001'
sys.path.insert(0,str(OUT/'candidate_deps'))
import numpy as np,psutil
start=time.perf_counter();proc=psutil.Process();base=proc.memory_info().rss
try:
 import torch,yaml,soundfile as sf
 from funasr.models.emotion2vec.model import Emotion2vec
 torch.set_num_threads(2)
 cfg=yaml.safe_load((OUT/'candidate_emotion2vec/config.yaml').read_text())
 cfg['model_conf']['norm_eps']=float(cfg['model_conf']['norm_eps'])
 state=torch.load(OUT/'candidate_emotion2vec/model.pt',map_location='cpu',weights_only=True)
 print('checkpoint keys',list(state)[:10],flush=True)
 if 'state_dict' in state:state=state['state_dict']
 elif 'model' in state:state=state['model']
 state={k.removeprefix('d2v_model.'):v for k,v in state.items()}
 cfg['model_conf']['modalities']['audio']['decoder']=None
 cfg['model_conf']['project_dim']=int(state['proj.weight'].shape[0])
 model=Emotion2vec(**cfg,vocab_size=int(state['proj.weight'].shape[0]))
 info=model.load_state_dict(state,strict=False)
 print('load',info,flush=True)
 if info.missing_keys:raise RuntimeError('Missing checkpoint weights: '+str(info.missing_keys))
 del state;gc.collect();model.eval();params=sum(p.numel() for p in model.parameters())
 samples,sr=sf.read(ROOT/'models/sensevoice/test_wavs/zh.wav',dtype='float32')
 x=torch.from_numpy(samples);x=torch.nn.functional.layer_norm(x,x.shape)[None]
 cold=time.perf_counter()-start;times=[];peak=proc.memory_info().rss
 with torch.inference_mode():
  for i in range(11):
   t=time.perf_counter();features=model.extract_features(x)['x'].mean(dim=1);scores=torch.softmax(model.proj(features),dim=-1);elapsed=(time.perf_counter()-t)*1000
   if i:times.append(elapsed)
   peak=max(peak,proc.memory_info().rss)
 row={'candidate':'emotion2vec_plus_base','parameters':params,'cold_start_seconds':cold,'ram_rss_mb':peak/1024**2,
      'ram_increment_mb':(peak-base)/1024**2,'latency_ms':{'p50':float(np.percentile(times,50)),'p95':float(np.percentile(times,95))},
      'embedding_shape':list(features.shape),'scores':scores.tolist(),'checkpoint_bytes':(OUT/'candidate_emotion2vec/model.pt').stat().st_size,
      'missing_keys':info.missing_keys,'unexpected_keys':info.unexpected_keys,'status':'measured','audio_seconds':len(samples)/sr}
 from faster_whisper import WhisperModel
 asr=WhisperModel(str(ROOT/'models/whisper-base'),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
 paired=[]
 with torch.inference_mode():
  for _ in range(5):
   t=time.perf_counter();features=model.extract_features(x)['x'].mean(dim=1);list(asr.transcribe(samples,language='zh',beam_size=3,vad_filter=True,condition_on_previous_text=False)[0]);paired.append((time.perf_counter()-t)*1000)
 row['paired_with_whisper']={'latency_p50_ms':float(np.median(paired)),'ram_rss_mb':proc.memory_info().rss/1024**2,'weights_only_fp32_bytes':sum(p.numel()*p.element_size() for p in model.parameters())}
 original_scores=scores.clone();t=time.perf_counter()
 model=torch.ao.quantization.quantize_dynamic(model,{torch.nn.Linear},dtype=torch.qint8,inplace=True)
 quant_times=[]
 with torch.inference_mode():
  for _ in range(5):
   t=time.perf_counter();f=model.extract_features(x)['x'].mean(dim=1);q=torch.softmax(model.proj(f),dim=-1);list(asr.transcribe(samples,language='zh',beam_size=3,vad_filter=True,condition_on_previous_text=False)[0]);quant_times.append((time.perf_counter()-t)*1000)
 row['int8_paired_with_whisper']={'latency_p50_ms':float(np.median(quant_times)),'ram_rss_mb':proc.memory_info().rss/1024**2,'max_score_difference':float(abs(q-original_scores).max()),'top_class_agreement':bool(q.argmax()==original_scores.argmax()),'scope':'one neutral clip, not accuracy validation; process retains allocator memory after fp32 test'}
except Exception as e:
 import traceback
 row={'candidate':'emotion2vec_plus_base','status':'failed','error':str(e),'traceback':traceback.format_exc()}
(OUT/'emotion2vec.json').write_text(json.dumps(row,indent=2),encoding='utf-8');print(json.dumps(row,indent=2))
