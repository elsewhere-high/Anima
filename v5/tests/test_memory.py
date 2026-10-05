import time
import pytest
from social_v5.memory import MemoryStore

@pytest.fixture
def store(tmp_path):
    m=MemoryStore(tmp_path/'memory.db',tmp_path/'key');yield m;m.db.close()

def test_restart_encryption_and_wrong_key(tmp_path):
    m=MemoryStore(tmp_path/'memory.db',tmp_path/'key')
    m.register('a','小林','securepin',True)
    rid=m.put('a','fact','物品','眼镜在卧室抽屉');m.update('a',m.empty());m.remind('a',1,'给花浇水');m.db.close()
    assert '眼镜'.encode() not in (tmp_path/'memory.db').read_bytes()
    assert '小林'.encode() not in (tmp_path/'memory.db').read_bytes()
    m=MemoryStore(tmp_path/'memory.db',tmp_path/'key')
    assert m.login('a','securepin') and not m.login('a','wrongpin')
    assert m.search('a','眼镜')[0]['id']==rid
    m.db.close()
    bad=MemoryStore(tmp_path/'memory.db',tmp_path/'another_key')
    with pytest.raises(Exception):bad.profile('a')
    bad.db.close()

def test_correction_retrieves_only_current_fact(store):
    store.capture('a','day1','我的眼镜放在书桌')
    store.capture('a','day2','我把眼镜移到了抽屉')
    rows=store.search('a','眼镜在哪里')
    assert rows and rows[0]['text']=='眼镜在抽屉'
    assert all('书桌' not in r['text'] for r in rows)
    assert any(not r['active'] for r in store.list('a',True))

def test_isolation_no_match_and_expiry(store):
    store.put('alice','fact','物品','钥匙在玄关',ttl_days=1)
    assert store.search('bob','钥匙')==[]
    assert store.search('alice','火星人口')==[]
    store.db.execute('UPDATE records SET expires=?',(time.time()-1,));store.db.commit()
    assert store.search('alice','钥匙')==[] and store.list('alice',True)==[]

@pytest.mark.parametrize('speech',['我叫谁？','如果我叫王明','故事里的我叫王明','他说我叫王明','我的密码是123456'])
def test_does_not_turn_questions_fiction_or_secrets_into_facts(store,speech):
    store.capture('a','s',speech)
    assert not [r for r in store.list('a') if r['kind']=='fact']
    if '密码' in speech:assert store.list('a')==[]

def test_user_facts_not_assistant_guesses_and_summary_source(store):
    for text in ['我叫小林','今天陪奶奶散步','准备给阳台浇水','晚上看了一本书']:store.capture('a','s',text)
    facts=[r for r in store.list('a') if r['kind']=='fact']
    assert len(facts)==1 and facts[0]['slot']=='姓名'
    summary=next(r for r in store.list('a') if r['kind']=='summary')
    assert summary['source']=='extractive_user_utterances' and len(summary['evidence'])==4

def test_deletion_cascades_to_old_revisions_and_episodes(store):
    store.capture('a','s','我的眼镜放在书桌')
    store.capture('a','s','我把眼镜移到了抽屉')
    rid=next(r['id'] for r in store.list('a') if r['kind']=='fact')
    assert store.delete_record('b',rid) is False
    assert store.delete_record('a',rid)
    assert not any('眼镜' in r['text'] for r in store.list('a',True))

def test_consent_revocation_erases_memory_but_face_requires_own_deletion(store):
    store.register('a','甲','securepin',True);store.put('a','fact','称呼','小甲');store.save_face('a',[[1,0]])
    store.consent('a',False)
    assert not store.profile('a')['memory_consent'] and store.list('a')==[]
    assert store.faces()
    store.delete_profile('a')
    assert store.profile('a') is None and store.faces()==[]

def test_records_bounded_without_other_user_loss(store):
    store.put('b','fact','称呼','乙')
    for i in range(510):store.put('a','fact',str(i),'这是物品'+str(i))
    assert len(store.list('a',limit=2000))==500
    assert len(store.list('b'))==1

def test_reminder_payload_encrypted_and_acknowledged(store):
    r=store.remind('a',-1,'给花浇水')
    assert store.due('a')[0]['text']=='给花浇水'
    assert not store.acknowledge('b',r['id'])
    assert store.acknowledge('a',r['id']) and store.due('a')==[]

def test_reconfirm_refreshes_expiry_and_slot_is_not_plaintext(store):
    rid=store.put('a','fact','私人的主题','眼镜在书桌',ttl_days=1)
    old=store.list('a')[0]['expires']
    store.put('a','fact','私人的主题','眼镜在书桌',ttl_days=7)
    assert store.list('a')[0]['expires']>old+5*86400
    raw=store.db.execute('SELECT slot FROM records WHERE id=?',(rid,)).fetchone()[0]
    assert raw!='私人的主题'

def test_event_delete_does_not_erase_all_other_events(store):
    a=store.put('a','event','对话事件','今天去了公园')
    b=store.put('a','event','对话事件','昨天看了电影')
    store.delete_record('a',a)
    assert [r['id'] for r in store.list('a')]==[b]

def test_drink_correction_preserves_unrelated_preference(store):
    store.capture('a','one','我喜欢游泳')
    store.capture('a','one','我喜欢喝咖啡')
    store.capture('a','two','我现在不喝咖啡')
    facts=[r for r in store.list('a') if r['kind']=='preference']
    assert any('游泳' in r['text'] for r in facts)
    assert any('不喝咖啡' in r['text'] for r in facts)
    assert not any('喜欢喝咖啡' in r['text'] for r in store.search('a','咖啡'))

def test_edit_preserves_exact_expiry(store):
    store.put('a','fact','眼镜位置','眼镜在书桌',ttl_days=3)
    expiry=store.list('a')[0]['expires']
    store.put('a','fact','眼镜位置','眼镜在抽屉',ttl_days=3,preserve_expiry=True)
    assert store.list('a')[0]['expires']==expiry
