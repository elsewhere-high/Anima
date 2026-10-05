"""Pinned real Mandarin corpora, official partitions, masked labels, no future text."""
import json,sys,hashlib,random,zipfile,collections
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from social_world_zh.spec import *
random.seed(20260925)
out={s:[] for s in ['train','validation','test']}

def add(split,source,id,text,labels,**meta):
    out[split].append(dict(id=f'{source}:{id}',source=source,text=text,labels=labels,**meta))

def choose(rows,n,seed):
    if len(rows)<=n:return rows
    return random.Random(seed).sample(rows,n)

# Real dialogue turns: dialogue identifiers never appear in the model input.
for si,(split,fn) in enumerate([('train','train_split.csv'),('validation','valid_split.csv'),('test','test_split.csv')]):
    df=pd.read_csv(ROOT/'data/raw/cped'/fn).fillna('')
    states=[];transitions=[]
    for (tv,did),g in df.groupby(['TV_ID','Dialogue_ID'],sort=False):
        rows=g.to_dict('records')
        for i,r in enumerate(rows):
            speech=str(r['Utterance']).strip()
            if not speech or r['Emotion'] not in EMOTIONS or r['DA'] not in DIALOG_ACTS:continue
            history=[('用户' if x['Speaker']==r['Speaker'] else '对方',str(x['Utterance'])) for x in rows[max(0,i-4):i]]
            metadata=dict(dialogue=f'{tv}:{did}',home=r['Scene']=='home',tv=str(tv))
            states.append((f'{tv}:{did}:{i}',state_text(history,speech),{'emotion':EMOTIONS.index(r['Emotion']),'dialog_act':DIALOG_ACTS.index(r['DA'])},metadata))
            if i+2<len(rows) and rows[i+1]['Speaker']!=r['Speaker'] and rows[i+2]['Speaker']==r['Speaker']:
                future=rows[i+2]
                if future['Emotion'] not in EMOTIONS or future['DA'] not in DIALOG_ACTS:continue
                candidate=str(rows[i+1]['Utterance'])
                transitions.append((f'{tv}:{did}:{i}',transition_text(history,speech,candidate),{'next_emotion':EMOTIONS.index(future['Emotion']),'next_act':DIALOG_ACTS.index(future['DA'])},dict(**metadata,current_emotion=EMOTIONS.index(r['Emotion']),current_act=DIALOG_ACTS.index(r['DA']),history=history,speech=speech,candidate=candidate)))
    # Uniform sampling preserves natural prevalence; imbalance handled by loss weights.
    for source,rows,n in [('cped_state',states,[14000,1300,2400][si]),('cped_transition',transitions,[7000,900,1600][si])]:
        for id,text,labels,meta in choose(rows,n,410+si):add(split,source,id,text,labels,**meta)

for split in out:
    df=pd.read_parquet(ROOT/'data/raw/massive'/f'{split}.parquet')
    for r in df.to_dict('records'):
        add(split,'massive_zh',str(r['id']),state_text([],r['utt']),{'intent':int(r['intent'])})

# CrossWOZ domain supervision comes only from the CURRENT user dialog acts.
for si,(split,fn) in enumerate([('train','train.json.zip'),('validation','val.json.zip'),('test','test.json.zip')]):
    with zipfile.ZipFile(ROOT/'data/raw/crosswoz'/fn) as z: data=json.loads(z.read(z.namelist()[0]))
    examples=[]
    for did,d in data.items():
        history=[]
        for i,m in enumerate(d['messages']):
            domains=[x[1] for x in m['dialog_act'] if x[1] in DOMAINS]
            if m['role']=='usr' and domains:
                domain=collections.Counter(domains).most_common(1)[0][0]
                examples.append((f'{did}:{i}',state_text(history,m['content']),{'task_domain':DOMAINS.index(domain)},dict(dialogue=did)))
            history.append(('用户' if m['role']=='usr' else '对方',m['content']))
    for id,text,labels,meta in choose(examples,[3000,300,500][si],55+si):add(split,'crosswoz',id,text,labels,**meta)

