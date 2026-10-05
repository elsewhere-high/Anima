"""Time-aware, bounded EMA fusion and slow consented within-person statistics.

Confidence values are engineering reliability gates, not calibrated accuracy.
Emotion/personality cannot be deduced from geometry or a single observation.
"""
import copy, math, re, threading, time
from collections import deque
from .human_state import HumanState, Face, Voice, Body, Language, Temporal
from .expression_actions import action_scores, describe_actions

EMOTIONS={
 'frustrated':('挫败','烦死','烦躁'), 'disappointed':('失望',),
 'relieved':('松了口气','放心了'), 'lonely':('孤独','孤单'),
 'embarrassed':('尴尬','不好意思'), 'hesitant':('犹豫',),
 'anxious':('焦虑','担心','紧张'), 'bored':('无聊',),
 'impatient':('不耐烦','等不及'), 'emotionally_exhausted':('心累','撑不住','累坏'),
 'confused':('困惑','不明白'), 'interested':('感兴趣','好奇'),
 'disengaged':('不想聊','别烦我'), 'happy':('开心','高兴'), 'sad':('难过','伤心'),
}
POSITIVE={'relieved','interested','happy'}
def language_signal(text, now):
    labels=[]
    # Quoted, hypothetical, other-person and explicitly negated feelings are not self-reports.
    clauses=re.split(r'[，。！？；\n]|但是|不过',re.sub(r'“[^”]*”|「[^」]*」|"[^"]*"','',text))
    for label,words in EMOTIONS.items():
        for clause in clauses:
            if re.search(r'如果|假如|假设|电影|小说|昨天|以前|上次|(?:他|她|朋友|妈妈|爸爸)(?:很|有点|说|觉得)',clause):continue
            matched=False
            for word in words:
                for hit in re.finditer(re.escape(word),clause):
                    prefix=clause[max(0,hit.start()-6):hit.start()]
                    if not re.search(r'(?:不是|没有|并不|不太|不|没|(?<!特)别|不要)(?:说|觉得|感到|那么|很|再|会|为)?$',prefix):matched=True
            if matched:labels.append(label);break
    sentiment=(sum(1 if x in POSITIVE else -1 for x in labels)/len(labels)) if labels else (0.0 if re.search('没事|还好|正常',text) else None)
    return Language(source='explicit_lexical_cues_not_diagnosis', observed_at=now,
        confidence=.8 if labels else (.6 if sentiment is not None else 0),
        explicit_emotion=labels,sentiment=sentiment)

def numeric_features(state):
    result={}
    for name,part in [('face',state.face),('voice',state.voice),('body',state.body)]:
        if part.confidence<.35:continue
        keys={'face':['valence','arousal'], 'voice':['speech_rate','voice_activity'],
              'body':['movement_intensity','hand_movement_intensity','torso_lean','head_down_proxy','shoulder_openness','approach_avoidance']}[name]
        for k in keys:
            value=getattr(part,k)
            if value is not None and math.isfinite(value):result[name+'.'+k]=float(value)
    if state.voice.confidence>=.35:
        for k,value in [('pitch',state.voice.pitch.get('median_hz')),('energy',state.voice.energy.get('rms')),('pause',state.voice.pause.get('ratio'))]:
            if value is not None and math.isfinite(value):result['voice.'+k]=value
    return result

