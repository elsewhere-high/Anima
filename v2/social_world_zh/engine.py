import threading,time,copy
from .policy import decide
from .cloud import CloudReasoner
from .affect import coarse_affect

class SocialEngine:
    def __init__(self,predictor,memory):
        self.predictor=predictor;self.memory=memory;self.cloud=CloudReasoner();self.lock=threading.RLock();self.sessions={}
    def forget(self,user_id):
        with self.lock:
            self.memory.forget(user_id);self.sessions={k:v for k,v in self.sessions.items() if k[1]!=user_id}
    def step(self,observation):
        started=time.monotonic();o=observation.model_dump()
        with self.lock:
            persistent=o['identity_verified'] and o['memory_consent'] and o['user_id']!='anonymous'
            now=time.monotonic();key=(o['session_id'],o['user_id'])
            self.sessions={k:v for k,v in self.sessions.items() if now-v['time']<300}
            if len(self.sessions)>=1024 and key not in self.sessions:self.sessions.pop(min(self.sessions,key=lambda k:self.sessions[k]['time']))
            session=self.sessions.get(key,{'time':now,'history':[],'memory':self.memory.empty()})
            mem=self.memory.read(o['user_id']) if persistent else copy.deepcopy(session['memory'])
            for pref in ['preferred_distance','preferred_style']:
                if o[pref] is not None:mem[pref]=o[pref]
            if o['relationship_level'] is not None:mem['relationship']=o['relationship_level'];mem['relationship_explicit']=True
            history=session['history'][-4:]
            priority_event=o['emergency_verified'] or not o['person_present']
            neural=self.predictor.state(history,'' if priority_event else o['speech'])
            if priority_event:
                for value in neural.values():value['source']='not_evaluated_priority_event'
            result=decide(o,neural,mem)
            # Inferred boundaries govern this response only; durable boundaries
            # require the user's explicit statement or structured observation.
            if result['boundary_evidence']=='explicit':mem['boundary_state']=result['boundary_state'];mem['boundary_flags']=result['explicit_boundary_flags']
            interacting=bool(o['speech'].strip() or result['response'])
            mem['interaction_count']+=int(interacting);mem['positive_interactions']+=int(o['positive_feedback'] is True)
            mem['rejection_count']+=int(result['boundary_evidence']=='explicit' and result['boundary_state']!='open')
            mem['recent_actions']=(mem['recent_actions']+[result['action']])[-10:]
            if not mem.get('relationship_explicit'):mem['relationship']='unknown' if mem['interaction_count']==0 else 'first_contact' if mem['interaction_count']==1 else 'acquaintance' if mem['interaction_count']<10 else 'familiar'
            mem['trust']=None
            if persistent:
                if o['memory_note']:mem['memories']=(mem['memories']+[o['memory_note']])[-30:]
                mem['known_topics']=list(dict.fromkeys(mem['known_topics']+o['known_topics']))[-30:]
                self.memory.update(o['user_id'],mem)
            if result['action']=='REMIND' and o['reminder_after_seconds'] and o['reminder_text'] and persistent:
                result['reminder']=self.memory.remind(o['user_id'],o['reminder_after_seconds'],o['reminder_text']);result['response']='已设置提醒。'
            elif result['action']=='REMIND' and not persistent:result['response']='保存提醒需要确认用户身份并允许记忆。'
            if result['action']=='CLOUD_REASON':
                result['reasoning']=self.cloud.reason(o,result)
                if result['reasoning']['status']!='ok' and o['local_reasoning'] and hasattr(self.predictor,'generate_local'):result['reasoning']=self.predictor.generate_local(o['speech'])
                result['response']=result['reasoning']['reply']
            retrieved=self.memory.retrieve(mem,o['speech']+' '+o['current_goal']) if persistent else []
            if result['boundary_state']=='do_not_disturb':willing='explicitly_declined'
            else:willing='unknown'
            result.update(neural=neural,state={'emotion':neural['emotion'],'dialog_act':neural['dialog_act'],'intent':neural['intent'],'attention':o['gaze'],'interaction_willingness':willing,'trust':None,'familiarity':mem['relationship'],'relationship_basis':'explicit' if mem.get('relationship_explicit') else 'interaction_count_heuristic','urgency':'verified_emergency' if o['emergency_verified'] else 'unknown','boundary_state':result['boundary_state'],'current_goal':o['current_goal'],'user_preference':{'distance':mem['preferred_distance'],'style':mem['preferred_style']},'recent_actions':mem['recent_actions']},memory_persisted=persistent,retrieved_memories=retrieved,style={'tone':'gentle' if result['action']=='COMFORT' else mem['preferred_style'],'initiative':0 if result['action'] in {'WAIT','SILENCE'} else .3,'max_length':'short'},action_semantics='controller_request_no_direct_actuation',history_turns_used=len(history))
            if mem['preferred_style']=='silent' and not result['human_request']:result['response']=''
            new_turns=([('用户',o['speech'])] if o['speech'].strip() else [])+([('对方',result['response'])] if result['response'] else [])
            if o['person_present']:self.sessions[key]={'time':now,'history':(history+new_turns)[-4:],'memory':copy.deepcopy(mem)}
            else:self.sessions.pop(key,None)
            result['latency_ms']=(time.monotonic()-started)*1000
            result['state']['sentiment_cped']=coarse_affect(neural['emotion'])
            return result
    def imagine(self,request):
        with self.lock:return self.predictor.imagine(request.history,request.speech,request.candidates)
