"""Deterministic home-care services. No diagnosis, calls, or physical actuation.

The safety matcher is a conservative routing aid, NOT a validated detector.
Durable care settings and reminder text use the existing encrypted store.
"""
import re
import json
import time
import threading
from datetime import datetime, timezone, timedelta
from .memory import safe_text

NUMBERS={'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'半':.5}

def number(value):
    if value.isdigit():return int(value)
    if value in NUMBERS:return NUMBERS[value]
    if '十' in value:
        a,b=value.split('十');return NUMBERS.get(a,1)*10+NUMBERS.get(b,0)
    return None

def triage(text,confidence=1):
    """Only current explicit reports; do not treat quotations as verified emergencies."""
    s=re.sub(r'\s+','',text)
    # A present-time clause overrides earlier background context.
    current=re.split(r'但是现在|但现在|可是现在|不过现在',s)[-1]
    present=re.search(r'(?:我现在|现在我|现在妈妈|现在爸爸|现在爷爷|现在奶奶)[^，。；!?！？]*',current)
    if present and not re.search(r'如果|假如|翻译|电影|小说|[“”「」]',current[:present.start()]):current=present.group()
    if re.search(r'电影|电视剧|小说|这句话|翻译|假如|如果|演练|开玩笑|昨天|去年|以前',current):return None
    patterns=[
        ('breathing',r'喘不过气|呼吸困难|无法呼吸|不能呼吸|呼吸不了|窒息'),
        ('chest',r'胸(?:口)?(?:疼|痛)|胸闷.{0,8}(?:冒汗|出汗|喘)'),
        ('fall',r'(?:摔倒|跌倒|摔了).{0,15}(?:起不来|不能动|动不了|很痛|出血)|(?:老人|爸爸|妈妈|爷爷|奶奶|他|她).{0,6}(?:昏倒|叫不醒)|我.{0,5}(?:倒在地上|摔倒了|跌倒了)'),
        ('self_harm',r'不想活了|想自杀|要自杀|想结束生命|想伤害自己|准备跳楼'),
        ('environment',r'着火了|闻到.{0,6}(?:煤气|燃气)味|燃气泄漏|煤气泄漏'),
        ('help',r'救命|快救我|帮我叫救护车|快叫120'),
    ]
    for kind,pattern in patterns:
        for match in re.finditer(pattern,current):
            prefix=current[max(0,match.start()-7):match.start()]
            if re.search(r'(?:没有|并没有|不再|不是|并非|没|否认)(?:感觉|出现|觉得)?$',prefix):continue
            if confidence<.65:
                return dict(kind='clarify_safety',priority='attention',response='我没有听清，你现在是否需要紧急帮助？如果正处于危险中，请立即呼叫身边的人或当地急救服务。')
            if kind=='environment':
                reply='这可能有危险。请先远离危险区域，到安全处呼叫身边的人和当地应急服务。不要等待我的回复；我还没有替你报警。'
            elif kind=='self_harm':
                reply='我很在意你现在的安全。请马上联系一位能到你身边的人，不要独自承受；如果可能马上伤害自己，请立即联系当地急救服务。你现在身边有人吗？我还没有替你联系任何人。'
            elif kind=='fall':
                reply='先不要勉强起身。请呼叫身边的人；如果受伤、无法起身或意识不清，请立即联系当地急救服务。在中国大陆可拨打 120。我还没有替你拨号。'
            else:
                reply='这可能需要立即得到帮助。请现在呼叫身边的人并联系当地急救服务；在中国大陆可拨打 120，说明所在位置和当前情况。不要等我继续聊天，我还没有替你拨号。'
            return dict(kind=kind,priority='urgent',response=reply)
    return None

def reminder_request(text):
    s=text.strip().rstrip('。！!')
    if not re.search(r'提醒我|提醒一下我',s):return None
    if re.search(r'不用|不要|别再|取消|昨天|之前|记得|你说|他说|她说|[“”「」]',s):return None
    patterns=[r'^(?:请|帮我)?([\d一二两三四五六七八九十半]+)(秒钟?|分钟|小时|天)后(?:再)?提醒(?:一下)?我[，,\s]*(.+)$',
              r'^(?:请|帮我)?提醒(?:一下)?我[，,\s]*([\d一二两三四五六七八九十半]+)(秒钟?|分钟|小时|天)后[，,\s]*(.+)$']
    for pattern in patterns:
        m=re.match(pattern,s)
        if m:
            n=number(m[1]);scale={'秒':1,'秒钟':1,'分钟':60,'小时':3600,'天':86400}[m[2]]
            if n is not None and 1<=n*scale<=31536000 and len(m[3])<=200:return {'delay_seconds':int(n*scale),'text':m[3]}
    return {'clarify':True}

DEFAULTS=dict(proactive_enabled=False,interval_minutes=60,quiet_start=22,quiet_end=8,utc_offset_minutes=480)

class ReminderConflict(ValueError):
    """A request identifier was reused for a different operation."""

class CareService:
    def __init__(self,memory,clock=time.time):
        self.memory=memory;self.clock=clock;self.lock=threading.RLock();self.activity={};self.paused=set()
        with memory.lock:
            columns={r[1] for r in memory.db.execute('PRAGMA table_info(reminders)')}
            for name,definition in [('request_key','TEXT'),('request_fingerprint','TEXT'),('repeat_seconds','INTEGER NOT NULL DEFAULT 0'),('kind',"TEXT NOT NULL DEFAULT 'general'")]:
                if name not in columns:memory.db.execute(f'ALTER TABLE reminders ADD COLUMN {name} {definition}')
            memory.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS reminder_request_key ON reminders(user_id,request_key) WHERE request_key IS NOT NULL')
            memory.db.commit()

    def settings(self,uid,value=None):
        with self.memory.lock,self.lock:
            p=self.memory.profile(uid)
            if not p:raise ValueError('请先登录成员')
            if value is not None:
                if not p['memory_consent']:raise ValueError('保存陪护设置需要长期记忆许可')
                p['care_preferences']={**DEFAULTS,**value}
                p['care_runtime']={'last_offer':self.clock(),'paused':False}
                self.memory.db.execute('UPDATE profiles SET payload=? WHERE id=?',(self.memory.cipher.dump(p),uid));self.memory.db.commit()
                self.activity[uid]=self.clock();self.paused.discard(uid)
            return {**DEFAULTS,**p.get('care_preferences',{})}

    def note_speech(self,uid,text):
        if not text.strip():return
        from social_world_zh.policy import explicit_boundary
        boundary=explicit_boundary(text)
        with self.lock:
            if len(self.activity)>=1024:self.activity.pop(next(iter(self.activity)),None)
            self.activity[uid]=self.clock()
            if boundary=='do_not_disturb':self.paused.add(uid)
            elif boundary=='open':self.paused.discard(uid)
        if uid!='anonymous' and boundary in {'do_not_disturb','open'}:
            with self.memory.lock:
                p=self.memory.profile(uid)
                if p and p['memory_consent']:
                    p.setdefault('care_runtime',{})['paused']=boundary=='do_not_disturb'
                    self.memory.db.execute('UPDATE profiles SET payload=? WHERE id=?',(self.memory.cipher.dump(p),uid));self.memory.db.commit()

    def add(self,uid,text,due,request_key=None,repeat_seconds=0,kind='general',delay_seconds=None):
        if not text.strip() or len(text)>200 or not safe_text(text):raise ValueError('请填写不含认证秘密的提醒内容，最多 200 字')
        now=self.clock()
        # Hash the original request, not a moving deadline or snoozed occurrence.
        timing={'delay_seconds':delay_seconds} if delay_seconds is not None else {'due_at':float(due)}
        fingerprint=self.memory.cipher.index(json.dumps([text,timing,repeat_seconds,kind],ensure_ascii=False,sort_keys=True))
        with self.memory.lock:
            p=self.memory.profile(uid)
            if not p or not p['memory_consent']:raise ValueError('保存提醒需要先登录并允许长期记忆')
            if request_key:
                old=self.memory.db.execute('SELECT id,request_fingerprint FROM reminders WHERE user_id=? AND request_key=?',(uid,request_key)).fetchone()
                if old:
                    if old[1]!=fingerprint:
                        raise ReminderConflict('请求编号已用于其他内容，或旧版记录无法核验；请刷新提醒并使用新的请求编号')
                    return self.get(uid,old[0])
            if not now-2<=due<=now+31536000:raise ValueError('提醒时间应在未来一年内')
            if self.memory.db.execute('SELECT COUNT(*) FROM reminders WHERE user_id=? AND delivered=0',(uid,)).fetchone()[0]>=100:raise ValueError('待办提醒已达 100 条，请先整理')
            # Bound retained completed rows, while preserving active reminders.
            self.memory.db.execute('DELETE FROM reminders WHERE user_id=? AND delivered=1 AND id NOT IN (SELECT id FROM reminders WHERE user_id=? AND delivered=1 ORDER BY id DESC LIMIT 200)',(uid,uid))
            c=self.memory.db.execute('INSERT INTO reminders(user_id,due,text,request_key,repeat_seconds,kind,request_fingerprint) VALUES (?,?,?,?,?,?,?)',(uid,due,self.memory.cipher.dump(text),request_key,repeat_seconds,kind,fingerprint));self.memory.db.commit()
            return self.get(uid,c.lastrowid)

    def get(self,uid,rid):
        with self.memory.lock:
            row=self.memory.db.execute('SELECT id,due,text,delivered,repeat_seconds,kind FROM reminders WHERE user_id=? AND id=?',(uid,rid)).fetchone()
            return self._row(row) if row else None

    def _row(self,row):
        return dict(id=row[0],due_unix=row[1],text=self.memory.cipher.load(row[2]),status='done' if row[3] else 'pending',repeat_seconds=row[4],kind=row[5],overdue_seconds=max(0,round(self.clock()-row[1])),occurrence=f'{row[0]}:{row[1]:.6f}')

    def reminders(self,uid,due_only=False):
        with self.memory.lock:
            rows=self.memory.db.execute('SELECT id,due,text,delivered,repeat_seconds,kind FROM reminders WHERE user_id=? AND delivered=0 ORDER BY due LIMIT 100',(uid,)).fetchall()
            return [self._row(r) for r in rows if not due_only or r[1]<=self.clock()]

    def resolve(self,uid,rid,action,occurrence,minutes=10):
        if action not in {'ack','snooze','cancel'}:raise ValueError('未知提醒操作')
        if action=='snooze' and (not isinstance(minutes,int) or not 1<=minutes<=1440):raise ValueError('延后时间应为 1 到 1440 分钟')
        with self.memory.lock:
            item=self.get(uid,rid)
            if not item:return None
            if item['occurrence']!=occurrence:return {'status':'stale_occurrence','item':item}
            if action=='cancel':self.memory.db.execute('DELETE FROM reminders WHERE user_id=? AND id=?',(uid,rid))
            elif item['status']=='done':return {'status':'already_done','item':item}
            elif action=='snooze':self.memory.db.execute('UPDATE reminders SET due=? WHERE user_id=? AND id=?',(self.clock()+minutes*60,uid,rid))
            elif item['repeat_seconds']:
                step=item['repeat_seconds'];due=item['due_unix']+max(1,int((self.clock()-item['due_unix'])//step)+1)*step
                self.memory.db.execute('UPDATE reminders SET due=? WHERE user_id=? AND id=?',(due,uid,rid))
            else:self.memory.db.execute('UPDATE reminders SET delivered=1 WHERE user_id=? AND id=?',(uid,rid))
            self.memory.db.commit();return {'status':action,'item':self.get(uid,rid)}

    def poll(self,uid,present=False,busy=False):
        """Reads reminders without acknowledging them. Proactivity is explicit opt-in."""
        now=self.clock();settings=self.settings(uid);p=self.memory.profile(uid)
        reminders=self.reminders(uid,True) if p and p['memory_consent'] else []
        runtime=p.get('care_runtime',{}) if p else {}
        stored=self.memory.read(uid) if p and p['memory_consent'] else {}
        hour=datetime.fromtimestamp(now,timezone(timedelta(minutes=settings['utc_offset_minutes']))).hour
        start,end=settings['quiet_start'],settings['quiet_end']
        quiet=(start<=hour<end) if start<end else (hour>=start or hour<end) if start>end else False
        with self.memory.lock, self.lock:
            last=self.activity.setdefault(uid,now)
            reason='not_enabled' if not settings['proactive_enabled'] else 'quiet_hours' if quiet else 'no_confirmed_presence' if not present else 'busy' if busy else 'user_requested_quiet' if uid in self.paused or runtime.get('paused') or stored.get('boundary_state')=='do_not_disturb' or stored.get('preferred_style')=='silent' else 'cooldown' if now-max(last,runtime.get('last_offer',now))<settings['interval_minutes']*60 else 'ready'
            offer=None
            if reason=='ready':
                with self.memory.lock:
                    p=self.memory.profile(uid)
                    if not p or not p['memory_consent']:return {'reminders':[], 'check_in':None,'reason':'consent_required'}
                    runtime=p.setdefault('care_runtime',{});runtime['last_offer']=now
                    self.memory.db.execute('UPDATE profiles SET payload=? WHERE id=?',(self.memory.cipher.dump(p),uid));self.memory.db.commit()
                offer={'kind':'gentle_check_in','text':'现在想聊一会儿，还是让我安静陪着？','automatic_audio':False}
            return {'reminders':reminders,'check_in':offer,'reason':reason,'quiet_hours':quiet,'automatic_audio':False}

    def preflight(self,observation):
        speech=observation.speech
        safety=triage(speech,observation.asr_confidence)
        if safety:return safety
        if not observation.person_present or observation.asr_confidence<.65:return None
        if re.search(r'(?:药|胰岛素).{0,14}(?:加量|减量|停用|停药|多吃|少吃|补服|漏服|补吃|忘.{0,3}吃|吃几|吃多少|剂量)|(?:多吃|少吃|加量|减量|停用|漏服).{0,10}(?:药|胰岛素)',speech):
            return {'kind':'medication_boundary','priority':'attention','response':'药物剂量、停药或漏服后的处理，请按医生、药师或药品说明确认，我不能替你调整。你可以设置一个按既定医嘱核对用药的提醒。'}
        if observation.reminder_after_seconds and observation.reminder_text:return None
        parsed=reminder_request(speech)
        if not parsed:return None
        if parsed.get('clarify'):return {'kind':'reminder_clarification','priority':'normal','response':'请告诉我明确的时间和内容，例如“五分钟后提醒我给花浇水”。具体日期或每天重复的提醒，可以在提醒设置中填写。'}
        if not observation.identity_verified or not observation.memory_consent:return {'kind':'reminder_needs_consent','priority':'normal','response':'还没有保存提醒。请先登录并开启长期记忆，再告诉我提醒的时间和内容。'}
        # Short dedupe window prevents the same recognized utterance creating a burst.
        key=self.memory.cipher.index(f'{observation.session_id}:{speech}:{int(self.clock()//30)}')
        try:item=self.add(observation.user_id,parsed['text'],self.clock()+parsed['delay_seconds'],key,kind='medication' if re.search(r'吃药|用药|服药',parsed['text']) else 'general',delay_seconds=parsed['delay_seconds'])
        except ValueError as e:return {'kind':'reminder_error','priority':'attention','response':str(e)+'，提醒尚未保存。'}
        return {'kind':'reminder_saved','priority':'normal','response':f"已保存提醒：{parsed['text']}。约 {parsed['delay_seconds']} 秒后到期，可在提醒里查看、延后或取消。服务和接收端需要保持运行。",'reminder':item}

def fast_result(event):
    """Same UI-facing envelope without waiting for the language-model lock."""
    from .human_state import HumanState
    from .temporal import response_plan
    state=HumanState();plan=response_plan(state);plan['verbal_response']=event['response'];plan['response_strategy']='urgent_support' if event['priority']=='urgent' else event['kind']
    return dict(version='5.2.0',action='RESPOND',response=event['response'],care={**event,'human_contact_sent':False,'clinical_detection_validated':False},
        boundary_state='open',motion={'requested':False,'authorized':False,'command':'HOLD'},task={'requested':False,'authorized':False,'execution_status':'not_executed'},human_request=False,
        state={'dialogue_profile':{},'emotion':{},'facial_expression':{}},dialogue={'status':'care_controller','action_authority':False},neural={},retrieved_memories=[],
        memory={'writes':[],'retrieved_count':0,'reason':'care_controller_no_automatic_fact_write'},memory_persisted=False,human_state=state.model_dump(),response_plan=plan,latency_ms=0)