class HumanStateBuffer:
    """Per-owner + stream state, stale evidence expiry, bounded histories and TTL."""
    def __init__(self,memory=None,clock=time.monotonic):
        self.memory=memory;self.clock=clock;self.lock=threading.RLock();self.streams={}

    def clear(self,owner):
        with self.lock:
            for key in list(self.streams):
                if key[0]==owner:self.streams.pop(key,None)

    def update(self,key,*,face=None,voice=None,body=None,text=None,uid=None,consent=False,now=None):
        now=self.clock() if now is None else now
        with self.lock:
            self.streams={k:v for k,v in self.streams.items() if now-v['time']<300}
            if key not in self.streams:
                if len(self.streams)>=128:self.streams.pop(min(self.streams,key=lambda k:self.streams[k]['time']))
                saved=self.memory.user_model(uid) if consent and uid and self.memory else {}
                self.streams[key]={'time':now,'state':HumanState(),'history':deque(maxlen=300),
                    'ema':{},'last_feature':{},'stats':saved.get('baseline',{}),'last_baseline':-1e9,
                    'face_actions':{},'action_count':0,'action_at':None,
                    'last_event':-1e9,'pending_action':None,'reactions':saved.get('reactions',[])[:20]}
            stream=self.streams[key];state=stream['state'];stream['time']=now
            changed=[]
            for name,value,cls in [('face',face,Face),('voice',voice,Voice),('body',body,Body)]:
                if value is not None:
                    value=dict(value);value['observed_at']=now
                    if name=='face':
                        continuous=value.pop('_tracking_continuous',True)
                        scores=action_scores(value.get('facial_blendshapes',{}))
                        valid=bool(scores) and (value.get('detection_confidence') or value.get('confidence',0))>=.5
                        if not valid or not continuous or stream['action_at'] is None or now-stream['action_at']>5:
                            stream['face_actions']={};stream['action_count']=0
                        if valid:
                            dt=now-stream['action_at'] if stream['action_at'] is not None else 1
                            alpha=1-math.exp(-max(dt,0)/.8)
                            stream['face_actions']={k:stream['face_actions'].get(k,v)+alpha*(v-stream['face_actions'].get(k,v)) for k,v in scores.items()}
                            stream['action_count']+=1;stream['action_at']=now
                            value['expression_actions']=stream['face_actions'].copy()
                            value['action_sample_count']=stream['action_count']
                            value['stable_actions']=describe_actions(stream['face_actions']) if stream['action_count']>=3 else []
                    setattr(state,name,cls(**value));changed.append(name)
                elif getattr(state,name).observed_at is not None and now-getattr(state,name).observed_at>(15 if name=='voice' else 5):
                    setattr(state,name,cls())
            if text is not None:state.language=language_signal(text,now)
            elif state.language.observed_at is not None and now-state.language.observed_at>15:state.language=Language()
            features=numeric_features(state)
            # Update a feature once per new modality observation, never once per poll.
            for k,x in features.items():
                if k.split('.')[0] not in changed:continue
                previous=stream['ema'].get(k,x);dt=max(0,now-stream['last_feature'].get(k,now-1))
                alpha=1-math.exp(-dt/2)
                stream['ema'][k]=previous+alpha*(x-previous);stream['last_feature'][k]=now
            current={k:round(stream['ema'].get(k,v),5) for k,v in features.items()}
            history=stream['history']
            if changed:history.append((now,current.copy()))
            while history and now-history[0][0]>120:history.popleft()
            def trend(seconds):
                candidates=[(t,x) for t,x in history if now-t>=seconds]
                if not candidates:return {}
                then,old=candidates[-1]
                return {k:round((v-old[k])/max(now-then,.001),6) for k,v in current.items() if k in old}
            baseline={k:round(v['mean'],5) for k,v in stream['stats'].items() if v['count']>=20 and v.get('span',0)>=120 and k in current}
            delta={k:round(current[k]-v,5) for k,v in baseline.items()}
            state.temporal=Temporal(source='time_aware_ema_personal_statistics',observed_at=now,current=current,
                baseline=baseline,delta=delta,short_term_trend=trend(10),medium_term_trend=trend(30),
                sample_count=len(history),confidence=min(1,len(baseline)/max(1,len(current))),
                stability=1/(1+sum(abs(v) for v in trend(10).values())) if len(history)>1 else None)
            state.uncertainty=[]
            vals=[]
            if state.face.confidence>=.5 and state.face.valence is not None:vals.append(('face',state.face.valence))
            if state.voice.confidence>=.5:
                # SenseVoice emits a label, not probabilities or continuous V/A.
                voice_label=state.voice.emotion_label
                if voice_label in {'SAD','ANGRY','FEARFUL','DISGUSTED'}:vals.append(('voice_label_proxy',-.7))
                elif voice_label=='HAPPY':vals.append(('voice_label_proxy',.7))
            if state.language.confidence>=.5 and state.language.sentiment is not None:vals.append(('language',state.language.sentiment))
            spread=max((v for _,v in vals),default=0)-min((v for _,v in vals),default=0)
            state.cross_modal_consistency=round(max(0,1-spread/2),3) if len(vals)>=2 else None
            state.language.contradiction=len(vals)>=2 and spread>=.65
            if state.language.contradiction:state.uncertainty.append('inconsistent_signals_do_not_infer_deception')
            if not baseline:state.uncertainty.append('personal_baseline_warming_up')
            if state.face.confidence==0 or state.voice.confidence==0:state.uncertainty.append('missing_or_unreliable_modality')
            state.uncertainty.append('scores_not_field_calibrated')
            state.confidence=round(min(.85,sum(x.confidence for x in [state.face,state.voice,state.body,state.language])/4),3)
            shifts=[k for k,d in delta.items() if abs(d) > max(.15,abs(baseline[k])*.35)]
            event='cross_modal_conflict' if state.language.contradiction else 'personal_state_change' if len(shifts)>=2 else 'nonverbal_distress' if 'Crying' in state.voice.audio_events and state.voice.confidence>=.5 else 'stable_or_insufficient_evidence'
            # Hysteresis: keep an event for three seconds; never repeatedly wake Qwen.
            if event!='stable_or_insufficient_evidence':stream['last_event']=now;state.event=event
            elif now-stream['last_event']>3:state.event=event
            pending=stream['pending_action']
            if pending and changed and 1<=now-pending['time']<=30:
                reaction={k:round(v-pending['before'][k],5) for k,v in current.items() if k in pending['before']}
                if reaction:
                    record={'robot_action':pending['strategy'],'human_state_delta':reaction,'causation_proven':False,'confidence':state.confidence}
                    state.interaction.action_reaction=record;stream['reactions']=(stream['reactions']+[record])[-20:];stream['pending_action']=None
            elif pending and now-pending['time']>30:stream['pending_action']=None
            # Five-second independent samples, slow capped updates and bounded outliers.
            if changed and now-stream['last_baseline']>=5:
                for k,x in features.items():
                    if k.split('.')[0] not in changed:continue
                    if consent and k in stream['stats'] and stream['stats'][k].get('persistable') is False:
                        stream['stats'].pop(k)
                    stat=stream['stats'].setdefault(k,{'mean':x,'variance':0.,'count':0,'span':0.,'updated':time.time()})
                    count=stat['count'];gap=max(0,time.time()-stat['updated']);decay=math.exp(-gap/(30*86400))
                    quality=getattr(state,k.split('.')[0]).confidence
                    count=max(0,count*decay);alpha=(1/(count+1) if count<20 else .01)*quality
                    diff=x-stat['mean'];scale=max(.1,math.sqrt(stat['variance']))
                    if count>=20:diff=max(-4*scale,min(4*scale,diff))
                    stat['mean']+=alpha*diff;stat['variance']=(1-alpha)*(stat['variance']+alpha*diff*diff)
                    stat['count']=min(count+quality,10000);stat['span']+=0 if stream['last_baseline']<0 else min(30,now-stream['last_baseline']);stat['updated']=time.time()
                    stat['persistable']=bool(consent)
                stream['last_baseline']=now
                if consent and uid and self.memory:
                    self.memory.user_model(uid,{'baseline':{k:v for k,v in stream['stats'].items() if v.get('persistable',True)},'reactions':stream['reactions'],
                        'personality':{'big_five':None,'confidence':0,'source':'not_inferred'},
                        'relationship':{'trust':None,'source':'not_inferred'},'schema_version':1})
            return state.model_copy(deep=True)

    def record_action(self,key,strategy):
        with self.lock:
            if key in self.streams:
                s=self.streams[key];s['pending_action']={'strategy':strategy,'time':self.clock(),'before':dict(s['state'].temporal.current)}

def response_plan(state, silent=False):
    conflict=state.language.contradiction
    strategy='respect_silence' if silent else 'gentle_check_in' if conflict or state.event in {'personal_state_change','nonverbal_distress'} else 'attentive_response'
    return {'state_interpretation':{'event':state.event,'evidence':state.temporal.delta,'observed':state.compact(),
            'cross_modal_consistency':state.cross_modal_consistency,'uncertainty':state.uncertainty},
        'confidence':state.confidence,'response_strategy':strategy,'verbal_response':'',
        'voice_style':{'speed':.9 if strategy=='gentle_check_in' else 1.,'volume':.8,'warmth':.8},
        'robot_behavior':{'approach':False,'maintain_distance':True,'gesture_intensity':0.,'gaze':'soft','execution_authorized':False},
        'memory_update':{'permanent_emotion_fact':False,'personality_changed':False},'strategy_source':'bounded_fusion_controller'}