# Synthetic home boundary/policy supervision: reviewed phrase families with disjoint
# validation/test wording. Counts and provenance are explicitly separated from real data.
families=[
 ('SILENCE','do_not_disturb',['先别跟我说话','让我一个人待会儿','我现在不想聊天','不要再问我了','请安静一会儿','我想独处，你先别打扰','别吵，我要休息','今天没心情聊','不用陪我说话，我需要安静','我正在开会，先别出声','此刻不方便交流','暂时别和我搭话']),
 ('KEEP_DISTANCE','keep_distance',['请离我远一点','不要再靠近我','你站得太近了，退后些','请保持一点距离','别贴着我站','离开我的私人空间','你停在那里，不要过来','往后一点，我不舒服','别往我这边走','和我隔远些好吗','不要紧挨着我','咱们保持距离就好']),
 ('RESPOND','open',['现在可以聊天了','刚才让你安静，现在继续吧','我休息好了，可以说话了','你可以重新跟我讲话','不用再保持沉默了','刚才不方便，现在没事了','继续刚才的话题吧，我愿意聊了','我已经开完会，可以交流','不需要独处了，陪我说说话','现在不用避着我了','我改变主意，咱们聊聊','可以恢复对话了']),
 ('GREET','unspecified',['早上好呀','嗨，很高兴见到你','你好，小助手','下午好','晚上好，机器人','哈喽，你在吗','我回家啦','初次见面，你好','早安，小伙伴','你好啊，今天精神不错','见到你真好，嗨','嗨，我来了']),
 ('COMFORT','unspecified',['今天工作不顺心，我挺难过的','我被朋友误会了，心里很委屈','最近总是觉得很孤单','考试没考好，我有点失落','和家人吵架了，好难受','今天受批评了，心情不好','我想说说心里的烦恼','压力很大，我需要有人听听','我的宠物走丢了，我很伤心','刚才的事让我挺沮丧','我遇到了挫折，想倾诉','我一个人在家，有些寂寞']),
 ('ENCOURAGE','unspecified',['我今天考试通过了','我终于完成这个项目了','我拿到了期待的录取通知','今天升职了，好开心','我学会了一首新曲子','我锻炼坚持了一个月','我做的菜被大家夸了','我比赛拿到了奖牌','我终于把问题解决了','我今天达成了小目标','努力有回报了，我通过考核啦','我做成功了，想分享这个好消息']),
 ('CHANGE_TOPIC','unspecified',['不聊这个了，换个话题','我不想谈工作，聊点别的','这件事先不说了','咱们换个轻松的话题吧','别再提我的考试了','这个话题到此为止吧','聊聊其他事情好吗','不要总说这件事','换个内容聊，我不喜欢这个','不谈这个问题，讲点别的','这话题让我不舒服，换掉吧','先翻篇吧，说其他的']),
 ('WAIT','unspecified',['等我一下，我马上回来','稍等，让我想一想','你先等着，我拿个东西','暂停一下，待会儿继续','让我考虑考虑','我忙完就来，等一下','别着急，给我一点时间','请先等两分钟','我先接电话，一会儿再聊','停一会儿让我整理思路','等我把手头事情做完','先缓一缓，我准备一下']),
 ('LEAVE','unspecified',['再见，我要出门了','拜拜，下次再聊','今天就聊到这里吧','你可以离开这个房间了','先这样，再见','我该睡觉了，晚安','你回充电座去吧','请离开，让我休息','谢谢陪伴，今天结束了','对话结束，下次见','你先回去吧','到这里就好，拜拜']),
 ('FOLLOW','unspecified',['跟我去厨房','请跟着我走','随我去客厅','你跟在我后面吧','陪我走到门口','请跟我到书房','我走到哪你跟到哪','和我一起去那边','跟上我的脚步','随我进餐厅','沿着我走的路线跟过来','你在后面跟着我就行']),
 ('APPROACH','unspecified',['过来一点，我听不清','请到我这边来','靠近一点吧','来我旁边','你过来一下','朝我走近些','你可以靠过来','到沙发这边来找我','走到我面前好吗','往我这边挪一点','请移动到我身边','过这儿来，离我近些']),
 ('OFFER_HELP','unspecified',['我不知道你能帮我什么','你有哪些本领','你可以做哪些事情','介绍一下你的功能','我需要一点帮助','你能帮帮我吗','有什么你能协助的','我遇到点小麻烦','能为我提供哪些服务','你能协助我处理什么','我想了解你的能力','我需要搭把手']),
 ('CALL_HUMAN','unspecified',['帮我叫一下家人','我需要真人来帮忙','请通知工作人员过来','替我联系护理员','我想请人来协助','帮我找个能处理的人','叫一下值班人员','请家属来一趟','能让服务人员过来吗','我希望由真人接手','请找我的照护者','需要人来现场帮忙']),
 ('CLOUD_REASON','unspecified',['朋友三天不理我，帮我分析该怎么办','给我讲讲丝绸之路的历史','解释一下量子力学是什么','帮我分析这段复杂的人际关系','我该怎么和同事沟通这个矛盾','给我写一首关于秋天的诗','帮我想一份详细的旅行方案','我想听一个有趣的长故事','如何理解这篇文章的深层含义','请比较不同的教育理念','帮我分析双方争执背后的原因','能详细解释人工智能的发展吗']),
 ('CANCEL_TASK','unspecified',['取消刚才的任务','不要执行刚才的指令了','我改主意了，停止任务','把刚才的操作撤销','这个事情不用做了','请终止当前任务','取消刚才的安排','刚刚那个要求作废','现在停止执行','别继续做这件事','刚才说错了，取消','撤回我的上一个要求']),
 ('CLARIFY','unspecified',['把那个弄一下','就是那个东西，你懂吧','帮我处理一下那边','那个，算了，又不是','你帮我那个一下','我忘了要说什么','把它调整一下','就按那个来吧','你知道我指什么吗','那个什么，嗯……','帮我把那里搞好','照之前那样弄']),
 ('RESPOND','unspecified',['好的，我知道了','没关系，你不用道歉','谢谢，我已经收到','我只是随便说说','我没有不想聊天，只是不知道说什么','我不是让你保持安静','我并不是叫你离开','不用离我那么远','他说不要靠近，这句话是什么意思我知道','电影里有人说别打扰我','我不需要你帮我联系任何人','我说的是以前不想说话']),
 ('REMIND','unspecified',['提醒我明天带雨伞','五分钟后叫我喝水','下午三点提醒我开会','晚上八点提醒我关窗','十分钟后告诉我烤箱好了','明早七点叫我起床','半小时后提醒我休息','周末提醒我买牛奶','过一会儿提醒我取快递','到九点提醒我看节目','明天上午提醒我交材料','十五分钟后提醒我出门']),
 ('TASK_REQUEST','unspecified',['帮我打开客厅灯','把空调温度调高一点','请关掉电视','打开扫地机器人','把窗帘拉上','播放一点轻音乐','降低音箱的音量','帮我把台灯调暗','将卧室的灯关掉','给咖啡机通电','把走廊灯打开','关闭风扇'])]
