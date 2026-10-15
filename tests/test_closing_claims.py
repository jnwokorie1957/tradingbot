import json,sqlite3,threading,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from trading_pipeline.closing_run import run_once
from trading_pipeline.closing_fixtures import create
from trading_pipeline.engine_v4 import Ledger,digest

class ClosingClaimTests(unittest.TestCase):
 def path(self):
  p=Path(__file__).resolve().parents[1]/'local-results'/('claims-'+uuid.uuid4().hex)
  p.mkdir(parents=True);return p/'ledger.sqlite'
 def test_failed_admission_consumes_id_and_input_hash(self):
  l=Ledger(':memory:')
  try:
   bad=create();bad['synthetic']=False
   self.assertEqual(run_once(l,'same',bad)['status'],'failed')
   with self.assertRaisesRegex(ValueError,'run_id_already_used'):run_once(l,'same',create())
   self.assertEqual(l.db.execute('SELECT input_hash FROM closing_run_claims').fetchone()[0],digest(bad))
   self.assertEqual(l.db.execute('SELECT count(*) FROM trials').fetchone()[0],1)
   self.assertEqual(l.db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
  finally:l.close()
 def test_failed_admission_claim_survives_restart(self):
  path=self.path();l=Ledger(str(path));bad=create();bad['synthetic']=False
  run_once(l,'same',bad);l.close();l=Ledger(str(path))
  try:
   with self.assertRaisesRegex(ValueError,'run_id_already_used'):run_once(l,'same',create())
   self.assertEqual(json.loads(l.db.execute('SELECT result FROM trials').fetchone()[0])['status'],'failed')
  finally:l.close()
 def test_interrupt_before_engine_creation_leaves_claim_and_started_trial(self):
  path=self.path();l=Ledger(str(path));bundle=create()
  try:
   with patch('trading_pipeline.closing_run.ClosingEngine',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):run_once(l,'interrupted',bundle)
  finally:l.close()
  l=Ledger(str(path))
  try:
   self.assertEqual(l.db.execute('SELECT input_hash FROM closing_run_claims').fetchone()[0],digest(bundle))
   self.assertIsNone(l.db.execute('SELECT result FROM trials').fetchone()[0])
   with self.assertRaisesRegex(ValueError,'run_id_already_used'):run_once(l,'interrupted',bundle)
  finally:l.close()
 def test_concurrent_claims_exactly_one_winner(self):
  path=self.path();initial=Ledger(str(path));initial.close();barrier=threading.Barrier(2)
  def worker(n):
   l=Ledger(str(path));b=create();b.update(synthetic=False,claim_probe=n)
   try:
    barrier.wait(timeout=10)
    try:return ('won',digest(b),run_once(l,'contended',b)['status'])
    except ValueError as exc:return ('rejected',digest(b),str(exc))
   finally:l.close()
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[1,2]))
  self.assertEqual(sorted(r[0] for r in results),['rejected','won'])
  l=Ledger(str(path))
  try:
   self.assertEqual(l.db.execute('SELECT count(*) FROM closing_run_claims').fetchone()[0],1)
   self.assertEqual(l.db.execute('SELECT count(*) FROM trials').fetchone()[0],1)
   self.assertEqual(l.db.execute('SELECT input_hash FROM closing_run_claims').fetchone()[0],next(r[1] for r in results if r[0]=='won'))
  finally:l.close()
 def test_claims_cannot_be_updated_or_deleted(self):
  l=Ledger(':memory:');b=create();b['synthetic']=False
  try:
   run_once(l,'immutable',b)
   for sql in ['DELETE FROM closing_run_claims','UPDATE closing_run_claims SET input_hash="changed"']:
    with self.assertRaises(sqlite3.IntegrityError):l.db.execute(sql)
    l.db.rollback()
  finally:l.close()
 def test_legacy_failed_trial_blocks_reuse_without_claim(self):
  l=Ledger(':memory:')
  try:
   with l.db:l.db.execute('INSERT INTO trials(metadata,result) VALUES(?,?)',(json.dumps({'run_id':'legacy'}),json.dumps({'status':'failed'})))
   with self.assertRaisesRegex(ValueError,'run_id_already_used'):run_once(l,'legacy',create())
   self.assertEqual(l.db.execute('SELECT count(*) FROM trials').fetchone()[0],1)
  finally:l.close()
