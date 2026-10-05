"""Pre-training quality review. Original held-out bytes are immutable."""
import json,re,hashlib,collections,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HUMAN_APPROVED={
 'oasst:46e33778-523b-4b3a-b9dd-77b72cef2688':'原创七言短诗，格式符合请求；不冒充历史原作',
 'oasst:0bfbc473-b10a-49b6-885e-fe5367e8b851':'用户指定水主题的创作，不作事实教学',
 'oasst:d4216d2b-8699-4db6-aad8-a09e262fd488':'常见灯谜与简短解释',
 'oasst:6fcba9cd-c442-4c5c-b32b-7d032a39047d':'接续上一轮地名并给出正确省份',
 'oasst:e788dfc4-e154-438e-93b9-bc1488aabe03':'回应物质与主观幸福的区分，包含不同可能性',
 'oasst:92b4c424-ee55-4609-8754-ce39a29bfe8c':'鸡兔方程及23只鸡12只兔与给定35头94脚一致',
 'oasst:c8a93af2-d3ca-4b25-b206-2d614ad927ba':'依据用户提供会议内容总结，不编造会议信息',
 'oasst:7760db4b-eddb-48db-91d6-53bbe1611e30':'成语接龙保持前后衔接',
 'oasst:f643f559-cbae-4c64-8e7d-78cde6d36f35':'简繁体对应例句',
 'oasst:2ff9293c-fec0-4ca7-b5d5-e237fdfee717':'对晚宴建议后的感谢做简短承接',
 'oasst:1a9523a5-a5c9-445c-9e90-acaf24e4aba5':'缺少文章内容时请求提供，不编造摘要',
 'oasst:24a6d612-e566-41df-bf6a-746522f8f118':'简单算术后回应感谢',
 'oasst:503ca537-c3f2-4cbe-9440-f8328a4ff321':'正确回答接续算术问题',
 'oasst:3c6fc457-5192-407b-af16-31d6158dab01':'面对单个问号进行澄清',
 'oasst:7fa70e86-a45d-4e9a-92fa-1a37fabf1ee8':'一般助手能力介绍，不冒充其他产品',
 'oasst:b37df38c-7605-4b4a-b6fd-ef1c9aade52e':'接续上下文确认ten的三个字母'
}

def main():
    folder=ROOT/'data/dialogue';backup=ROOT/'data/dialogue_pre_quality_review'
    refining='--refine' in sys.argv
    if backup.exists() and not refining:raise RuntimeError('Quality review was already applied')
    if (ROOT/'runs/dialogue_sft/protocol.json').exists():raise RuntimeError('Cannot mutate a started training corpus')
    input_folder=backup if refining else folder
    manifest=json.loads((input_folder/'manifest.json').read_text(encoding='utf-8'))
    rows=[json.loads(line) for line in (input_folder/'train.jsonl').read_text(encoding='utf-8').splitlines()]
    assert set(HUMAN_APPROVED).issubset({r['id'] for r in rows})
    # Keep the full pre-review snapshot, including previous hashes and source attribution.
    shutil.copytree(folder,ROOT/'data/dialogue_quality_review_v1' if refining else backup)
    emotion=re.compile(r'开心|開心|高兴|高興|难过|難過|难受|難受|伤心|傷心|压力|壓力|紧张|緊張|担心|擔心|焦虑|焦慮|烦|煩|生气|生氣|委屈|难受|孤单|孤單|孤独|孤獨|害怕|恐惧|恐懼|沮丧|沮喪|失落|失望|糟糕|累|疲惫|疲憊|无聊|無聊|开心|快樂|快乐|幸福|放松|放鬆|兴奋|興奮|激动|激動|想哭|不安|倾诉|傾訴|安慰|陪我|聊聊|说说话|說說話|鼓励|鼓勵|自信|信心|感谢|感謝|谢谢|謝謝|感动|感動|不理解我|跟不上|后悔|後悔|遗憾|遺憾|孤立|尴尬|尷尬|努力.*认可|努力.*認可')
    unsupported=re.compile(r'一定会|一定會|肯定|你一定|一定能|总能|總能|总会|總會|就会|就會|一切都|都会|都會|很快|保证|保證|别难过|別難過|别紧张|別緊張|别想太多|別想太多|没什么大不了|沒什麼大不了|我也.{0,5}(?:经历过|經歷過|吃过|吃過|去过|去過)|我.{0,4}(?:看过这|看過這|听过这|聽過這)|这个电影确实|這個電影確實|我今天也|大哥|大姐|小伙子|姑娘|成年人嘛|无心之言|無心之言|最近天气|最近天氣|新开的|新開的|你一直都|你已经很|你已經很|(?:他|她|他们|他們)只是|[0-9一二三四五六七八九十百千万两]+(?:秒|分钟|分鐘|小时|小時|个月|個月|万|萬|公里|岁|歲|年|次)')
    excluded=[];kept=[]
    for r in rows:
        reason=None
        if r['source']=='oasst2_zh' and r['id'] not in HUMAN_APPROVED:reason='not_in_manually_reviewed_human_allowlist'
        if r['source']=='opens2s_zh':
            query=r['messages'][-2]['content'];answer=r['messages'][-1]['content']
            if not emotion.search(query):reason='outside_current_empathy_dialogue_curriculum'
            elif unsupported.search(answer):reason='unsupported_guarantee_minimization_or_experience'
            elif re.search(r'安慰|陪我|(?:只想|只是).{0,6}(?:说说|聊聊)',query) and re.search(r'首先|建议|建議|你应该|你應該|科学.{0,4}(?:饮食|飲食)|一起制定',answer):reason='unsolicited_directive_advice_in_support_request'
        if reason:excluded.append({'id':r['id'],'reason':reason})
        else:kept.append(r)
    file=folder/'train.jsonl';file.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in kept),encoding='utf-8')
    manifest['files']['train']={'n':len(kept),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'sources':dict(collections.Counter(r['source'] for r in kept)),'multiturn_n':sum(len(r['messages'])>2 for r in kept),'target_tokens':sum(r['target_tokens'] for r in kept)}
    manifest['pre_training_quality_review']={'human_allowlist':HUMAN_APPROVED,'synthetic_filter':'Emotion/support-oriented queries; remove unsupported certainty, emotional minimization and invented assistant experience. Deterministic filter plus documented sample inspection, not a claim of exhaustive human annotation.','excluded_count':len(excluded),'original_snapshot':'data/dialogue_pre_quality_review','heldout_unchanged':True}
    for split in ['validation','test']:
        assert (folder/(split+'.jsonl')).read_bytes()==(backup/(split+'.jsonl')).read_bytes()
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'reports/dialogue_training_curation.json').write_text(json.dumps({'input_n':len(rows),'output':manifest['files']['train'],'approved_human':HUMAN_APPROVED,'excluded':excluded,'heldout_changed':False,'before_first_optimizer_step':True},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest['files']['train'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
