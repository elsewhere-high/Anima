"""Compare shipping INT8 decoder with/without activity/gain front end on held-out audio."""
import base64,io,json,sys,time,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from train_speech_pilot import rows,corrupt,seed_for,normalize,distance
from social_v5.speech_activity import inspect_audio
import sherpa_onnx,soundfile as sf

def main():
    model=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(ROOT/'models/sensevoice/model.int8.onnx'),tokens=str(ROOT/'models/sensevoice/tokens.txt'),num_threads=2,language='zh',use_itn=True)
    def decode(x):
        stream=model.create_stream();stream.accept_waveform(16000,x);model.decode_stream(stream);return normalize(stream.result.text)
    results=[]
    for row in rows('test'):
        raw=sf.read(row['path'],dtype='float32')[0];reference=normalize(row['text'])
        for kind in ['clean','quiet','noise','reverb_noise']:
            x=corrupt(raw,kind,seed_for(row,kind));start=time.monotonic();before=decode(x);quality=inspect_audio(x)
            gain=min(8,.06/max(quality['rms'],1e-8),.95/max(float(np.max(np.abs(x))),1e-8));after=decode(x*gain) if gain>1 else before
            results.append({'id':row['id'],'condition':kind,'reference':reference,'before':before,'after':after,'before_errors':distance(reference,before),'after_errors':distance(reference,after),'characters':len(reference),'rejected':quality['requires_repeat'],'quality':quality,'gain':gain,'seconds':time.monotonic()-start})
        if len(results)%24==0:print(f'evaluated {len(results)} conditions',flush=True)
    summary={}
    for kind in ['clean','quiet','noise','reverb_noise']:
        part=[r for r in results if r['condition']==kind];chars=sum(r['characters'] for r in part)
        summary[kind]={'raw_cer':sum(r['before_errors'] for r in part)/chars,'gain_cer':sum(r['after_errors'] for r in part)/chars,'speech_rejected':sum(r['rejected'] for r in part),'n':len(part)}
    out={'scope':'36 speaker-held-out Mandarin utterances, synthetic degradations; not physical distance or clinical speech','conditions':summary,'samples':results}
    (ROOT/'reports/speech_20261005/frontend_evaluation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
