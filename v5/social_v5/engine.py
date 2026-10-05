"""Controller-preserving orchestration of text, visual evidence and memory."""
import re, time
from social_v4.engine import CONVERSATION_ACTIONS
from social_v4.response_guard import guard_reply,missing_visual_input
from social_world_zh.engine import SocialEngine as OriginalEngine
from .memory import safe_text
from .personality import dialogue_policy
from .human_state import HumanState
from .temporal import language_signal,response_plan

def guard_name_echo(reply,speech,memories):
    sources=[speech]+[m.split('] ',1)[-1] for m in memories]
    for source in sources:
        match=re.match(r'^我(?:叫|的名字是)([\u4e00-\u9fffA-Za-z·]{1,20})(?=$|[，。；！])',source)
        if match:
            name=match[1]
            reply=re.sub(r'^我(?:叫|是)'+re.escape(name)+r'(?=$|[，。；！])','你好，'+name,reply)
    return reply

class SocialEngine(OriginalEngine):
    def __init__(self,predictor,memory):
        super().__init__(predictor,memory)
        from .care import CareService
        from .robot import RobotGateway
        self.care=CareService(memory);self.robot=RobotGateway()

    def step(self,observation,visual=None,preferences=None,preference_source='default',human_state=None):
        started=time.monotonic()
        from .care import fast_result
        event=self.care.preflight(observation)
        if event:
            result=fast_result(event);result['latency_ms']=(time.monotonic()-started)*1000;return result
        with self.lock:
            key=(observation.session_id,observation.user_id);session=self.sessions.get(key)
            history=list(session['history']) if session and time.monotonic()-session['time']<300 else []
            persistent=observation.identity_verified and observation.memory_consent and observation.user_id!='anonymous'
            writes={'writes':[],'reason':'no_consent_or_unverified'}
            forget_reply=None
            command=re.fullmatch(r'(?:请)?(?:忘掉|忘记|删除)(.{1,80}?)[。！!]?',observation.speech.strip())
            if command and persistent and observation.asr_confidence>=.65:
                target=command[1]
                if target in {'所有记忆','全部记忆','我的所有记忆','关于我的所有记忆'}:
                    self.forget(observation.user_id);forget_reply='已删除你的长期记忆和提醒，并清空短期上下文。'
                else:
                    target=re.sub(r'^我的|^关于我(?:的)?','',target).replace('的记忆','').replace('这件事','').strip()
                    matches=[r for r in self.memory.list(observation.user_id,limit=2000) if target and (target in r['slot'] or target in r['text'])]
                    for row in matches:self.memory.delete_record(observation.user_id,row['id'])
                    forget_reply='已删除相关记忆，并清空短期上下文。' if matches else '没有找到明确对应的记忆。你可以在记忆列表里选择要删除的条目。'
                self.sessions={k:v for k,v in self.sessions.items() if k[1]!=observation.user_id};history=[]
                writes={'writes':[],'reason':'explicit_forget_request'}
            if persistent and observation.person_present and observation.asr_confidence>=.65 and not forget_reply:
                writes=self.memory.capture(observation.user_id,observation.session_id,observation.speech,observation.memory_note)
            result=super().step(observation.model_copy(update={'local_reasoning':False,'memory_note':None}))
            memory_question=bool(re.search(r'记得|我.{0,30}(?:哪天|哪儿|哪里|哪|几|什么|多少)|(?:以前|上次|之前).{0,30}(?:说|聊|告诉)',observation.speech))
            if (memory_question and not observation.emergency_verified and not observation.task_execution_authorized
                    and not observation.motion_authorized and not observation.reminder_after_seconds
                    and not re.search(r'提醒我|设置提醒|帮我定',observation.speech)
                    and result['boundary_state']=='open' and observation.person_present and observation.asr_confidence>=.65):
                result.update(action='RESPOND',human_request=False)
                result['task'].update(requested=False,authorized=False,intent=None)
                result['motion'].update(requested=False,authorized=False,command='HOLD')
                result['overrides'].append('memory_question_is_not_action_request')
            action=result['action'];conversational=action in CONVERSATION_ACTIONS or action=='CLARIFY'
            if action=='CLOUD_REASON' and result.get('reasoning',{}).get('status')!='ok':conversational=True
            if action=='TASK_REQUEST' and not result['task']['authorized']:conversational=True
            if action=='CALL_HUMAN' and not observation.emergency_verified:
                result['human_request']=False;result['human_assistance']={'status':'unconfirmed_suggestion','authorized':False};conversational=True
            allowed=(conversational and observation.person_present and bool(observation.speech.strip()) and observation.asr_confidence>=.65 and not observation.emergency_verified and result['boundary_state']!='do_not_disturb' and result['state']['user_preference']['style']!='silent')
            evidence={'status':'no_visual_input','emotion_is_not_ground_truth':True}
            if visual:
                faces=visual['faces']
                if len(faces)!=1:evidence['status']='no_face' if not faces else 'multiple_faces_no_speaker_binding'
                else:
                    face=faces[0];candidate=face['identity'].get('candidate_user_id')
                    if candidate and candidate!=observation.user_id:evidence['status']='different_member_no_speaker_binding'
                    else:evidence={'status':'single_visible_face','expression':face['expression'],'speaker_identity_verified':False,'emotion_is_not_ground_truth':True}
            result['state']['facial_expression']=evidence
            human_state=human_state or HumanState(language=language_signal(observation.speech,time.monotonic()))
            human_state.language.semantic_emotion=result['neural'].get('emotion',{})
            human_state.language.intention=result['neural'].get('intent',{}).get('label')
            silent=result['boundary_state']=='do_not_disturb' or result['state']['user_preference']['style']=='silent' or not observation.person_present
            plan=response_plan(human_state,silent)
            result['human_state']=human_state.model_dump()
            # A nonverbal event is actionable evidence even with no recognized words.
            if not observation.speech.strip() and human_state.event=='nonverbal_distress' and not silent and not observation.emergency_verified:
                result['response']='我在这里。你想让我安静陪着，还是聊一会儿？'
                result['action']='RESPOND'
            personality=dialogue_policy(preferences or {},observation.speech,history,preference_source)
            result['state']['dialogue_profile']=personality
            result['state']['emotion_source']='text';result['state']['fusion']={'strategy':'time_aware_separate_evidence_explicit_conflict','human_state_available':True,'no_automatic_action_authority':True}
            result['dialogue']={'status':'controller_template','action_authority':False,'history_turns_used':0}
            # A completed local memory deletion needs its own receipt even when
            # the neural policy misclassifies the verb as a device request.
            if forget_reply and observation.person_present and not observation.emergency_verified:
                result['task'].update(authorized=False,requested=False,intent=None);result['motion'].update(authorized=False,requested=False,command='HOLD');result['human_request']=False
                silent=result['boundary_state']=='do_not_disturb' or result['state']['user_preference']['style']=='silent'
                result['action']='SILENCE' if silent else 'RESPOND';result['response']='' if silent else forget_reply
                result['dialogue']={'status':'memory_deletion_receipt','reply':forget_reply,'action_authority':False,'history_turns_used':0}
                allowed=False
            if allowed:
                policy={'action':action,'style':result['state']['user_preference']['style'],'boundary':result['boundary_state'],'emotion_is_uncertain_hypothesis':True,'visual_evidence':evidence}
                from .conversation import turn_plan
                conversation=turn_plan(observation.speech,history,human_state,personality)
                policy['conversation']=conversation
                plan['conversation']=conversation
                policy['dialogue_profile']=personality
                policy['human_state']=human_state.compact()
                policy['response_strategy']=plan['response_strategy']
                policy['home_companion']={'listen_before_advice':True,'one_question_at_a_time':True,'avoid_repeated_generic_reassurance':True,'support_real_world_relationships':True,'never_claim_completed_calls_or_devices':True,'medication_changes_require_professional':True,'do_not_infer_dementia_or_diagnosis':True}
                if persistent:
                    user_model=self.memory.user_model(observation.user_id)
                    policy['user_model']={'communication_preferences':{k:round(v['confidence'],2) for k,v in user_model.get('communication_preferences',{}).items() if v['observations']>=3},'personality':'unknown'}
                if action=='TASK_REQUEST':policy['设备执行尚未授权，只可询问或解释']=True
                if action=='CALL_HUMAN':policy.update(action='RESPOND',no_human_contact_sent=True)
                facial_question=bool(re.search(r'(?:表情|看我的脸|我看起来|我看上去)',observation.speech))
                from .conversation import grounded_wording
                wording=grounded_wording(history) if conversation.get('compose_utterance') else None
                mbti_question=bool(re.search(r'我(?:的)?\s*(?:mbti|人格类型)|我(?:是|属于).{0,8}(?:mbti|人格类型)',observation.speech,re.I)
                    and (re.search(r'什么|哪|记得|知道|是不是|[？?]',observation.speech) or re.fullmatch(r'我的\s*(?:mbti|人格类型)',observation.speech.strip(),re.I)))
                if forget_reply:
                    generated={'status':'memory_deletion_receipt','reply':forget_reply,'action_authority':False}
                elif mbti_question:
                    kind=personality.get('mbti')
                    saved=self.memory.dialogue_preferences(observation.user_id).get('mbti') if persistent else None
                    reply=(f'你设置的 MBTI 是 {kind}。'+('已保存在你的成员档案里，我会持续参考它调整交流方式；你当下的需要优先。' if saved==kind else '当前会参考它交流；开启长期记忆并保存后，下次登录也会沿用。')) if kind else '当前没有读取到你设置的 MBTI。请在聊天方式里选择；开启长期记忆后会自动保存到你的成员档案。'
                    generated={'status':'member_profile_recall','reply':reply,'action_authority':False}
                elif conversation['mode']=='adjust_style':
                    generated={'status':'communication_feedback_receipt','reply':'好，我少问一些，接着听你说。','action_authority':False}
                elif wording:
                    generated={'status':'grounded_user_wording','reply':wording,'action_authority':False}
                elif facial_question:
                    e=evidence.get('expression',{})
                    if evidence['status']=='single_visible_face' and human_state.face.stable_actions:
                        reply='连续画面里检测到'+ '、'.join(human_state.face.stable_actions[:3])+'。这是面部动作线索，不一定代表你的真实感受。'
                    elif e.get('status')=='expression_hypothesis':reply=f"人脸模块捕捉到偏向{e['label_zh']}的线索，不过表情不一定代表你的真实感受。你愿意说说现在的感觉吗？"
                    elif evidence['status']=='multiple_faces_no_speaker_binding':reply='画面里有多个人，我还不能确定你指的是谁。请让要识别的人单独入镜。'
                    else:reply='当前没有足够清晰且能对应到你的表情线索。可以面向摄像头重新采集，也可以直接告诉我你的感受。'
                    generated={'status':'grounded_face_observation','reply':reply,'action_authority':False}
                elif missing_visual_input(observation.speech):
                    generated={'status':'capability_boundary','reply':'目前视觉模块只分析人脸表情和已登记成员，不能判断物品颜色或外观。你可以用文字描述。','action_authority':False}
                else:generated=self.predictor.generate_dialogue(history,observation.speech,result['retrieved_memories'],policy)
                result['dialogue']={**generated,'history_turns_used':generated.get('history_messages_used',min(24,len(history)))}
                if generated.get('reply'):
                    checked=guard_reply(generated['reply'],observation.speech)
                    from .conversation import remove_repeated_questions
                    checked['reply']=remove_repeated_questions(checked['reply'],history,conversation,observation.speech)
                    corrected=guard_name_echo(checked['reply'],observation.speech,result['retrieved_memories'])
                    if corrected!=checked['reply']:checked.update(reply=corrected,reason='user_name_not_assistant_identity')
                    result['response']=checked['reply'];result['dialogue'].update(reply=checked['reply'],grounding_guard=checked['reason'])
            if 'sentiment' in result['neural']:result['state']['sentiment_cped']=result['neural']['sentiment']
            if observation.person_present and key in self.sessions:
                turns=[] if forget_reply else ([('用户',observation.speech)] if observation.speech.strip() and safe_text(observation.speech) else [])+([('对方',result['response'])] if result['response'] and safe_text(result['response']) else [])
                self.sessions[key]['history']=(history+turns)[-24:]
            result['memory']={**writes,'short_term_turns':len(self.sessions.get(key,{}).get('history',[])),'short_term_idle_ttl_seconds':300,'long_term_enabled':persistent,'retrieved_count':len(result['retrieved_memories']),'raw_images_stored':False}
            if re.search(r'你(?:在|是|就是)?(?:撒谎|装的|骗人)|你有(?:抑郁症|焦虑症)',result['response']):
                result['response']='我还不能确定你的感受。你愿意说说，或者让我安静陪着你吗？'
            plan['verbal_response']=result['response'];result['response_plan']=plan
            result['forecast_enabled']=False;result['version']='5.2.0';result['latency_ms']=(time.monotonic()-started)*1000
            return result
