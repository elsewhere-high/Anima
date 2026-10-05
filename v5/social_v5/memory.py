"""Bounded, encrypted episodic and semantic memory with evidence and revisions.

Chinese character bigram relevance + recency + importance + diversity. No model
guess is promoted to a durable fact, and assistant replies are not fact sources.
"""
import hashlib, hmac, json, math, re, secrets, time
from datetime import datetime, timezone
from social_world_zh.memory import MemoryStore as BaseStore
from .storage import Cipher

SECRET=re.compile(r'密码|口令|验证码|私钥|助记词|银行卡号|身份证号|api[_ -]?key|password|token\s*[:=]',re.I)
def safe_text(text):return not bool(SECRET.search(text))
def grams(text):
    text=re.sub(r'[^\w\u4e00-\u9fff]','',text.casefold())
    return set(text[i:i+2] for i in range(len(text)-1)) | set(re.findall(r'[a-z0-9]{2,}',text))

class MemoryStore(BaseStore):
    def __init__(self,path,key_path,embedder=None):
        self.embedder=embedder
        self.cipher=Cipher(key_path)
        super().__init__(path)
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, uid TEXT NOT NULL,
          kind TEXT NOT NULL, slot TEXT NOT NULL, payload TEXT NOT NULL,
          created REAL NOT NULL, updated REAL NOT NULL, expires REAL,
          importance REAL NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE INDEX IF NOT EXISTS memory_owner ON records(uid,active,kind,updated);
        CREATE TABLE IF NOT EXISTS faces(uid TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS user_models(uid TEXT PRIMARY KEY, payload TEXT NOT NULL);
        ''');self.db.commit()
    def read(self,uid):
        with self.lock:
            row=self.db.execute('SELECT data FROM users WHERE id=?',(uid,)).fetchone()
            state=self.cipher.load(row[0]) if row else self.empty()
            state['_uid']=uid; state['memories']=[]
            return state
    def user_model(self,uid,value=None):
        """Encrypted statistics; never returned by public member listing."""
        with self.lock:
            profile=self.profile(uid)
            if not profile or not profile['memory_consent']:return {}
            if value is not None:
                previous=self.db.execute('SELECT payload FROM user_models WHERE uid=?',(uid,)).fetchone()
                value={**(self.cipher.load(previous[0]) if previous else {}),**value}
                self.db.execute('INSERT INTO user_models VALUES (?,?) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload',(uid,self.cipher.dump(value)));self.db.commit()
            row=self.db.execute('SELECT payload FROM user_models WHERE uid=?',(uid,)).fetchone()
            result=self.cipher.load(row[0]) if row else {}
            result['preferences']=profile.get('dialogue_preferences',{})
            return result
    def observe_communication_feedback(self,uid,text):
        """Only repeated explicit feedback updates a style profile; no inferred OCEAN."""
        if not text or not safe_text(text):return
        choices={'listen':r'只想.{0,6}听我说|先听我说|不要建议|别给建议',
                 'brief':r'简短一点|说短一点|别说那么多',
                 'analyze':r'帮我分析|给我建议|帮我想办法',
                 'quiet':r'安静陪着|先别说话|不要打扰'}
        selected=next((k for k,p in choices.items() if re.search(p,text)),None)
        if not selected:return
        with self.lock:
            model=self.user_model(uid)
            if not model:return
            now=time.time();preferences=model.get('communication_preferences',{})
            for item in preferences.values():
                item['weight']*=math.exp(-max(0,now-item['updated'])/(30*86400));item['updated']=now
            old=preferences.setdefault(selected,{'weight':0.,'observations':0,'updated':now,'last_observed':0})
            if now-old['last_observed']<30:return
            old.update(weight=min(20,old['weight']+1),observations=old['observations']+1,updated=now,last_observed=now)
            total=sum(x['weight'] for x in preferences.values())
            for item in preferences.values():item['confidence']=min(.85,item['weight']/max(1,total))*min(1,item['observations']/3)
            self.user_model(uid,{'communication_preferences':preferences,'preference_basis':'repeated_explicit_requests_with_decay_not_personality'})
    def update(self,uid,state):
        with self.lock:
            state={k:v for k,v in state.items() if k!='_uid'}; state['memories']=[]
            self.db.execute('INSERT INTO users VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(uid,self.cipher.dump(state)));self.db.commit()
    def register(self,uid,name,pin,consent=False):
        if uid=='anonymous':raise ValueError('anonymous is reserved')
        salt=secrets.token_hex(16)
        profile=dict(display_name=name,salt=salt,pin_hash=hashlib.scrypt(pin.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex(),memory_consent=consent,created=time.time())
        with self.lock:
            if self.db.execute('SELECT 1 FROM profiles WHERE id=?',(uid,)).fetchone():raise ValueError('成员 ID 已存在')
            if self.db.execute('SELECT COUNT(*) FROM profiles').fetchone()[0]>=32:raise ValueError('最多支持 32 位成员')
            self.db.execute('INSERT INTO profiles VALUES (?,?)',(uid,self.cipher.dump(profile)));self.db.commit()
    def profile(self,uid):
        with self.lock:
            r=self.db.execute('SELECT payload FROM profiles WHERE id=?',(uid,)).fetchone()
            return self.cipher.load(r[0]) if r else None
    def dialogue_preferences(self,uid,value=None):
        with self.lock:
            p=self.profile(uid)
            if not p:raise ValueError('Unknown member')
            if value is not None:
                if not p['memory_consent']:raise ValueError('请先允许长期记忆；也可仅在当前页面使用')
                p['dialogue_preferences']=value
                self.db.execute('UPDATE profiles SET payload=? WHERE id=?',(self.cipher.dump(p),uid));self.db.commit()
            return p.get('dialogue_preferences',{'mbti':None,'support':'auto'})
    def login(self,uid,pin):
        p=self.profile(uid)
        if not p:return False
        value=hashlib.scrypt(pin.encode(),salt=p['salt'].encode(),n=16384,r=8,p=1).hex()
        return hmac.compare_digest(value,p['pin_hash'])
    def profiles(self):
        with self.lock:
            return [{'user_id':uid,'display_name':self.cipher.load(p)['display_name'],'face_enrolled':self.db.execute('SELECT 1 FROM faces WHERE uid=?',(uid,)).fetchone() is not None} for uid,p in self.db.execute('SELECT id,payload FROM profiles').fetchall()]
    def consent(self,uid,value):
        with self.lock:
            p=self.profile(uid)
            if not p:raise ValueError('Unknown member')
            p['memory_consent']=value
            self.db.execute('UPDATE profiles SET payload=? WHERE id=?',(self.cipher.dump(p),uid));self.db.commit()
            if not value:self.forget(uid)
    def put(self,uid,kind,slot,text,source='user_explicit',session_id='',ttl_days=None,importance=.7,evidence=None,preserve_expiry=False):
        if not safe_text(text):raise ValueError('不保存密码、验证码等认证秘密')
        now=time.time(); record_id=secrets.token_hex(12);slot_index=self.cipher.index(slot)
        # Exact slot revisions keep history for audit, while retrieval uses only active facts.
        with self.lock:
            self.purge(uid)
            old=self.db.execute('SELECT id,payload,expires FROM records WHERE uid=? AND slot=? AND kind=? AND active=1',(uid,slot_index,kind)).fetchone() if kind!='event' else None
            expires=old[2] if preserve_expiry and old else now+ttl_days*86400 if ttl_days else None
            if old and self.cipher.load(old[1])['text']==text:
                self.db.execute('UPDATE records SET updated=?,expires=? WHERE id=?',(now,expires,old[0]));self.db.commit();return old[0]
            if old:self.db.execute('UPDATE records SET active=0 WHERE id=?',(old[0],))
            payload=dict(slot=slot,text=text,source=source,session_id=session_id,evidence=evidence or text,supersedes=old[0] if old else None)
            if self.embedder:payload['_embedding']=self.embedder.encode(text)
            self.db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,1)',(record_id,uid,kind,slot_index,self.cipher.dump(payload),now,now,expires,importance))
            self.db.commit(); self._bound(uid)
        return record_id
    def _bound(self,uid):
        for clause,cap in [("kind IN ('event','summary')",1000),("kind NOT IN ('event','summary') AND active=1",500),("active=0",500)]:
            self.db.execute(f'DELETE FROM records WHERE id IN (SELECT id FROM records WHERE uid=? AND {clause} ORDER BY updated DESC LIMIT -1 OFFSET ?)',(uid,cap))
        self.db.commit()
    def purge(self,uid=None):
        with self.lock:
            if uid:self.db.execute('DELETE FROM records WHERE uid=? AND expires IS NOT NULL AND expires<=?',(uid,time.time()))
            else:self.db.execute('DELETE FROM records WHERE expires IS NOT NULL AND expires<=?',(time.time(),))
            self.db.commit()
    def list(self,uid,include_history=False,limit=100,_vectors=False):
        with self.lock:
            self.purge(uid)
            rows=self.db.execute('SELECT id,kind,slot,payload,created,updated,expires,importance,active FROM records WHERE uid=?'+('' if include_history else ' AND active=1')+' ORDER BY updated DESC LIMIT ?',(uid,min(2000,max(1,limit)))).fetchall()
            result=[dict(id=r[0],kind=r[1],**self.cipher.load(r[3]),created=r[4],updated=r[5],expires=r[6],importance=r[7],active=bool(r[8])) for r in rows]
            if not _vectors:
                for r in result:r.pop('_embedding',None)
            return result
    def search(self,uid,query,limit=5):
        q=grams(query); all_rows=self.list(uid,True,limit=2000,_vectors=True); rows=[r for r in all_rows if r['active']]; now=time.time(); ranked=[]
        obsolete=[r for r in all_rows if not r['active'] and r['kind'] in {'fact','preference'}]
        vector=self.embedder.encode(query,query=True) if self.embedder and rows else None
        for r in rows:
            t=grams(r['text']+' '+r['slot']); overlap=len(q&t)
            profile=r['slot'] in {'姓名','称呼'}
            embedding=r.pop('_embedding',None)
            semantic=sum(a*b for a,b in zip(vector,embedding)) if vector is not None and embedding else 0.
            if not overlap and not profile and semantic<.6:continue
            if r['kind']=='event' and re.search(r'[?？]|在哪里|什么|记得吗',r['text']):continue
            if r['kind'] in {'event','summary'} and any(old['text'] in r['text'] or (isinstance(old['evidence'],str) and old['evidence'] in r['text']) for old in obsolete):continue
            relevance=overlap/math.sqrt(max(1,len(q))*max(1,len(t)))
            score=2*relevance+1.5*semantic+.12*math.exp(-(now-r['updated'])/(30*86400))+.12*r['importance']+(.15 if r['kind'] in {'fact','preference'} else 0)
            ranked.append((score,r,t))
        chosen=[];seen=set()
        for _,r,t in sorted(ranked,key=lambda x:x[0],reverse=True):
            # Once a semantic slot is current, don't inject obsolete episodic copies.
            if r['kind'] in {'event','summary'} and any(s['slot'].replace('位置','') in r['text'] and s['text'] not in r['text'] for s in rows if s['kind'] in {'fact','preference'}):continue
            if any(len(t&old)/max(1,len(t|old))>.8 for old in seen):continue
            chosen.append(r);seen.add(frozenset(t))
            if len(chosen)>=limit:break
        return chosen
    def retrieve(self,state,query,limit=5):
        uid=state.get('_uid')
        if not uid:return []
        return [f"[{datetime.fromtimestamp(r['updated'],timezone.utc).isoformat()}；{r['source']}；{r['kind']}] {r['text']}" for r in self.search(uid,query,limit)]
    def capture(self,uid,session_id,speech,note=None):
        text=speech.strip(); writes=[]
        if not text or not safe_text(text):return {'writes':[],'reason':'empty_or_sensitive'}
        # Questions, hypothetical/quoted stories and third-person statements aren't self facts.
        eligible=not re.search(r'[?？]|如果|假如|假设|故事|扮演|他说|她说|有人说|朋友说|是不是|叫什么|在哪里|哪儿|哪里',text)
        patterns=[('姓名',r'(?:^|[，。；])(?:请记住[，：]?)?我(?:叫|的名字是)([\u4e00-\u9fffA-Za-z·]{1,20})(?=$|[，。；！])','fact',None),
                  ('称呼',r'(?:以后)?(?:请)?叫我([^，。；！？]{1,20})','fact',None),
                  ('偏好',r'(?:^|[，。；])我(?:现在|最近|已经|改成)?(?:不再)?(?:喜欢|不喜欢|爱吃|不吃|爱喝|不喝)([^，。；！？]{1,40})','preference',None),
                  ('居住地',r'(?:^|[，。；])我(?:现在)?(?:住在|搬到了)([^，。；！？]{1,40})','fact',None)]
        if eligible:
            for slot,pattern,kind,ttl in patterns:
                m=re.search(pattern,text)
                if m:
                    if slot=='偏好':
                        topic=m[1]
                        slot=('饮品偏好' if re.search(r'茶|咖啡|果汁|牛奶|豆浆|饮料',topic) else '口味偏好' if re.search(r'辣|甜|咸|酸|清淡',topic) else '偏好:'+topic[:30])
                    value=m.group(0).lstrip('，。；');writes.append(self.put(uid,kind,slot,value,'user_statement_rule_v1',session_id,ttl,evidence=text))
            m=re.search(r'(?:^|[，。；])(?:请记住[，：]?)?(?:我的|我把)?(钥匙|眼镜|手机|遥控器|药盒)(?:现在|已经|刚才|改)?(?:放在了|放在|放到了|在|移到了)([^，。；！？]{1,50})',text)
            if m:writes.append(self.put(uid,'fact',m[1]+'位置',m[1]+'在'+m[2],'user_statement_rule_v1',session_id,7,evidence=text))
        if note and safe_text(note):writes.append(self.put(uid,'fact','手动:'+hashlib.sha256(note.encode()).hexdigest()[:12],note,'user_explicit',session_id))
        elif text.startswith(('请记住','记住：','记住:')) and eligible and not writes:
            note=re.sub(r'^(请记住|记住)[：:，,]?','',text).strip()
            if note:writes.append(self.put(uid,'fact','明确记忆:'+hashlib.sha256(note.encode()).hexdigest()[:12],note,'user_explicit',session_id))
        self.put(uid,'event','对话事件',text,'user_utterance',session_id,30,.35)
        self.consolidate(uid,session_id)
        return {'writes':writes,'reason':'explicit_facts_and_user_episode'}
    def consolidate(self,uid,session_id):
        rows=[r for r in self.list(uid,limit=100) if r['kind']=='event' and r['session_id']==session_id][:6]
        if len(rows)<4:return
        # Extractive, never an invented model summary; at most six source utterances.
        text='；'.join(r['text'][:40] for r in reversed(rows))[:300]
        self.put(uid,'summary','会话摘要:'+session_id,text,'extractive_user_utterances',session_id,30,.45,evidence=[r['id'] for r in rows])
    def delete_record(self,uid,rid):
        with self.lock:
            target=next((r for r in self.list(uid,True,2000) if r['id']==rid),None)
            if not target:return False
            # Remove all revisions and source-containing summaries/episodes too.
            rows=self.list(uid,True,2000)
            if target['kind'] in {'fact','preference'}:
                doomed={r['id'] for r in rows if r['slot']==target['slot'] or target['text'] in r['text'] or target['evidence']==r.get('evidence')}
            else:
                doomed={r['id'] for r in rows if r['id']==rid or (r['kind']=='summary' and (rid in r.get('evidence',[]) or target['text'] in r['text']))}
            if target['kind'] in {'fact','preference'}:
                doomed.update(r['id'] for r in rows if r['kind'] in {'event','summary'} and (target['slot'].replace('位置','') in r['text'] or any(x['text'] in r['text'] for x in rows if x['slot']==target['slot'])))
            self.db.executemany('DELETE FROM records WHERE uid=? AND id=?',[(uid,i) for i in doomed]);self.db.commit();return True
    def forget(self,uid):
        with self.lock:
            self.db.execute('DELETE FROM user_models WHERE uid=?',(uid,))
            super().forget(uid);self.db.execute('DELETE FROM records WHERE uid=?',(uid,));self.db.commit()
            p=self.profile(uid)
            if p and 'dialogue_preferences' in p:
                p.pop('dialogue_preferences')
                self.db.execute('UPDATE profiles SET payload=? WHERE id=?',(self.cipher.dump(p),uid));self.db.commit()
            if p and ('care_preferences' in p or 'care_runtime' in p):
                p.pop('care_preferences',None);p.pop('care_runtime',None)
                self.db.execute('UPDATE profiles SET payload=? WHERE id=?',(self.cipher.dump(p),uid));self.db.commit()
    def delete_profile(self,uid):
        with self.lock:
            self.forget(uid);self.db.execute('DELETE FROM profiles WHERE id=?',(uid,));self.db.execute('DELETE FROM faces WHERE uid=?',(uid,));self.db.commit()
    def save_face(self,uid,embeddings):
        with self.lock:
            self.db.execute('INSERT INTO faces VALUES (?,?) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload',(uid,self.cipher.dump(dict(embeddings=embeddings,consent_at=time.time()))));self.db.commit()
    def faces(self):
        with self.lock:return [(uid,self.cipher.load(p)) for uid,p in self.db.execute('SELECT uid,payload FROM faces').fetchall()]
    def delete_face(self,uid):
        with self.lock:self.db.execute('DELETE FROM faces WHERE uid=?',(uid,));self.db.commit()
    def remind(self,uid,seconds,text):
        if not safe_text(text):raise ValueError('Sensitive reminder')
        with self.lock:
            due=time.time()+seconds;c=self.db.execute('INSERT INTO reminders(user_id,due,text) VALUES (?,?,?)',(uid,due,self.cipher.dump(text)));self.db.commit()
            return dict(id=c.lastrowid,due_unix=due,text=text)
    def due(self,uid):
        result=super().due(uid)
        for r in result:r['text']=self.cipher.load(r['text'])
        return result
