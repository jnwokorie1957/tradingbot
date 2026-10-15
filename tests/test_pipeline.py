import copy,json,sqlite3,uuid,unittest
from pathlib import Path
from trading_pipeline.fixtures import create
from trading_pipeline.journal import Journal,digest
from trading_pipeline.runner import register,run
from trading_pipeline.dataset import validate_manifest,load_partition,AdmissionError
from trading_pipeline.metrics import summarize,assess,wilson

class PipelineTests(unittest.TestCase):
 def setUp(self):
  self.base=Path(__file__).resolve().parents[1]/'local-results'/('test-'+uuid.uuid4().hex);self.base.mkdir(parents=True)
  self.plan,self.m,self.c=create(self.base/'data');self.j=Journal(self.base/'journal.sqlite')
 def tearDown(self):self.j.close()
 def execute(self):
  p=register(self.j,'test',self.plan,self.m,self.c)
  return run(self.j,'test',p,self.m,self.c,self.base/'data',self.base/'results')
 def test_full_chronological_flow_and_holdout_not_opened(self):
  r=self.execute();self.assertEqual(r['status'],'completed_research_not_qualified');self.assertEqual(len(r['trials']),5)
  self.assertFalse(r['qualified_for_paper']);self.assertFalse(r['statistical_screen_pass']);self.assertEqual(r['final_holdout'],'untouched_locked')
  self.assertTrue(all(t['metrics']['closed_trades']==1 for t in r['trials']))
  kinds=[x[0] for x in self.j.db.execute('SELECT kind FROM records ORDER BY seq')]
  self.assertLess(kinds.index('selection_frozen'),[i for i,k in enumerate(kinds) if k=='trial_started'][1])
 def test_no_double_execution_or_reset(self):
  p=register(self.j,'test',self.plan,self.m,self.c);run(self.j,'test',p,self.m,self.c,self.base/'data',self.base/'results')
  with self.assertRaises(sqlite3.IntegrityError):run(self.j,'test',p,self.m,self.c,self.base/'data',self.base/'other')
 def test_missing_quotes_is_recorded_failure(self):
  self.m['quote_path_verified']=False;r=self.execute()
  self.assertEqual(r['reason'],'no_verified_next_quote_path');self.assertEqual(len(r['trials']),0)
  self.assertEqual(self.j.db.execute("SELECT count(*) FROM records WHERE kind='finished'").fetchone()[0],1)
 def test_risk_cannot_be_relaxed(self):
  self.plan['risk']['trade_risk']=.01;self.assertEqual(self.execute()['reason'],'risk_policy_change_prohibited')
 def test_protected_receipts_rejected_even_old_market_dates(self):
  self.m['source_kind']='legacy_ibkr_observer';self.assertEqual(self.execute()['reason'],'legacy_receipt_protected_no_scoring')
 def test_partition_overlap_rejected(self):
  self.m['files']['validation']['start']=self.m['files']['train']['start'];self.assertEqual(self.execute()['reason'],'chronological_partition_overlap')
 def test_final_holdout_unlock_rejected(self):
  self.m['final_holdout']['access']='unlocked';self.assertEqual(self.execute()['reason'],'final_holdout_not_locked')
 def test_embargo_covers_maximum_holding_period(self):
  self.m['files']['train']['end']=self.m['files']['validation']['start']
  self.assertEqual(self.execute()['reason'],'one_hour_holding_period_embargo_required')
 def test_data_hash_change_rejected_and_retained(self):
  with (self.base/'data/train.jsonl').open('a') as f:f.write('\n')
  self.assertEqual(self.execute()['reason'],'dataset_hash_mismatch')
 def test_registered_plan_cannot_change(self):
  p=register(self.j,'test',self.plan,self.m,self.c);p['hypotheses'][0]['lookback']=3
  self.assertEqual(run(self.j,'test',p,self.m,self.c,self.base/'data',self.base/'results')['reason'],'plan_not_registered')
 def test_journal_records_and_claims_are_immutable(self):
  self.execute()
  for statement in ['DELETE FROM records','UPDATE records SET kind="changed"','DELETE FROM claims']:
   with self.assertRaises(sqlite3.IntegrityError):self.j.db.execute(statement)
  self.j.db.rollback();self.assertEqual(len(self.j.verify()),64)
 def test_reused_validation_rejected_for_real_data(self):
  self.m['synthetic']=False;self.m['prior_exposure']='reused_development'
  with self.assertRaisesRegex(AdmissionError,'validation_previously_used'):validate_manifest(self.m,False)
 def test_no_trades_is_not_a_zero_percent_success_metric(self):
  m=summarize([],[],False);self.assertIsNone(m['win_rate']);self.assertIsNone(m['profit_factor']);self.assertIsNone(m['expectancy'])
  self.assertFalse(assess(m,synthetic=False,clean=True)['qualified_for_paper'])
 def test_wilson_reference(self):
  low,high=wilson(120,200);self.assertAlmostEqual(low,.53083672,places=6);self.assertAlmostEqual(high,.66539421,places=6)
 def test_stress_increases_costs(self):
  r=self.execute();v=[x for x in r['trials'] if x['phase']=='validation' and x['fold']==0]
  self.assertLess(v[1]['metrics']['net_pnl'],v[0]['metrics']['net_pnl'])
 def test_insufficient_training_does_not_open_validation(self):
  self.plan['hypotheses'][0]['lookback']=20
  (self.base/'data/validation.jsonl').unlink()
  r=self.execute();self.assertEqual(r['status'],'rejected_training_no_eligible_candidate')

if __name__=='__main__':unittest.main()
