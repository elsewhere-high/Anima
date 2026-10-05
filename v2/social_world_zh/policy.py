"""Explicit boundaries and actuator permissions are distinct from learned scores."""
import re
from .adapter import TASK_OPERATIONS
REPLIES={'GREET':'你好，很高兴见到你。','RESPOND':'好的，我听到了。','CLARIFY':'你能再说具体一点吗？','COMFORT':'听起来你有些不好受。如果愿意，我可以听你说。','ENCOURAGE':'真为你高兴，这份努力有了收获。','WAIT':'','SILENCE':'','CHANGE_TOPIC':'好的，我们换个话题。','REMIND':'请确认提醒的时间和内容。','APPROACH':'收到，你希望我靠近一些。','KEEP_DISTANCE':'好的，我会保持距离。','FOLLOW':'收到，你希望我跟着你。','LEAVE':'好的，我先不打扰你了。','OFFER_HELP':'我可以陪你聊聊，也可以帮你安排提醒。','CALL_HUMAN':'收到，我会请求人工协助。','CLOUD_REASON':'这个问题需要进一步分析。','TASK_REQUEST':'收到你的操作要求。','CANCEL_TASK':'收到，我会请求停止当前任务。'}
MOTION={'APPROACH','FOLLOW','LEAVE','KEEP_DISTANCE'}

def explicit_boundary(text):
    """Recognize direct speech; quoted/reporting forms remain model-level hypotheses."""
    s=text.strip()
    if re.search(r'[“”「」]|(?:他说|她说|电影里|电视里|这句话|以前|昨天)|(?:他|她|爸爸|妈妈|爷爷|奶奶|孩子|家人|朋友).{0,4}(?:说|不想|需要|要独处)',s):return None
    if re.search(r'现在(?:可以|能|愿意).{0,4}(?:聊|说话|交流)|(?:不用|不需要)再?(?:保持)?(?:沉默|安静|独处)|恢复对话|不是不想聊|并非不想聊',s):return 'open'
    if re.search(r'(?:不是|并不是|没有)(?:让你|叫你|不想)|不要保持安静|不用保持安静',s):return None
    if re.search(r'(?:别|不要|先别)(?:再)?(?:打扰|出声|说话|问我)|不(?:太)?想(?:聊天|说话)|让我(?:一个人|独处)|请(?:先)?(?:保持)?安静',s):return 'do_not_disturb'
    if re.search(r'(?:别|不要|不用)(?:再)?(?:靠近|过来)|保持.{0,2}距离|离我远|退后|站远',s):return 'keep_distance'
    return None

