"""Append-only, hash-chained experiment receipts; exclusive experiment claims."""
import hashlib,json,sqlite3
from datetime import datetime,timezone

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def utc_now():return datetime.now(timezone.utc).isoformat()

class Journal:
 def __init__(self,path):
  self.db=sqlite3.connect(path,timeout=10)
  self.db.execute('PRAGMA synchronous=FULL')
  self.db.executescript('''
   CREATE TABLE IF NOT EXISTS records(seq INTEGER PRIMARY KEY,experiment TEXT,kind TEXT,at TEXT,payload TEXT,previous TEXT,hash TEXT UNIQUE);
   CREATE TABLE IF NOT EXISTS claims(experiment TEXT PRIMARY KEY,plan_hash TEXT NOT NULL);
   CREATE TRIGGER IF NOT EXISTS records_no_update BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT,'immutable'); END;
   CREATE TRIGGER IF NOT EXISTS records_no_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT,'immutable'); END;
   CREATE TRIGGER IF NOT EXISTS claims_no_update BEFORE UPDATE ON claims BEGIN SELECT RAISE(ABORT,'immutable'); END;
   CREATE TRIGGER IF NOT EXISTS claims_no_delete BEFORE DELETE ON claims BEGIN SELECT RAISE(ABORT,'immutable'); END;
  ''')
  self.verify()
 def append(self,experiment,kind,payload):
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   self._append(experiment,kind,payload)
 def _append(self,experiment,kind,payload):
  prior=self.db.execute('SELECT hash FROM records ORDER BY seq DESC LIMIT 1').fetchone()
  previous=prior[0] if prior else '0'*64;at=utc_now();encoded=canonical(payload)
  value=digest([experiment,kind,at,encoded,previous])
  self.db.execute('INSERT INTO records(experiment,kind,at,payload,previous,hash) VALUES(?,?,?,?,?,?)',(experiment,kind,at,encoded,previous,value))
 def claim(self,experiment,plan_hash):
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   self.db.execute('INSERT INTO claims VALUES(?,?)',(experiment,plan_hash))
   self._append(experiment,'started',{'plan_hash':plan_hash})
 def verify(self):
  previous='0'*64
  for exp,kind,at,payload,prev,h in self.db.execute('SELECT experiment,kind,at,payload,previous,hash FROM records ORDER BY seq'):
   if prev!=previous or h!=digest([exp,kind,at,payload,prev]):raise ValueError('journal integrity failure')
   previous=h
  return previous
 def close(self):self.db.close()
