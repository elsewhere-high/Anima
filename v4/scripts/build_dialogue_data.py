"""Quality-filtered Chinese response supervision, with source/group isolation."""
import sys,json,re,hashlib,collections,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import pandas as pd
from transformers import AutoTokenizer
from social_v4.dialogue import SYSTEM,encode_example

def normalized(s):return re.sub(r'\W+','',unicodedata.normalize('NFKC',s)).lower()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def partition(group):
    v=int(digest('v4-dialogue-20260926:'+group)[:8],16)%100
    return 'train' if v<90 else 'validation' if v<95 else 'test'

def main():
    out=ROOT/'data/dialogue';out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise RuntimeError('Dataset already exists')
    tokenizer=AutoTokenizer.from_pretrained(ROOT.parent/'v2/models/qwen35_2B',local_files_only=True);data={s:[] for s in ['train','validation','test']};rejected=collections.Counter();raw=ROOT/'data/raw'
    report={'description':'Text-only response SFT. OpenS2S synthetic single-turn empathy, quality-rated OASST2 Chinese conversation, and explicitly project-authored home multi-turn examples. No synthetic data is called real home evidence.','sources':json.loads((ROOT/'data/source_manifest.json').read_text(encoding='utf-8')),'not_used':['sharegpt_gpt4: quality inspection found confidently incorrect answer; downloaded for inspection only','OpenS2S reasoning_content/audio/emotion/age/gender are not model inputs or targets','OpenS2S non-adult or non-Neutral voice conditions excluded to avoid training unknown demographic/paralinguistic assumptions'],'max_length':512,'loss':'Final assistant content and end token only; all prompt/history/padding masked','test_used_for_selection':False}
    banned=re.compile(r'<\|im_|<think>|```|https?://|服药|服藥|用药|用藥|处方|診斷|诊断|剂量|劑量|自杀|自殺|自残|自殘|心理咨询师|心理諮詢師|作为.*语言模型|作為.*語言模型|我是.*OpenAI|我已经帮你|我已經幫你|我给你.*(?:倒|拿|打开|打開)|小朋友|宝贝|寶貝|亲爱的|親愛的')
    def add(split,source,group,messages,id):
        if not messages or len(messages)%2 or any(m['role']!=('user' if i%2==0 else 'assistant') for i,m in enumerate(messages)):rejected[source+'_roles']+=1;return
        if any(banned.search(m['content']) for m in messages):rejected[source+'_content_filter']+=1;return
        if not 8<=len(messages[-1]['content'])<=240:rejected[source+'_target_length']+=1;return
        encoded=encode_example(tokenizer,[{'role':'system','content':SYSTEM}]+messages)
        if encoded is None:rejected[source+'_token_length']+=1;return
        data[split].append({'id':id,'source':source,'group':group,'messages':messages,**encoded})
    # Same normalized query across synthesized voice variants remains one group.
    groups={}
    for line in (raw/'OpenS2S_Datasets/manifest_zh.jsonl').open(encoding='utf-8'):
        r=json.loads(line);q=r['query'];answer=r['response']['text'].strip();question=q['text'].strip()
        if q['age']!='adult' or q['emotion']!='Neutral':rejected['opens2s_unobserved_condition']+=1;continue
        if not 8<=len(question)<=220 or not 16<=len(answer)<=180 or banned.search(question+answer):rejected['opens2s_filter']+=1;continue
        key=normalized(question)
        if not key:continue
        if key not in groups or len(answer)<len(groups[key]['response']['text']):groups[key]=r
    for key in sorted(groups,key=lambda k:digest('order:'+k)):
        r=groups[key];split=partition(key)
        if sum(x['source']=='opens2s_zh' for x in data[split])>={'train':3500,'validation':240,'test':240}[split]:continue
        add(split,'opens2s_zh',digest(key),[{'role':'user','content':r['query']['text'].strip()},{'role':'assistant','content':r['response']['text'].strip()}],'opens2s:'+str(r['index']))
    # Reconstruct parent chains; keep original official validation entirely as TEST.
    for file in sorted((raw/'oasst2').glob('*.parquet')):
        rows=pd.read_parquet(file).to_dict('records');lookup={r['message_id']:r for r in rows};official_test=file.name.startswith('validation')
        for r in rows:
            if r['lang']!='zh' or r['role']!='assistant' or r['deleted'] or r['review_result'] is not True:continue
            labels=dict(zip(r['labels']['name'],r['labels']['value']));rank=r['rank']
            if labels.get('quality',0)<.65 or any(labels.get(k,0)>.1 for k in ['spam','fails_task','pii','not_appropriate','hate_speech','sexual_content']):rejected['oasst_quality']+=1;continue
            if rank is not None and not pd.isna(rank) and rank!=0:continue
            chain=[];current=r;seen=set()
            while current is not None:
                if current['message_id'] in seen:raise ValueError('Parent cycle')
                seen.add(current['message_id']);chain.append(current);parent=current['parent_id']
                if parent is None or pd.isna(parent):break
                current=lookup.get(parent)
                if current is None:chain=[];break
            chain.reverse()
            if not chain or any(x['lang']!='zh' or x['deleted'] for x in chain):continue
            chain=chain[-6:];group=r['message_tree_id'];split='test' if official_test else ('validation' if int(digest('oasst:'+group)[:8],16)%10==0 else 'train')
            messages=[{'role':'user' if x['role']=='prompter' else 'assistant','content':x['text'].strip()} for x in chain]
            add(split,'oasst2_zh',group,messages,'oasst:'+r['message_id'])
    # Original authored examples are TRAIN only, never the held-out corpus.
    seeds=json.loads((ROOT/'data/home_dialogue_seeds.json').read_text(encoding='utf-8'))
    for seed in seeds:
        for end in range(2,len(seed['turns'])+1,2):
            messages=[{'role':'user' if i%2==0 else 'assistant','content':text} for i,text in enumerate(seed['turns'][:end])]
            encoded=encode_example(tokenizer,[{'role':'system','content':SYSTEM}]+messages)
            assert encoded is not None
            data['train'].append({'id':f'home_authored:{seed["id"]}:{end}','source':'home_authored','group':seed['id'],'messages':messages,**encoded,'synthetic':True})
    # Cross-source exact prompt leakage audit: retain held-out rows, exclude overlapping TRAIN.
    def signature(r):return digest(json.dumps(r['messages'][:-1],ensure_ascii=False,sort_keys=True))
    held={signature(r) for split in ['validation','test'] for r in data[split]};before=len(data['train']);data['train']=[r for r in data['train'] if signature(r) not in held];rejected['train_heldout_exact_prompt_overlap']=before-len(data['train'])
    for a,b in [('train','validation'),('train','test'),('validation','test')]:assert not {(r['source'],r['group']) for r in data[a]}&{(r['source'],r['group']) for r in data[b]}
    report['files']={};report['rejected']=dict(rejected)
    for split,rows in data.items():
        file=out/(split+'.jsonl');file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8');report['files'][split]={'n':len(rows),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'sources':dict(collections.Counter(r['source'] for r in rows)),'multiturn_n':sum(len(r['messages'])>2 for r in rows),'target_tokens':sum(r['target_tokens'] for r in rows)}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:report[k] for k in ['files','rejected']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
