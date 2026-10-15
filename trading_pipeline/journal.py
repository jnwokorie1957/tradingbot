"""Append-only, hash-chained experiment receipts; exclusive experiment claims."""
import hashlib,json,sqlite3
from .engine_v3 import utc
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
  self.db.executescript("""
   CREATE TABLE IF NOT EXISTS consumed_validation(experiment TEXT PRIMARY KEY,content_hash TEXT,start TEXT,end TEXT,contracts TEXT);
   CREATE TRIGGER IF NOT EXISTS consumed_no_update BEFORE UPDATE ON consumed_validation BEGIN SELECT RAISE(ABORT,'immutable'); END;
   CREATE TRIGGER IF NOT EXISTS consumed_no_delete BEFORE DELETE ON consumed_validation BEGIN SELECT RAISE(ABORT,'immutable'); END;
  """)
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
 def consume_validation(self,experiment,manifest,contracts):
  spec=manifest['files']['validation'];start=utc(spec['start']);end=utc(spec['end'])
  # Broker contract IDs are stable across file encodings, aliases and dataset names.
  ids=sorted({str(c['contract_id']) for c in contracts.values()})
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   for exp,payload in self.db.execute("SELECT experiment,payload FROM records WHERE kind='trial_started'"):
    if json.loads(payload).get('phase')=='validation' and not self.db.execute('SELECT 1 FROM consumed_validation WHERE experiment=?',(exp,)).fetchone():
     raise ValueError('legacy_validation_exposure_requires_registry_reconciliation')
   for exp,h,a,b,keys in self.db.execute('SELECT * FROM consumed_validation'):
    if h==spec['sha256'] or (set(ids)&set(json.loads(keys)) and start<utc(b) and utc(a)<end):
     raise ValueError('validation_consumed_or_overlapping')
   self.db.execute('INSERT INTO consumed_validation VALUES(?,?,?,?,?)',(experiment,spec['sha256'],start.isoformat(),end.isoformat(),canonical(ids)))
   self._append(experiment,'validation_consumed',dict(content_hash=spec['sha256'],start=start.isoformat(),end=end.isoformat(),contract_ids=ids,shared_comparisons='registered_scenarios_within_this_experiment_only'))
 def verify(self):
  previous='0'*64
  for exp,kind,at,payload,prev,h in self.db.execute('SELECT experiment,kind,at,payload,previous,hash FROM records ORDER BY seq'):
   if prev!=previous or h!=digest([exp,kind,at,payload,prev]):raise ValueError('journal integrity failure')
   previous=h
  return previous
 def close(self):self.db.close()