def decide(o,neural,memory):
    action=neural['policy']['label'];reasons=[]
    explicit=o.get('boundary') or explicit_boundary(o['speech'])
    flags=dict(memory.get('boundary_flags',{'do_not_disturb':memory['boundary_state']=='do_not_disturb','keep_distance':memory['boundary_state']=='keep_distance'}))
    if o.get('boundary')=='open':flags={'do_not_disturb':False,'keep_distance':False}
    elif explicit=='open':flags['do_not_disturb']=False
    elif explicit in flags:
        flags[explicit]=True
        # A single sentence can decline speech AND proximity. Preserve both when
        # later permission only reopens conversation.
        if re.search(r'别靠近|不要靠近|保持.{0,2}距离|离我远|退后|站远',o['speech']):flags['keep_distance']=True
    boundary='do_not_disturb' if flags['do_not_disturb'] else 'keep_distance' if flags['keep_distance'] else 'open'
    # Learned boundary predictions are reported, but cannot silently erase an
    # explicit refusal or manufacture durable user preferences.
    b=neural['boundary']
    direct=not re.search(r'[“”「」]|他说|她说|电影里|电视里|这句话|昨天|以前|不是|并非|没有|不用|(?:他|她|爸爸|妈妈|爷爷|奶奶|孩子|家人|朋友).{0,4}(?:说|不想|需要|要独处)',o['speech'])
    reported=bool(re.search(r'[“”「」]|他说|她说|电影里|电视里|这句话|昨天|以前|不是|并非|没有|(?:他|她|爸爸|妈妈|爷爷|奶奶|孩子|家人|朋友).{0,4}(?:说|不想|需要|要独处)',o['speech']))
    if direct and not explicit and boundary=='open' and b['confidence']>=.90 and b['label'] in {'do_not_disturb','keep_distance'}:
        boundary=b['label'];reasons.append('high_confidence_inferred_boundary')
    if o['emergency_verified']:action='CALL_HUMAN';reasons.append('verified_emergency')
    elif not o['person_present']:action='SILENCE';reasons.append('no_person')
    elif boundary=='do_not_disturb':action='SILENCE';reasons.append('boundary_priority')
    elif boundary=='keep_distance' and (explicit=='keep_distance' or action in {'APPROACH','FOLLOW'}):action='KEEP_DISTANCE';reasons.append('boundary_priority')
    elif o['asr_confidence']<.65:action='CLARIFY';reasons.append('uncertain_asr')
    elif re.match(r'^(?:不用了|不用不用|不必了|谢谢不用|算了不用)',o['speech'].strip()):
        action='WAIT' if o['current_task'] in {'conversation','greeting',''} else 'CANCEL_TASK';reasons.append('explicit_polite_refusal')
    elif reported:
        if action in MOTION|{'SILENCE','TASK_REQUEST','CANCEL_TASK','REMIND','CALL_HUMAN'}:
            action='CLARIFY';reasons.append('reported_or_negated_command_requires_clarification')
        elif neural['policy']['confidence']<.55:action='CLARIFY';reasons.append('uncertain_policy')
    else:
        intent=neural['intent'];label=intent['label']
        confirmed=o.get('confirmed_task_intent')
        # Device routing requires a confident supervised intent and an explicit
        # request; raw intent heads are out of domain on arbitrary conversations.
        if o['task_execution_authorized'] and o['target_device'] and confirmed in TASK_OPERATIONS:
            action='CANCEL_TASK' if confirmed=='cancel_current_task' else 'TASK_REQUEST';reasons.append('explicit_confirmed_device_intent')
        elif intent['confidence']>=.75 and re.search(r'打开|关闭|关掉|调高|调低|播放|暂停|把.+(?:灯|音量)|扫地|开灯|关灯',o['speech']) and label.startswith(('iot_','audio_','play_')):
            action='TASK_REQUEST';reasons.append('supervised_home_intent')
        elif neural['policy']['confidence']<.55:action='CLARIFY' if o['speech'] else 'WAIT';reasons.append('uncertain_policy')
    response=REPLIES[action]
    if 'explicit_polite_refusal' in reasons and action=='WAIT':response='好的，有需要再叫我。'
    motion_requested=action in MOTION
    motion_authorized=motion_requested and o['motion_authorized'] and boundary!='do_not_disturb' and not(action in {'APPROACH','FOLLOW'} and boundary=='keep_distance')
    task_requested=action in {'TASK_REQUEST','CANCEL_TASK'}
    task_intent='cancel_current_task' if action=='CANCEL_TASK' else neural['intent']['label']
    if 'explicit_confirmed_device_intent' in reasons:task_intent=o['confirmed_task_intent']
    task_authorized=task_requested and o['task_execution_authorized'] and o['asr_confidence']>=.65 and bool(o['target_device']) and o['confirmed_task_intent']==task_intent and task_intent in TASK_OPERATIONS
    if motion_requested and not motion_authorized and action in {'APPROACH','FOLLOW'}:response='我现在还不能移动，可以先在这里陪你说话。'
    if task_requested and not task_authorized:response='请先确认要操作哪台设备，以及希望它做什么。'
    return {'action':action,'response':response,'boundary_state':boundary,'explicit_boundary_flags':flags,'boundary_evidence':'explicit' if explicit else 'inferred' if 'high_confidence_inferred_boundary' in reasons else 'stored','overrides':reasons,'motion':{'requested':motion_requested,'authorized':motion_authorized,'command':action if motion_authorized else 'HOLD','min_distance_m':memory['preferred_distance'],'requires_navigation_collision_check':True,'expires_after_ms':1000},'task':{'requested':task_requested,'authorized':task_authorized,'intent':task_intent if task_requested else None,'target_device':o['target_device'],'execution_status':'not_executed','requires_device_and_slot_confirmation':True},'human_request':action=='CALL_HUMAN'}
