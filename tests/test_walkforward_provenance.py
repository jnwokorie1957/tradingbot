"""Durable negative probes: no dataset access before provenance rejection."""
import copy,json,sqlite3,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from trading_pipeline.closing_walkforward_fixtures import create
from trading_pipeline.closing_walkforward import register,run
from trading_pipeline.journal import Journal

class WalkforwardProvenanceTests(unittest.TestCase):
 def check_rejected_before_reads(self,case):
  base=Path(__file__).resolve().parents[1]/'local-results'/('provenance-'+uuid.uuid4().hex)
  plan,m,c=create(base/'data');dbpath=base/'journal.sqlite';j=Journal(str(dbpath))
  if case=='legacy':
   j.append('legacy-validation','trial_started',dict(phase='validation',trial_id='old'))
   expected='legacy_validation_exposure_requires_registry_reconciliation'
  else:
   consumed=copy.deepcopy(m)
   consumed['files']['validation']=dict(path='irrelevant',sha256=m['files']['train']['sha256'],start='2000-01-01T00:00:00Z',end='2000-01-02T00:00:00Z')
   prior_contracts=copy.deepcopy(c);prior_contracts['TEST']['contract_id']=999
   j.consume_validation('prior-other-contract',consumed,prior_contracts)
   expected='training_reuses_consumed_validation'
  j.close();j=Journal(str(dbpath))
  try:
   p=register(j,'new-study',plan,m,c)
   with patch('trading_pipeline.closing_walkforward.partition',side_effect=AssertionError('dataset read forbidden')) as market,patch('trading_pipeline.closing_walkforward.administrative',side_effect=AssertionError('admin read forbidden')) as admin:
    result=run(j,'new-study',p,m,c,base/'data',base/'output')
    market.assert_not_called();admin.assert_not_called()
   self.assertEqual(result['status'],'blocked_or_failed');self.assertEqual(result['reason'],expected);self.assertEqual(result['trials'],[])
   self.assertFalse((base/'output').exists())
  finally:j.close()
  j=Journal(str(dbpath))
  try:
   rows=j.db.execute("SELECT payload FROM records WHERE experiment='new-study' AND kind='finished'").fetchall()
   self.assertEqual(len(rows),1);self.assertEqual(json.loads(rows[0][0])['reason'],expected)
   self.assertEqual(j.db.execute("SELECT count(*) FROM records WHERE experiment='new-study' AND kind='trial_started'").fetchone()[0],0)
   self.assertEqual(j.db.execute("SELECT count(*) FROM claims WHERE experiment='new-study'").fetchone()[0],1)
   with self.assertRaises(sqlite3.IntegrityError):run(j,'new-study',p,m,c,base/'data',base/'retry')
   self.assertEqual(j.verify(),result['journal_head'])
  finally:j.close()
 def test_unreconciled_legacy_validation_rejected_before_any_reads(self):self.check_rejected_before_reads('legacy')
 def test_exact_consumed_hash_other_contract_and_interval_rejected_before_any_reads(self):self.check_rejected_before_reads('hash')
