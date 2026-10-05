"""Expose real penultimate features and evaluate selective INT8 quantization parity."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np,onnx,onnxruntime as ort,cv2
from onnxruntime.quantization import quantize_dynamic,QuantType
def main():
    folder=ROOT/'models/social';source=folder/'emotieff_va.onnx'
    model=onnx.load(source);head=next(n for n in reversed(model.graph.node) if n.op_type=='Gemm')
    model.graph.output.append(onnx.helper.make_tensor_value_info(head.input[0],onnx.TensorProto.FLOAT,[1,1280]))
    prepared=folder/'emotieff_va_features.onnx';onnx.save(model,prepared)
    trial=ROOT/'reports/upgrade_20261001/emotieff_head_int8.onnx'
    quantize_dynamic(onnx.shape_inference.infer_shapes(model),str(trial),weight_type=QuantType.QInt8,op_types_to_quantize=['MatMul','Gemm'])
    opt=ort.SessionOptions();opt.intra_op_num_threads=2;opt.inter_op_num_threads=1
    original=ort.InferenceSession(str(prepared),opt,providers=['CPUExecutionProvider'])
    quantized=ort.InferenceSession(str(trial),opt,providers=['CPUExecutionProvider'])
    from social_v5.vision import Vision
    vision=Vision(type('Memory',(),{'faces':lambda self:[]})(),model_dir=ROOT/'models/vision')
    image=cv2.imdecode(np.frombuffer((ROOT/'tests/assets/astronaut.png').read_bytes(),np.uint8),1);face=vision.detect(image)[0];_,crop=vision.quality(image,face)
    rows=[];times=[[],[]]
    for scale in np.linspace(.75,1.2,20):
        x=cv2.cvtColor(cv2.resize(cv2.convertScaleAbs(crop,alpha=scale),(224,224)),cv2.COLOR_BGR2RGB).astype(np.float32)/255
        x=((x-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)).transpose(2,0,1)[None]
        outputs=[]
        for i,session in enumerate([original,quantized]):
            t=time.perf_counter();outputs.append(session.run(None,{session.get_inputs()[0].name:x})[0]);times[i].append((time.perf_counter()-t)*1000)
        a,b=outputs;rows.append({'same_top_class':bool(a[0,:8].argmax()==b[0,:8].argmax()),'max_absolute_output_error':float(abs(a-b).max())})
    result={'parameters':sum(np.prod(x.dims).item() for x in model.graph.initializer),
        'fp32_bytes':prepared.stat().st_size,'head_int8_bytes':trial.stat().st_size,
        'latency_p50_ms':[float(np.median(t)) for t in times],
        'max_output_error':max(r['max_absolute_output_error'] for r in rows),
        'class_agreement':sum(r['same_top_class'] for r in rows)/len(rows),
        'decision':'keep_fp32; selective head quantization saves negligible bytes, no independent labeled accuracy set',
        'scope':'20 brightness variants of one public fixture; parity only, NOT accuracy calibration'}
    manifest=json.loads((folder/'manifest.json').read_text());manifest=[r for r in manifest if r['file']!='social/emotieff_va_features.onnx']
    manifest.append({'file':'social/emotieff_va_features.onnx','source':'social/emotieff_va.onnx','transform':'add penultimate 1280D output, identical weights','bytes':prepared.stat().st_size,'sha256':hashlib.sha256(prepared.read_bytes()).hexdigest()})
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (ROOT/'reports/upgrade_20261001/quantization.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)
if __name__=='__main__':main()
