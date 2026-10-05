"""Explicit synthetic curriculum for observed dialogue failures; no test label edits."""
import sys,json,hashlib,itertools,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from transformers import AutoTokenizer
from social_v4.dialogue import SYSTEM,encode_example,PROMPT_VERSION

def digest(s):return hashlib.sha256(s.encode()).hexdigest()

def main():
    folder=ROOT/'data/dialogue_repair_v2';folder.mkdir(exist_ok=True)
    if (folder/'manifest.json').exists():raise RuntimeError('Corpus already exists')
    tokenizer=AutoTokenizer.from_pretrained(ROOT.parent/'v2/models/qwen35_2B',local_files_only=True)
    data={s:[] for s in ['train','validation','test']};synthetic=[]
    def add(family,index,turns,required=None,required_any=None,forbidden=None):
        messages=[{'role':'user' if i%2==0 else 'assistant','content':t} for i,t in enumerate(turns)]
        assert len(messages)%2==0
        synthetic.append({'id':f'grounded:{family}:{index}','source':'grounded_authored','family':family,'group':f'{family}:{index}','messages':messages,'synthetic':True,'required':required or [],'required_any':required_any or [],'forbidden':forbidden or []})
    objects=['折叠伞','便签本','围巾','跳绳','旅行手册','收音机','小风扇','充电线','手套','画笔','棋盘','水壶']
    places=['鞋柜上层','书房第二个抽屉','餐桌旁的木箱','储物间的上层架子','卧室窗边的小柜','厨房门后的挂钩','客房床头柜','走廊尽头的篮子','阳台的矮柜','书架最下面一层','客厅沙发旁的小桌','门边的收纳袋']
    for i,(obj,place) in enumerate(itertools.product(objects,places)):
        other=objects[(objects.index(obj)+3)%len(objects)];other_place=places[(places.index(place)+5)%len(places)]
        if i%3==0:turns=[f'我把{obj}放在{place}了。','好，这次聊天里我知道了。',f'我刚才说{obj}放在哪里？',f'你说{obj}放在{place}。']
        elif i%3==1:turns=[f'{obj}在{place}，{other}在{other_place}。','你说了两件物品的位置。',f'我要找的是{obj}，它在哪里？',f'{obj}在{place}。']
        else:turns=[f'{obj}原来放在{other_place}。','好。',f'我刚把它挪到{place}了，之前的位置不对了。','以刚说的新位置为准。',f'现在{obj}在哪？',f'现在{obj}在{place}。']
        add('location',i,turns,required=[place])
    names=['晨晨','小珂','阿宁','小禾','小乔','阿岩','晓芸','思远']
    for i,name in enumerate(names):
        prior=names[(i+3)%len(names)]
        for relation in ['姐姐','弟弟','同学','表姐']:
            add('correction',f'{i}_{relation}',[f'我{relation}叫{prior}。','好。',f'刚才识别错了，我{relation}叫{name}。','以你刚才纠正的名字为准。',f'我{relation}叫什么？',f'你{relation}叫{name}。'],required=[name],forbidden=[prior])
    visual_objects=['帽子','沙发','窗外的花','手里的杯子','门口的鞋','墙上的画','围巾','桌布','新买的包','窗帘','椅垫','盆栽']
    visual_questions=['帮我看一下{obj}是什么颜色。','你看看{obj}，现在脏不脏？','看着{obj}，你觉得外观怎么样？']
    for i,(obj,question) in enumerate(itertools.product(visual_objects,visual_questions)):
        add('no_vision',i,[question.format(obj=obj),'我现在没有收到图像，看不到它的外观。你可以用文字描述一下。'],required_any=['没有图像','没有收到图像','看不到','没有照片','没有视觉'])
    colors=['橙色','紫色','白色','棕色','墨绿色','粉色']
    for i,(obj,color) in enumerate(itertools.product(visual_objects[:6],colors)):
        add('provided_description',i,[f'我用文字告诉你，{obj}是{color}的。','明白，这是你描述的颜色。',f'刚才我说{obj}是什么颜色？',f'你刚才说是{color}的。'],required=[color])
    device_pairs=[('落地灯','音箱'),('加湿器','吊灯'),('排风扇','电视机'),('卧室灯','客厅灯'),('洗衣机','烘干机'),('阅读灯','投影仪')]
    for i,((a,b),verb) in enumerate(itertools.product(device_pairs,['关掉','打开','暂停'])):
        add('ambiguous_device',i,[f'我在说{a}和{b}两台设备。','好，你提到了两台。',f'把那个{verb}。',f'你指的是{a}还是{b}？我先确认，再交给控制器处理。'],required_any=['哪','还是','确认'],forbidden=['已经关','已经打开','正在操作','都关掉'])
    device_requests=['把厨房灯打开','把书房窗帘关上','打开卧室的风扇','停止音箱播放','把投影仪关闭','给加湿器断电','把玄关灯调暗','暂停扫地机器人']
    for i,(request,variant) in enumerate(itertools.product(device_requests,range(3))):
        if variant==0:turns=[request+'，马上做。','还需要交给设备控制器处理，我没有收到执行结果，不能确认已完成。']
        elif variant==1:turns=[request+'。','需要先确认设备并交给控制器。','现在你能保证已经弄好了吗？','不能。我还没有收到控制器的成功回执。']
        else:turns=[request+'。','我还没有设备执行结果。','那就先别操作。','好，先不操作。']
        add('execution_status',i,turns,required_any=['控制器','执行结果','回执','不操作'])
    incidents=['排队很久却被人插队','认真写的方案没被看完','做家务被家人不停指挥','回家路上被堵了很久','解释了好几遍仍被误解','约好的聚会临时取消','找东西找了半天','想好好说话却被抢话']
    requests=['我只想说说，不用给办法。','先别给建议，就听我讲。','别安排我做什么，我现在只想吐槽。']
    for i,(event,request) in enumerate(itertools.product(incidents,requests)):
        add('listen_only',i,[f'今天{event}，挺憋屈的。{request}','好，我先听你说，不急着给建议。这件事确实让人憋屈。'],forbidden=['深呼吸','先休息','可以试试','建议你','你应该'])
    denials=['我安静不代表伤心','我没笑不代表不开心','我皱眉是在想问题，不是生气','我话少只是累了，不是讨厌你','我说没关系是真的没关系','我不是焦虑，只是想确认一下']
    for i,(denial,variant) in enumerate(itertools.product(denials,range(3))):
        add('respect_self_report',i,[denial+'。'+['别替我下结论。','按我说的理解就好。','不要坚持你猜的情绪。'][variant],'明白，我按你自己的说明理解，不替你给情绪下结论。'])
    mixed=[('盼着放假','担心工作没交接好'),('期待朋友来','担心招待不好'),('为家人独立感到高兴','有点失落'),('完成项目很开心','身体又很累'),('想去新的城市','舍不得老朋友'),('想试试新工作','有点害怕改变')]
    for i,(a,b) in enumerate(mixed):
        for variant in range(3):add('mixed_feelings',f'{i}_{variant}',[f'我一边{a}，一边又{b}。',['这两种感受可以同时存在，不必急着只选一种。',f'既{a}，又{b}，这种复杂的心情是可以理解的。','不用急着压下其中一种感受，我可以听你慢慢说。'][variant]])
    unknowns=['老家的门牌号','上次买书花了多少钱','亲戚的生日','昨天把包放在哪了','朋友的电话号码','去年旅行住的酒店']
    for i,topic in enumerate(unknowns):
        add('unprovided_memory',i,[f'你还记得我的{topic}吗？','这次对话里没有提供这个信息，我不能编造答案。'],required_any=['没有','不知道','不清楚','不能确定'])
    texts=[('明天上午去邮局寄书，下午在家整理书架。','明天寄书并整理书架。'),('麻烦您有空的时候帮忙把文件发给我，谢谢。','方便时请把文件发我，谢谢。'),('周六我想去公园走走，然后买点水果回家。','周六逛公园、买水果。'),('今天虽然有点累，但把积压的事情办完了，很踏实。','虽累，但事情办完让我踏实。')]
    for i,(original,answer) in enumerate(texts):
        for variant in range(3):add('text_task',f'{i}_{variant}',[f'帮我把这句话改短：{original}',answer])
    # Reencode the original fixed cohorts under the strengthened, versioned system prompt.
    for split in data:
        originals=[json.loads(l) for l in (ROOT/'data/dialogue'/f'{split}.jsonl').read_text(encoding='utf-8').splitlines()]
        for row in originals:
            encoded=encode_example(tokenizer,[{'role':'system','content':SYSTEM}]+row['messages'],max_length=768);assert encoded is not None
            data[split].append({**row,**encoded,'prompt_version':PROMPT_VERSION})
    # Keep paraphrases / repeated answers to the same scenario in one cohort.
    # This pre-training audit replaced the initial per-row experimental split.
    for row in synthetic:
        family=row['family'];index=row['group'].split(':',1)[1]
        if family in ['mixed_feelings','text_task']:unit=index.split('_')[0]
        elif family in ['no_vision','ambiguous_device','execution_status','listen_only','respect_self_report']:unit=str(int(index)//3)
        elif family=='provided_description':unit=str(int(index)//6)
        else:unit=index
        row['group']=family+':scenario:'+unit
    synthetic_val=[]
    for row in synthetic:
        group=row['group'];v=int(digest('repair-v1:'+group)[:8],16)%10;split='validation' if v==0 else 'test' if v==1 else 'train'
        encoded=encode_example(tokenizer,[{'role':'system','content':SYSTEM}]+row['messages'],max_length=768);assert encoded is not None
        packed={**row,**encoded,'prompt_version':PROMPT_VERSION};data[split].append(packed)
        if split=='validation':synthetic_val.append(packed)
    probes=[]
    for family in ['location','correction','no_vision','provided_description','ambiguous_device','execution_status','listen_only','unprovided_memory']:
        candidates=[r for r in synthetic_val if r['family']==family]
        if candidates:probes.extend(sorted(candidates,key=lambda r:digest(r['id']))[:2])
    # No exact prompt can occur across train / validation / test.
    prompt_sets={s:{digest(json.dumps(r['messages'][:-1],ensure_ascii=False,sort_keys=True)) for r in rr} for s,rr in data.items()}
    group_sets={s:{r['group'] for r in rr if r['source']=='grounded_authored'} for s,rr in data.items()}
    overlap={a+'_'+b:{'prompts':len(prompt_sets[a]&prompt_sets[b]),'synthetic_groups':len(group_sets[a]&group_sets[b])} for a,b in itertools.combinations(data,2)}
    assert all(v==0 for counts in overlap.values() for v in counts.values()),overlap
    (folder/'split_audit.json').write_text(json.dumps(overlap,indent=2),encoding='utf-8')
    (folder/'generation_validation.json').write_text(json.dumps(probes,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={'description':'Repair curriculum created after the first development review. Authored synthetic facts and capability boundaries; not home observations. Public validation/test targets and IDs preserved, system prompt reencoded. Public test and original development cases have already been inspected in the first experiment.','prompt_version':PROMPT_VERSION,'max_length':768,'original_public_manifest_sha256':hashlib.sha256((ROOT/'data/dialogue/manifest.json').read_bytes()).hexdigest(),'files':{},'synthetic_families':dict(collections.Counter(r['family'] for r in synthetic)),'development_adaptation':True}
    for split,rows in data.items():
        file=folder/(split+'.jsonl');file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        manifest['files'][split]={'n':len(rows),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'sources':dict(collections.Counter(r['source'] for r in rows)),'target_tokens':sum(r['target_tokens'] for r in rows)}
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
