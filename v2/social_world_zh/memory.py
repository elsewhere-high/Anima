import sqlite3,json,time,threading

class MemoryStore:
    """Store explicit preferences only for verified, consenting identities."""
    def __init__(self,path):
        self.lock=threading.RLock()
        self.db=sqlite3.connect(str(path),check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, user_id TEXT, due REAL, text TEXT, delivered INTEGER DEFAULT 0)')
        self.db.commit()
    @staticmethod
    def empty():
        return dict(relationship='unknown',interaction_count=0,positive_interactions=0,rejection_count=0,preferred_distance=1.2,preferred_style='neutral',boundary_state='open',known_topics=[],memories=[],recent_actions=[],trust=None)
    def read(self,uid):
        with self.lock:
            r=self.db.execute('SELECT data FROM users WHERE id=?',(uid,)).fetchone()
            return json.loads(r[0]) if r else self.empty()
    @staticmethod
    def retrieve(state,query,limit=5):
        # Cheap lexical relevance; never loads a second embedding model.
        def tokens(s):
            s=s.casefold()
            return set(s.split()) | {s[i:i+2] for i in range(max(0,len(s)-1))}
        q=tokens(query)
        ranked=sorted(enumerate(state['memories']),key=lambda pair:(len(q & tokens(pair[1])),pair[0]),reverse=True)
        return [note for _,note in ranked[:limit]]
    def update(self,uid,state):
        with self.lock:
            self.db.execute('INSERT INTO users VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(uid,json.dumps(state,ensure_ascii=False))); self.db.commit()
    def forget(self,uid):
        with self.lock:
            self.db.execute('DELETE FROM users WHERE id=?',(uid,)); self.db.execute('DELETE FROM reminders WHERE user_id=?',(uid,)); self.db.commit()
    def remind(self,uid,seconds,text):
        with self.lock:
            due=time.time()+seconds
            c=self.db.execute('INSERT INTO reminders(user_id,due,text) VALUES (?,?,?)',(uid,due,text)); self.db.commit()
            return dict(id=c.lastrowid,due_unix=due,text=text)
    def due(self,uid):
        with self.lock:
            rows=self.db.execute('SELECT id,due,text FROM reminders WHERE user_id=? AND due<=? AND delivered=0',(uid,time.time())).fetchall()
            # At-least-once until explicit acknowledgement by the caller.
            return [dict(id=r[0],due_unix=r[1],text=r[2]) for r in rows]
    def acknowledge(self,uid,rid):
        with self.lock:
            c=self.db.execute('UPDATE reminders SET delivered=1 WHERE id=? AND user_id=?',(rid,uid)); self.db.commit(); return c.rowcount>0
