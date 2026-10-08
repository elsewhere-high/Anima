from pathlib import Path
import os,sys,time,base64,subprocess,json,datetime
os.environ['HF_HUB_OFFLINE']='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'integrations'))
import torch,imageio_ffmpeg
from local_asr import LocalAsrModel
from depthwise_cpu import install,forward
torch.manual_seed(17);torch.set_num_threads(3)
# Generic equivalence check includes nontrivial stride/dilation and bias.
errors=[]
for channels,kernel,stride,dilation,padding,bias in [(512,11,1,1,0,False),(4,5,2,2,3,True),(3,3,1,1,1,False)]:
 m=torch.nn.Conv1d(channels,channels,kernel,stride=stride,padding=padding,dilation=dilation,groups=channels,bias=bias).eval();x=torch.randn(2,channels,45)
 with torch.inference_mode():a=m(x);b=forward(m,x)
 torch.testing.assert_close(a,b,atol=2e-6,rtol=2e-5);errors.append(float((a-b).abs().max()))
model=LocalAsrModel(fast=False);requests=[];report={'createdAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'maxOperatorErrors':errors,'runs':[]}
for source in [*sorted((ROOT/'public/assets').glob('*.mp4')),ROOT/'integrations/models/sensevoice/example/zh.mp3']:
 audio=subprocess.check_output([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(source),'-t','3','-ar','16000','-ac','1','-f','wav','-']);requests.append((source.stem,{'audio':base64.b64encode(audio).decode()}))
for variant in ['original','vectorized']:
 if variant=='vectorized':report['changedLayers']=install(model.model.model)
 for clip,request in requests:
  started=time.perf_counter();r=model.infer(request);row={'variant':variant,'clip':clip,'ms':round((time.perf_counter()-started)*1000),**r};report['runs'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
  (ROOT/'research/depthwise-feasibility.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
for clip,_ in requests:
 pair=[r for r in report['runs']if r['clip']==clip];assert pair[0]['transcript']==pair[1]['transcript'],clip
print('All six transcript pairs identical',flush=True)
