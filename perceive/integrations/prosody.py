"""Acoustic measurements, never a pitch-to-emotion classifier."""
import numpy as np
import opensmile

class ProsodyFeatures:
    def __init__(self):
        self.smile = opensmile.Smile(feature_set=opensmile.FeatureSet.eGeMAPSv02,
                                    feature_level=opensmile.FeatureLevel.LowLevelDescriptors)

    def extract(self, audio, rate=16000):
        if rate != 16000 or audio.ndim != 1:
            raise ValueError('mono_16khz_required')
        duration = len(audio)/rate
        if duration < .4 or not np.isfinite(audio).all():
            return {'model': 'openSMILE-eGeMAPSv02', 'bins': [], 'quality': 'insufficient'}
        if np.sqrt(np.mean(audio*audio)) < 10**(-55/20):
            return {'model': 'openSMILE-eGeMAPSv02', 'bins': [], 'quality': 'quiet'}
        data = self.smile.process_signal(audio, rate)
        times = np.array([index[0].total_seconds() for index in data.index])
        bins = []
        for start in np.arange(0, duration, .2):
            selected = data[(times >= start) & (times < start+.2)]
            if len(selected) < 3:
                continue
            semitones = selected['F0semitoneFrom27.5Hz_sma3nz'].to_numpy()
            voiced = semitones > 0
            f0 = float(27.5 * 2**(np.median(semitones[voiced])/12)) if voiced.any() else None
            bins.append({'start': round(float(start), 2), 'end': round(min(duration, float(start+.2)), 2),
                         'f0Hz': round(f0, 1) if f0 else None,
                         'voicedFraction': round(float(voiced.mean()), 2),
                         'loudness': round(float(selected['Loudness_sma3'].median()), 3),
                         'hnrDb': round(float(selected['HNRdBACF_sma3nz'].median()), 1),
                         'jitter': round(float(selected['jitterLocal_sma3nz'].median()), 4)})
        return {'model': 'openSMILE-eGeMAPSv02', 'bins': bins, 'quality': 'ok',
                'note': 'Voicing is not speech activity; unvoiced consonants are not pauses. Values do not determine emotion.'}
