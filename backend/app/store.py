"""SQLite persistence: full transcript across all scenarios + current state."""
import json, sqlite3, threading, time


class Store:
    def __init__(self, path="ares.db"):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("create table if not exists messages(id integer primary key autoincrement, scenario text, round int, plan_version int, frm text, type text, text text, source text, ts real)")
        self.db.execute("create table if not exists kv(k text primary key, v text)")
        self.db.commit()

    def add(self, scenario, round, plan_version, frm, type, text, source="rule"):
        with self.lock:
            c = self.db.execute("insert into messages(scenario,round,plan_version,frm,type,text,source,ts) values(?,?,?,?,?,?,?,?)", (scenario, round, plan_version, frm, type, text, source, time.time()))
            self.db.commit()
            return dict(id=c.lastrowid, scenario=scenario, round=round, plan_version=plan_version, frm=frm, type=type, text=text, source=source)

    def messages(self, since=0):
        with self.lock:
            cur = self.db.execute("select id,scenario,round,plan_version,frm,type,text,source from messages where id>? order by id", (since,))
            return [dict(zip(["id", "scenario", "round", "plan_version", "frm", "type", "text", "source"], r)) for r in cur]

    def get_state(self):
        with self.lock:
            r = self.db.execute("select v from kv where k='state'").fetchone()
            return json.loads(r[0]) if r else None

    def set_state(self, s):
        with self.lock:
            self.db.execute("insert or replace into kv values('state',?)", (json.dumps(s),)); self.db.commit()

    def reset(self):
        with self.lock:
            self.db.execute("delete from messages"); self.db.execute("delete from kv"); self.db.commit()