contexts=[[],[('对方','需要我陪你聊一会儿吗？')],[('用户','我回家了。'),('对方','欢迎回来，有什么需要吗？')],[('对方','我在这里等你。'),('用户','好。')]]
for fi,(policy,boundary,phrases) in enumerate(families):
    for pi,phrase in enumerate(phrases):
        split='train' if pi<8 else 'validation' if pi<10 else 'test'
        for ci,history in enumerate(contexts):
            add(split,'home_synthetic',f'{fi}:{pi}:{ci}',state_text(history,phrase),{'policy':POLICIES.index(policy),'boundary':BOUNDARIES.index(boundary)},family=policy,synthetic=True)
# Hard contrast cases: explicit cancellation/resumption and quoted speech.
contrasts={
 'train':[('别打扰我','现在可以聊了','RESPOND','open'),('你能靠近吗','不用了，站远点','KEEP_DISTANCE','keep_distance'),('陪我说说话','我改主意了，先安静吧','SILENCE','do_not_disturb'),('我不想说话','我说的是昨天，今天可以聊','RESPOND','open')],
 'validation':[('我要独处','现在不需要独处了','RESPOND','open'),('请过来','还是不要靠近了','KEEP_DISTANCE','keep_distance')],
 'test':[('让我安静一会','我缓过来了，继续陪我聊','RESPOND','open'),('你到旁边来','等等，我想保持距离','KEEP_DISTANCE','keep_distance'),('我现在想聊天','又有事了，请先别出声','SILENCE','do_not_disturb')]}
for split,rows in contrasts.items():
    for i,(prior,speech,pol,bd) in enumerate(rows):add(split,'home_synthetic',f'contrast:{i}',state_text([('用户',prior),('对方','好的。')],speech),{'policy':POLICIES.index(pol),'boundary':BOUNDARIES.index(bd)},synthetic=True)

# Remove exact input overlap with earlier partitions, keeping the held-out set intact.
# Test first prevents training on repeated utterances found in public corpus splits.
seen=set();removed=collections.Counter()
for split in ['test','validation','train']:
    clean=[]
    for r in out[split]:
        key=hashlib.sha256(r['text'].encode()).hexdigest()
        if key in seen:removed[split]+=1;continue
        seen.add(key);clean.append(r)
    out[split]=clean
folder=ROOT/'data/processed';folder.mkdir(exist_ok=True)
manifest={'seed':20260925,'max_length':MAX_LENGTH,'heads':HEADS,'removed_exact_input_duplicates':dict(removed),'splits':{}}
for split,rows in out.items():
    random.Random(73).shuffle(rows)
    path=folder/f'{split}.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    manifest['splits'][split]={'count':len(rows),'sources':dict(collections.Counter(r['source'] for r in rows)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest['splits'],indent=2))
