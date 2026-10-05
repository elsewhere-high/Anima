"""Self-selected communication hints, never an inferred personality diagnosis."""
import itertools
import re

DIMENSIONS = {
    'I': '留出表达空间，少追问，不把简短回答当作拒绝。',
    'E': '自然接话，可以邀请分享一个细节，不催促持续说话。',
    'S': '优先眼前事实、具体例子和可做的小事。',
    'N': '可联系意义和可能性，但不臆测经历。',
    'T': '需要建议时先讲清问题、依据和取舍，仍尊重感受。',
    'F': '先回应具体感受和在意的事，再征求是否需要建议。',
    'J': '需要行动时给清晰的下一小步，不擅自替用户安排。',
    'P': '给少量可选方向和调整空间，不催促定计划。',
}
SUPPORT = {
    'auto': '根据当下话语决定倾听或帮助，不确定时只问一个轻问题。',
    'listen': '以倾听为主，承接具体感受，不主动列建议或解决步骤。',
    'analyze': '简短回应感受后，梳理问题与取舍，给一个可行的小步骤。',
    'explore': '一起讨论可能性，最多提供两个方向，不急着下结论。',
}
SCENARIOS = [
    {'id':'hello','label':'第一次见面','speech':'你好，我们第一次聊天，先轻松认识一下吧。','guide':'自然打招呼，给一个低压力话题入口，不假装熟悉用户。'},
    {'id':'tired','label':'今天有点累','speech':'今天有点累，我想跟你待一会儿。','guide':'先接住疲惫，允许少说话，不自动安排休息、呼吸或任务。'},
    {'id':'joy','label':'分享一件开心事','speech':'今天有件开心的事，想跟你分享。','guide':'自然回应喜悦，可以邀请讲一个细节，不编造具体好消息。'},
    {'id':'decision','label':'有件事拿不定主意','speech':'有件事我拿不定主意，想和你一起理一理。','guide':'先问清具体选择或最在意的条件，不凭人格替用户决策。'},
    {'id':'vent','label':'只想说说心事','speech':'我现在只想倾诉，先别给建议。','guide':'明确接纳倾诉，温和倾听，不提供解决步骤。'},
    {'id':'quiet','label':'想安静一会儿','speech':'我想安静一会儿，请先不要打扰我。','guide':'尊重安静，由既有边界控制器决定保持静默。'},
]

def starter(mbti):
    if not mbti:
        return '你好，我在这里。想随便聊聊，还是说说今天的一件小事？'
    opening = '你好，慢慢说就好。' if mbti[0]=='I' else '你好，很高兴和你聊聊。'
    topic = '今天的一件小事' if mbti[1]=='S' else '最近在意的一件事'
    return opening + f'可以从{topic}开始。'

def catalog():
    return {'types':[{'mbti':''.join(chars),'hints':[DIMENSIONS[c] for c in chars],
                      'opening':starter(''.join(chars))}
                     for chars in itertools.product('EI','SN','TF','JP')],
            'default_opening':starter(None),'scenarios':SCENARIOS}

def dialogue_policy(preferences, speech, history, source='default'):
    mbti=preferences.get('mbti');support=preferences.get('support','auto')
    # Current explicit needs outrank both the saved type and UI defaults.
    if re.search(r'只想(?:倾诉|说说|聊聊)|(?:先|请)?(?:别|不要|不用)给(?:我)?建议|先听我说',speech):
        support='listen';need_source='current_utterance'
    elif re.search(r'(?:帮我|一起)(?:分析|理一理|梳理|想一句|想个办法)|给我(?:一个)?(?:建议|办法)',speech):
        support='analyze';need_source='current_utterance'
    else:need_source='selected_preference'
    turns=sum(1 for role,_ in history if role in {'用户','user'})
    result={'mbti':mbti,'source':source,'phase':'cold_start' if turns<3 else 'adapting',
            'support':support,'need_source':need_source,'response_guidance':SUPPORT[support],
            'style_hints':[DIMENSIONS[c] for c in mbti] if mbti else [],
            'priority':'安静/拒绝与安全边界 > 当前明确要求和自述 > 已表达的实际偏好 > MBTI初始提示',
            'rule':'这是用户自选的初始沟通偏好，不是机器人人设。不得由表情、用词猜类型，不提刻板标签，不编造经历。'}
    scenario=next((s for s in SCENARIOS if s['speech']==speech.strip()),None)
    if scenario:result['situation_guidance']=scenario['guide']
    if turns<3:result['cold_start_guidance']='先回应这句话，只在需要时问一个轻问题；不要做人格访谈，不必提MBTI。'
    return result
