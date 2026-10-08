from pathlib import Path
import os,sys,subprocess,time,json,base64,datetime
os.environ['HF_HUB_OFFLINE']='1'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations'))
import imageio_ffmpeg,torch
from local_asr import LocalAsrModel
torch.set_num_threads(3)
out=ROOT/'research/local-asr-feasibility.json'
report={'createdAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model':'FunAudioLLM/SenseVoiceSmall','scope':'Local warm prefix latency and transcription, not independent recognition accuracy','runs':[]}
start=time.perf_counter();model=LocalAsrModel();report['loadMs']=round((time.perf_counter()-start)*1000)
for source in [*sorted((ROOT/'public/assets').glob('*.mp4')),ROOT/'integrations/models/sensevoice/example/zh.mp3']:
 for seconds in [1,3]:
  audio=subprocess.check_output([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(source),'-t',str(seconds),'-ac','1','-ar','16000','-f','wav','-'])
  start=time.perf_counter();result=model.infer({'audio':base64.b64encode(audio).decode()})
  row={'clip':source.stem,'prefix':seconds,'ms':round((time.perf_counter()-start)*1000),**result};report['runs'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
  out.write_text(json.dumps(report,indent=2,ensure_ascii=False))
