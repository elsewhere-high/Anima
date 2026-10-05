"""Actual artifact sizes and stored floating-weight counts (not marketing totals)."""
import json,sys,zipfile,numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/upgrade_20261001'
sys.path.insert(0,str(OUT/'candidate_deps'))
import onnx,tflite
rows=[]
for relative in ['vision/yunet.onnx','vision/sface.onnx','vision/expression.onnx','social/emotieff_va_features.onnx','sensevoice/model.int8.onnx']:
 p=ROOT/'models'/relative;m=onnx.load(p,load_external_data=False)
 params=sum(int(np.prod(x.dims)) for x in m.graph.initializer if x.data_type in (1,2,3,10) and not any(t in x.name for t in ['zero_point','scale']))
 rows.append({'file':relative,'bytes':p.stat().st_size,'stored_weight_elements_estimate':params,'count_note':'float/float16/int8 initializers excluding quantization scales; includes fixed constants'})
for relative in ['social/pose_landmarker_lite.task','social/face_landmarker.task']:
 p=ROOT/'models'/relative;count=0;components=[]
 with zipfile.ZipFile(p) as z:
  for name in z.namelist():
   if not name.endswith('.tflite'):continue
   m=tflite.Model.GetRootAsModel(z.read(name),0);subtotal=0
   for i in range(m.SubgraphsLength()):
    graph=m.Subgraphs(i)
    for j in range(graph.TensorsLength()):
     tensor=graph.Tensors(j)
     if tensor.Type() in (0,1) and m.Buffers(tensor.Buffer()).DataLength():subtotal+=int(np.prod(tensor.ShapeAsNumpy()))
   count+=subtotal;components.append({'file':name,'stored_float_elements':subtotal})
 rows.append({'file':relative,'bytes':p.stat().st_size,'stored_weight_elements_estimate':count,'components':components})
common=[]
for folder in [ROOT.parent/'v2/models/qwen35_2B',ROOT.parent/'v2/models/social_zh/best',ROOT.parent/'v4/models',ROOT/'models/bge-small-zh-v1.5',ROOT/'models/whisper-base']:
 common.append({'folder':str(folder.relative_to(ROOT.parent)),'artifact_bytes':sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()),'note':'directory bytes; Qwen file includes unused visual tensors; V4 may include historical checkpoints'})
release=json.loads((ROOT.parent/'v4/models/release.json').read_text())
common_files=list((ROOT.parent/'v2/models/qwen35_2B').glob('*.safetensors'))
for folder in [ROOT.parent/'v2/models/social_zh/best',ROOT.parent/'v4'/release['state']['checkpoint'],ROOT.parent/'v4'/release['dialogue']['checkpoint'],ROOT/'models/bge-small-zh-v1.5']:
 common_files.extend(p for p in folder.rglob('*') if p.suffix in {'.safetensors','.pt','.bin','.onnx'})
common_bytes=sum(p.stat().st_size for p in set(common_files))
size={r['file']:r['bytes'] for r in rows};whisper=sum(p.stat().st_size for p in (ROOT/'models/whisper-base').rglob('*') if p.is_file())
profiles={}
for name in ['old','ultra_light','balanced','best_edge']:
 total=common_bytes+size['vision/yunet.onnx']+size['vision/sface.onnx']+size['vision/expression.onnx' if name=='old' else 'social/emotieff_va_features.onnx']
 total+=whisper if name in {'old','ultra_light'} else size['sensevoice/model.int8.onnx']+(ROOT/'models/sensevoice/tokens.txt').stat().st_size
 if name!='old':total+=size['social/pose_landmarker_lite.task']
 if name=='best_edge':total+=size['social/face_landmarker.task']
 profiles[name]={'active_artifact_bytes':total,'additional_artifact_bytes_vs_old':total-profiles.get('old',{}).get('active_artifact_bytes',total)}
(OUT/'model_inventory.json').write_text(json.dumps({'encoders':rows,'existing_folders':common,'active_profiles':profiles,'active_artifact_note':'physical weight files referenced by runtime; Qwen source file includes unused vision tensors; excludes research candidates, rollback source and alternative CPU Qwen'},indent=2),encoding='utf-8');print(json.dumps(rows,indent=2))
