import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EMOTIONS=['neutral','anger','negative-other','depress','relaxed','worried','positive-other','happy','astonished','sadness','fear','disgust','grateful']
DIALOG_ACTS=['statement-non-opinion','statement-opinion','question','answer','other','command','acknowledge','irony','interjection','comfort','disagreement','quotation','conventional-closing','reject','agreement','apology','thanking','appreciation','greeting']
INTENTS=['datetime_query','iot_hue_lightchange','transport_ticket','takeaway_query','qa_stock','general_greet','recommendation_events','music_dislikeness','iot_wemo_off','cooking_recipe','qa_currency','transport_traffic','general_quirky','weather_query','audio_volume_up','email_addcontact','takeaway_order','email_querycontact','iot_hue_lightup','recommendation_locations','play_audiobook','lists_createoradd','news_query','alarm_query','iot_wemo_on','general_joke','qa_definition','social_query','music_settings','audio_volume_other','calendar_remove','iot_hue_lightdim','calendar_query','email_sendemail','iot_cleaning','audio_volume_down','play_radio','cooking_query','datetime_convert','qa_maths','iot_hue_lightoff','iot_hue_lighton','transport_query','music_likeness','email_query','play_music','audio_volume_mute','social_post','alarm_set','qa_factoid','calendar_set','play_game','alarm_remove','lists_remove','transport_taxi','recommendation_movies','iot_coffee','music_query','play_podcasts','lists_query']
BOUNDARIES=['unspecified','do_not_disturb','keep_distance','open']
POLICIES=['GREET','RESPOND','CLARIFY','COMFORT','ENCOURAGE','WAIT','SILENCE','CHANGE_TOPIC','REMIND','APPROACH','KEEP_DISTANCE','FOLLOW','LEAVE','OFFER_HELP','CALL_HUMAN','CLOUD_REASON','TASK_REQUEST','CANCEL_TASK']
DOMAINS=['景点','餐馆','酒店','地铁','出租']
HEADS={'emotion':EMOTIONS,'dialog_act':DIALOG_ACTS,'intent':INTENTS,'boundary':BOUNDARIES,'policy':POLICIES,'next_emotion':EMOTIONS,'next_act':DIALOG_ACTS,'task_domain':DOMAINS}
MAX_LENGTH=256

def state_text(history,speech):
    turns='\n'.join(f'{role}：{text}' for role,text in history[-4:])
    return f'任务：理解当前中文对话状态。\n历史：\n{turns}\n当前用户：{speech}\n当前状态：'

def transition_text(history,speech,candidate):
    turns='\n'.join(f'{role}：{text}' for role,text in history[-4:])
    return f'任务：预测用户在候选回应之后的下一轮状态。\n历史：\n{turns}\n当前用户：{speech}\n候选回应：{candidate}\n预测下一轮用户状态：'
