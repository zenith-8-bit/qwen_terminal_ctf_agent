import sqlite3, threading, time, json, hashlib

class State:
    def __init__(self, path="agent.db"):
        self.path = path
        self.lock = threading.Lock()
        with self.db() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS state(
                id INTEGER PRIMARY KEY CHECK(id=1),
                user TEXT, level TEXT, status TEXT, mission TEXT,
                plan TEXT, hypothesis TEXT, command TEXT, output TEXT,
                cwd TEXT, candidate TEXT, step INTEGER, updated REAL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
                step INTEGER, kind TEXT, data TEXT)''')
            if c.execute("SELECT COUNT(*) FROM state").fetchone()[0] == 0:
                c.execute("INSERT INTO state VALUES(1,'','','idle','','','','','','','',0,?)",(time.time(),))

    def db(self):
        return sqlite3.connect(self.path)

    def update(self, **kw):
        with self.lock, self.db() as c:
            row = c.execute("SELECT user,level,status,mission,plan,hypothesis,command,output,cwd,candidate,step,updated FROM state WHERE id=1").fetchone()
            keys=["user","level","status","mission","plan","hypothesis","command","output","cwd","candidate","step","updated"]
            vals=dict(zip(keys,row))
            vals.update(kw); vals["updated"]=time.time()
            c.execute("UPDATE state SET "+",".join(k+"=?" for k in keys)+" WHERE id=1",[vals[k] for k in keys])

    def event(self, step, kind, data):
        with self.lock, self.db() as c:
            c.execute("INSERT INTO events(ts,step,kind,data) VALUES(?,?,?,?)",(time.time(),step,kind,json.dumps(data)))

    def seen_commands(self):
        with self.db() as c:
            rows=c.execute("SELECT data FROM events WHERE kind='command'").fetchall()
        return {json.loads(x[0]).get("command","").strip() for x in rows}

    def snapshot(self):
        with self.db() as c:
            row=c.execute("SELECT user,level,status,mission,plan,hypothesis,command,output,cwd,candidate,step,updated FROM state").fetchone()
            events=c.execute("SELECT ts,step,kind,data FROM events ORDER BY id DESC LIMIT 150").fetchall()
        return {
            "state": dict(zip(("user","level","status","mission","plan","hypothesis","command","output","cwd","candidate","step","updated"),row)),
            "events":[{"ts":x[0],"step":x[1],"kind":x[2],"data":json.loads(x[3])} for x in events]
        }
