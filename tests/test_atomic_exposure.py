"""Two-connection provenance protocol and durable exposure regressions."""
import copy,json,sqlite3,threading,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from trading_pipeline.journal import Journal
from trading_pipeline.engine_v4 import Ledger
from trading_pipeline.closing_walkforward_fixtures import create
from trading_pipeline import closing_walkforward as closing
from trading_pipeline import runner as generic
from trading_pipeline.fixtures import create as generic_fixture

class AtomicExposureTests(unittest.TestCase):
 def setUp(self):
  self.base=Path(__file__).resolve().parents[1]/'local-results'/('atomic-'+uuid.uuid4().hex)
  self.plan,self.m,self.c=create(self.base/'data');self.path=self.base/'journal.sqlite'
  self.j=Journal(str(self.path));self.peer=Journal(str(self.path))
  self.peer_m=copy.deepcopy(self.m);self.peer_m['files']['validation']=copy.deepcopy(self.m['files']['train'])
 def tearDown(self):self.peer.close();self.j.close()
 def test_training_first_blocks_validation_other_contract_and_interval(self):
  self.j.reserve_training('train',self.m,self.c)
  c=copy.deepcopy(self.c);c['TEST']['contract_id']=999
  m=copy.deepcopy(self.peer_m);m['files']['validation'].update(start='2000-01-01T00:00:00Z',end='2000-01-02T00:00:00Z')
  with self.assertRaisesRegex(ValueError,'validation_reuses_reserved_training'):self.peer.consume_validation('validation',m,c)
  self.assertEqual(self.peer.db.execute('SELECT count(*) FROM consumed_validation').fetchone()[0],0)
 def test_validation_first_blocks_training(self):
  self.peer.consume_validation('validation',self.peer_m,self.c)
  with self.assertRaisesRegex(ValueError,'training_reuses_consumed_validation'):self.j.reserve_training('train',self.m,self.c)
  self.assertEqual(self.j.db.execute('SELECT count(*) FROM reserved_training').fetchone()[0],0)
 def test_simultaneous_contention_exactly_one_commits(self):
  barrier=threading.Barrier(2)
  def worker(kind):
   journal=Journal(str(self.path))
   try:
    barrier.wait(timeout=10)
    try:
     if kind=='train':journal.reserve_training('race-train',self.m,self.c)
     else:journal.consume_validation('race-validation',self.peer_m,self.c)
     return 'won'
    except ValueError:return 'rejected'
   finally:journal.close()
  with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(worker,['train','validation']))
  self.assertEqual(sorted(result),['rejected','won'])
  self.assertEqual(sum(self.j.db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['reserved_training','consumed_validation']),1)
  self.assertEqual(self.j.db.execute("SELECT count(*) FROM records WHERE kind IN ('training_reserved','validation_consumed')").fetchone()[0],1)
  self.j.verify()
 def test_restart_retains_reservation_after_interrupted_reader(self):
  self.j.reserve_training('interrupted',self.m,self.c);self.j.close();self.j=Journal(str(self.path))
  self.assertEqual(self.j.db.execute('SELECT content_hash FROM reserved_training').fetchone()[0],self.m['files']['train']['sha256'])
  with self.assertRaisesRegex(ValueError,'validation_reuses_reserved_training'):self.peer.consume_validation('validation',self.peer_m,self.c)
  self.j.verify()
 def test_receipt_failure_rolls_back_reservation_atomically(self):
  with patch.object(self.j,'_append',side_effect=RuntimeError('simulated interrupted transaction')):
   with self.assertRaises(RuntimeError):self.j.reserve_training('rolledback',self.m,self.c)
  self.assertEqual(self.peer.db.execute('SELECT count(*) FROM reserved_training').fetchone()[0],0)
  self.peer.consume_validation('winner',self.peer_m,self.c)
 def test_old_style_consumer_insert_is_guarded_by_database(self):
  self.j.reserve_training('train',self.m,self.c);s=self.peer_m['files']['validation']
  with self.assertRaisesRegex(sqlite3.IntegrityError,'validation_reuses_reserved_training'):
   with self.peer.db:self.peer.db.execute('INSERT INTO consumed_validation VALUES(?,?,?,?,?)',('old-consumer',s['sha256'],s['start'],s['end'],json.dumps(['1'])))
  self.assertEqual(self.j.db.execute('SELECT count(*) FROM consumed_validation').fetchone()[0],0)
 def test_different_encoding_overlap_still_conflicts(self):
  self.j.reserve_training('train',self.m,self.c);self.peer_m['files']['validation']['sha256']='different'
  with self.assertRaisesRegex(ValueError,'validation_reuses_reserved_training'):self.peer.consume_validation('peer',self.peer_m,self.c)
 def test_closing_runner_blocks_peer_at_exact_read_boundary(self):
  frozen=closing.register(self.j,'closing',self.plan,self.m,self.c);original=closing.administrative;blocked=[]
  def boundary(*args):
   with self.assertRaisesRegex(ValueError,'validation_reuses_reserved_training'):self.peer.consume_validation('peer-at-boundary',self.peer_m,self.c)
   blocked.append(True);return original(*args)
  with patch.object(closing,'administrative',side_effect=boundary),patch.object(closing,'Ledger',side_effect=lambda _:Ledger(':memory:')):
   result=closing.run(self.j,'closing',frozen,self.m,self.c,self.base/'data',self.base/'closing')
  self.assertEqual(result['status'],'completed_research_not_qualified');self.assertEqual(len(result['trials']),5);self.assertEqual(blocked,[True])
  self.assertIsNone(self.peer.db.execute("SELECT 1 FROM consumed_validation WHERE experiment='peer-at-boundary'").fetchone())
 def test_generic_runner_uses_same_protocol_before_read(self):
  p,m,c=generic_fixture(self.base/'generic-data');peer=copy.deepcopy(m);peer['files']['validation']=copy.deepcopy(m['files']['train'])
  frozen=generic.register(self.j,'generic',p,m,c);original=generic.load_partition;blocked=[]
  def boundary(base,manifest,phase,contracts):
   if phase=='train':
    with self.assertRaisesRegex(ValueError,'validation_reuses_reserved_training'):self.peer.consume_validation('generic-peer',peer,c)
    blocked.append(True)
   return original(base,manifest,phase,contracts)
  with patch.object(generic,'load_partition',side_effect=boundary),patch.object(generic,'Ledger',side_effect=lambda _:Ledger(':memory:')):
   result=generic.run(self.j,'generic',frozen,m,c,self.base/'generic-data',self.base/'generic')
  self.assertEqual(result['status'],'completed_research_not_qualified');self.assertEqual(blocked,[True])
 def test_failed_read_keeps_reservation_across_restart(self):
  self.m['administrative']['sha256']='invalid';frozen=closing.register(self.j,'bad-read',self.plan,self.m,self.c)
  result=closing.run(self.j,'bad-read',frozen,self.m,self.c,self.base/'data',self.base/'bad')
  self.assertEqual(result['reason'],'evidence_hash_mismatch');self.assertFalse(result['trials'])
  self.j.close();self.j=Journal(str(self.path))
  with self.assertRaisesRegex(ValueError,'validation_reuses_reserved_training'):self.j.consume_validation('peer',self.peer_m,self.c)
 def test_reservation_is_immutable(self):
  self.j.reserve_training('train',self.m,self.c)
  for sql in ['DELETE FROM reserved_training','UPDATE reserved_training SET content_hash="changed"']:
   with self.assertRaises(sqlite3.IntegrityError):self.peer.db.execute(sql)
   self.peer.db.rollback()
 def test_unreconciled_legacy_training_blocks_validation(self):
  self.j.append('legacy','trial_started',dict(phase='training'))
  with self.assertRaisesRegex(ValueError,'legacy_training_exposure_requires_registry_reconciliation'):self.peer.consume_validation('peer',self.peer_m,self.c)
