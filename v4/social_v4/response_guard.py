"""Ground generated acknowledgements in controller results, not generated claims."""
import re

COMPLETION=re.compile(r'(?:我(?:已经|已經|已)|已为你|已為你|已帮你|已幫你|已经帮你|已經幫你|已经为你|已經為你|已经|已經).{0,12}(?:打开|打開|关闭|關閉|关掉|關掉|拉上|拉开|拉開|调高|調高|调低|調低|播放|暂停|暫停|发送|發送|拨打|撥打|叫来|叫來|清扫|清掃|设置提醒|設置提醒)')
NEGATED=re.compile(r'没有|沒有|还没|還沒|尚未|不能|不代表|不表示|无法|無法')

def missing_visual_input(speech):
    """Current API has no image input. Do not ask the text model to invent pixels.

    This is an explicit visual-request recognizer, not a universal hallucination detector.
    Questions about a supplied text description remain ordinary dialogue.
    """
    if re.search(r'文字|描述|刚才.*(?:说|告诉)|我说|你说',speech):return False
    return bool(re.search(r'(?:看看|看下|看一下|看一眼|看着|帮我看|你看).{0,60}(?:颜色|外观|样子|好看|脏|穿搭|长什么|怎么样|什么色)',speech))

def unsupported_bereavement_advice(speech,reply):
    if re.search(r'小说|电影|这句话|故事',speech):return False
    loss=re.search(r'(?:猫|狗|宠物|亲人|爸爸|妈妈|父亲|母亲|爷爷|奶奶|外公|外婆|爱人|朋友).{0,20}(?:去世|离世|过世|不在了|病逝|走了)',speech)
    if not loss or re.search(r'(?:想|打算|考虑|要不要).{0,12}(?:再养|领养|新伙伴|新的宠物)',speech):return False
    for clause in re.split(r'[，。！？；\n]',reply):
        if re.search(r'(?:新伙伴|新的宠物|再养一|再买一).{0,12}(?:填补|代替|替代|就好)|(?:填补|代替|替代).{0,12}(?:新伙伴|新宠物)',clause) and not re.search(r'不必|不要|不能|不需要|并不能',clause):return True
    return False


def guard_reply(reply,speech=''):
    secret_recall = re.search(r'密码|验证码',speech) and re.search(r'多少|什么|记得|说过|告诉过',speech)
    asks_for_secret = any(re.search(r'(?:重新|再|直接)?告诉我|提供给我|发给我',c) and not re.search(r'不要|不必|无需|不用|不需要',c) for c in re.split(r'[，。！？；\n]',reply))
    if secret_recall and asks_for_secret:
        return {'accepted':False,'reason':'do_not_request_authentication_secret','reply':'当前可见对话没有这项信息，我不能确定。请不要在聊天中发送密码或验证码。'}
    if unsupported_bereavement_advice(speech,reply):
        return {'accepted':False,'reason':'bereavement_replacement_advice','reply':'失去重要的陪伴会很难受，不必急着让自己释怀。如果你想说说，我愿意听。'}
    for match in COMPLETION.finditer(reply):
        if not NEGATED.search(reply[max(0,match.start()-10):match.start()]):
            return {'accepted':False,'reason':'unsupported_device_completion','reply':'我还没有执行设备操作，需要先确认设备和指令，再由控制器处理。'}
    return {'accepted':True,'reason':None,'reply':reply}
