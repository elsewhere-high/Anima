"""O(n) frame energy/VAD and bounded autocorrelation pitch; no psychological labels."""
import re
import numpy as np

def extract_audio_features(samples, text='', sr=16000):
    x=np.asarray(samples,dtype=np.float32);duration=len(x)/sr
    size=int(.02*sr);frames=x[:len(x)//size*size].reshape(-1,size)
    rms=np.sqrt(np.mean(frames**2,axis=1)+1e-12)
    threshold=max(.006,min(.03,float(np.percentile(rms,20))*2.5))
    active=rms>threshold;pitch=[]
    # One 40-ms pitch estimate per 100 ms, FFT autocorrelation.
    for start in range(0,len(x)-640+1,1600):
        frame=x[start:start+640].astype(float)
        if np.sqrt(np.mean(frame**2))<threshold:continue
        frame=(frame-frame.mean())*np.hanning(len(frame))
        spectrum=np.fft.rfft(frame,n=2048);corr=np.fft.irfft(abs(spectrum)**2,n=2048)[:640]
        low,high=int(sr/450),int(sr/65);lag=low+int(np.argmax(corr[low:high]))
        if corr[0]>0 and corr[lag]/corr[0]>.45:pitch.append(sr/lag)
    run=0;pauses=[]
    for flag in active:
        if not flag:run+=.02
        else:
            if run>=.2:pauses.append(run)
            run=0
    if run>=.2:pauses.append(run)
    voiced=float(active.sum())*.02
    return {'source':'local_dsp_energy_vad_autocorrelation','confidence':.65 if voiced>.2 else .15,
        'pitch':{'median_hz':round(float(np.median(pitch)),2) if pitch else None,
                 'range_hz':[round(float(np.percentile(pitch,q)),2) for q in [10,90]] if pitch else [],
                 'trend_hz':round(float(np.median(pitch[-3:])-np.median(pitch[:3])),2) if len(pitch)>=6 else None},
        'energy':{'rms':round(float(np.sqrt(np.mean(x*x))),6),'peak':round(float(abs(x).max()),5),
                  'relative_recording_level_not_calibrated_spl':True},
        'speech_rate':round(len(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+',text))/max(voiced,.2),3) if text else None,
        'pause':{'ratio':round(float(1-active.mean()),4),'count':len(pauses),'max_seconds':round(max(pauses,default=0),3)},
        'voice_activity':round(float(active.mean()),4),'duration_seconds':round(duration,3),
        'audio_events':[]}
