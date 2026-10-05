import json,sys,time
from pathlib import Path
import soundfile as sf
import sherpa_onnx
from train_speech_pilot import normalize,distance,rows
ROOT=Path(__file__).resolve().parents[1]

def main():
    canto=[json.loads(line) for line in (ROOT/'data/cantonese_probe/probe.jsonl').read_text(encoding='utf-8').splitlines()]
    mandarin=rows('validation');results=[];summary={}
    for language in ['zh','auto','yue']:
        model=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(ROOT/'models/sensevoice/model.int8.onnx'),tokens=str(ROOT/'models/sensevoice/tokens.txt'),num_threads=2,language=language,use_itn=True)
        for corpus,data in [('cantonese',canto),('mandarin_validation',mandarin)]:
            if language=='yue' and corpus=='mandarin_validation':continue
            errors=chars=0
            for row in data:
                x,sr=sf.read(row['path'],dtype='float32');s=model.create_stream();s.accept_waveform(sr,x);model.decode_stream(s)
                prediction=normalize(s.result.text);ref=normalize(row['text']);err=distance(ref,prediction);errors+=err;chars+=len(ref)
                results.append({'corpus':corpus,'language':language,'id':row['id'],'reference':ref,'prediction':prediction,'errors':err,'characters':len(ref)})
            summary[f'{corpus}_{language}']={'cer':errors/chars,'errors':errors,'characters':chars,'utterances':len(data)};print(language,corpus,summary[f'{corpus}_{language}'],flush=True)
    (ROOT/'reports/speech_20261005/cantonese_evaluation.json').write_text(json.dumps({'scope':'single-narrator external Cantonese probe; no Cantonese training in this run; traditional/simplified variants count as errors','summary':summary,'samples':results},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
