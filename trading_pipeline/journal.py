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
  self.db.executescript("""
   CREATE TABLE IF NOT EXISTS reserved_training(experiment TEXT PRIMARY KEY,content_hash TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,contracts TEXT NOT NULL);
   CREATE TRIGGER IF NOT EXISTS training_no_update BEFORE UPDATE ON reserved_training BEGIN SELECT RAISE(ABORT,'immutable training reservation'); END;
   CREATE TRIGGER IF NOT EXISTS training_no_delete BEFORE DELETE ON reserved_training BEGIN SELECT RAISE(ABORT,'immutable training reservation'); END;
   CREATE TRIGGER IF NOT EXISTS training_conflict_guard BEFORE INSERT ON reserved_training
   WHEN EXISTS(SELECT 1 FROM consumed_validation v WHERE v.content_hash=NEW.content_hash OR
    (julianday(NEW.start)<julianday(v.end) AND julianday(v.start)<julianday(NEW.end) AND
     EXISTS(SELECT 1 FROM json_each(NEW.contracts) a JOIN json_each(v.contracts) b ON a.value=b.value)))
   BEGIN SELECT RAISE(ABORT,'training_reuses_consumed_validation'); END;
   CREATE TRIGGER IF NOT EXISTS validation_training_conflict_guard BEFORE INSERT ON consumed_validation
   WHEN EXISTS(SELECT 1 FROM reserved_training t WHERE t.content_hash=NEW.content_hash OR
    (julianday(NEW.start)<julianday(t.end) AND julianday(t.start)<julianday(NEW.end) AND
     EXISTS(SELECT 1 FROM json_each(NEW.contracts) a JOIN json_each(t.contracts) b ON a.value=b.value)))
   BEGIN SELECT RAISE(ABORT,'validation_reuses_reserved_training'); END;
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
 def _require_reconciled_exposure(self):
  for exp,payload in self.db.execute("SELECT experiment,payload FROM records WHERE kind='trial_started'"):
   phase=json.loads(payload).get('phase')
   table={'training':'reserved_training','validation':'consumed_validation'}.get(phase)
   if table and not self.db.execute('SELECT 1 FROM '+table+' WHERE experiment=?',(exp,)).fetchone():
    raise ValueError('legacy_'+phase+'_exposure_requires_registry_reconciliation')
 def _exposure(self,experiment,manifest,contracts,phase):
  spec=manifest['files'][phase];start=utc(spec['start']);end=utc(spec['end'])
  ids=sorted({str(c['contract_id']) for c in contracts.values()})
  if not start<end:raise ValueError('invalid_exposure_interval')
  # All readers/consumers serialize on the same database write lock, then commit
  # an immutable exposure record. Never release on failed admission or restart.
  with self.db:
   self.db.execute('BEGIN IMMEDIATE')
   self._require_reconciled_exposure()
   checks=[('consumed_validation','training_reuses_consumed_validation' if phase=='train' else 'validation_consumed_or_overlapping')]
   if phase=='validation':checks.append(('reserved_training','validation_reuses_reserved_training'))
   for table,reason in checks:
    for exp,h,a,b,keys in self.db.execute('SELECT * FROM '+table):
     if h==spec['sha256'] or (set(ids)&set(json.loads(keys)) and start<utc(b) and utc(a)<end):raise ValueError(reason)
   table,kind=('reserved_training','training_reserved') if phase=='train' else ('consumed_validation','validation_consumed')
   self.db.execute('INSERT INTO '+table+' VALUES(?,?,?,?,?)',(experiment,spec['sha256'],start.isoformat(),end.isoformat(),canonical(ids)))
   self._append(experiment,kind,dict(content_hash=spec['sha256'],start=start.isoformat(),end=end.isoformat(),contract_ids=ids,protocol='atomic_exposure_v1',shared_comparisons='registered_scenarios_within_this_experiment_only'))
 def reserve_training(self,experiment,manifest,contracts):
  self._exposure(experiment,manifest,contracts,'train')
 def consume_validation(self,experiment,manifest,contracts):
  self._exposure(experiment,manifest,contracts,'validation')
 def verify(self):
  previous='0'*64
  for exp,kind,at,payload,prev,h in self.db.execute('SELECT experiment,kind,at,payload,previous,hash FROM records ORDER BY seq'):
   if prev!=previous or h!=digest([exp,kind,at,payload,prev]):raise ValueError('journal integrity failure')
   previous=h
  return previous
 def close(self):self.db.close()
