import copy,hashlib,json,sqlite3,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from trading_pipeline.closing_walkforward_fixtures import create
from trading_pipeline.closing_walkforward import register,run
from trading_pipeline.closing_admission import fold_events
from trading_pipeline.engine_v4 import Ledger
from trading_pipeline.journal import Journal

class ClosingWalkforwardTests(unittest.TestCase):
 def setUp(self):
  self.base=Path(__file__).resolve().parents[1]/'local-results'/('wf-test-'+uuid.uuid4().hex)
  self.plan,self.m,self.c=create(self.base/'data');self.j=Journal(':memory:')
  # Unit probes use memory event ledgers; the separate CLI exercise verifies durable SQLite output.
  self.mock=patch('trading_pipeline.closing_walkforward.Ledger',side_effect=lambda _:Ledger(':memory:'));self.mock.start()
 def tearDown(self):self.mock.stop();self.j.close()
 def execute(self,name='test'):
  p=register(self.j,name,self.plan,self.m,self.c)
  return run(self.j,name,p,self.m,self.c,self.base/'data',self.base/name)
 def rewrite(self,spec,value,lines=False):
  p=self.base/'data'/spec['path'];p.write_text(''.join(json.dumps(e)+'\n' for e in value) if lines else json.dumps(value));spec['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 def market(self,phase):return [json.loads(x) for x in (self.base/'data'/self.m['files'][phase]['path']).read_text().splitlines()]
 def margin(self,at,effective,amount=600):return dict(id='margin',kind='margin_update',contract='TEST',available_at=at,effective_at=effective,valid_until='2026-02-01T00:00:00Z',initial_margin=amount,maintenance_margin=amount,verified=True,source='SYNTHETIC',currency='USD')
 def test_full_training_then_two_folds_two_costs_holdout_unopened(self):
  r=self.execute();self.assertEqual(r['status'],'completed_research_not_qualified');self.assertEqual(len(r['trials']),5)
  self.assertFalse(r['qualified_for_paper']);self.assertFalse(r['statistical_screen_pass']);self.assertEqual(r['final_holdout'],'untouched_locked')
  self.assertTrue(all(len(t['trades'])==1 for t in r['trials']))
  self.assertLess(r['trials'][2]['metrics']['net_pnl'],r['trials'][1]['metrics']['net_pnl'])
  kinds=[x[0] for x in self.j.db.execute('SELECT kind FROM records ORDER BY seq')]
  self.assertLess(kinds.index('selection_frozen'),kinds.index('validation_consumed'))
 def test_bad_quotes_gate_before_trials(self):
  self.m['quote_path_verified']=False;r=self.execute();self.assertEqual(r['reason'],'no_verified_next_quote_path');self.assertFalse(r['trials'])
 def test_legacy_protected_receipts_rejected(self):
  self.m['source_kind']='legacy_ibkr_observer';self.assertEqual(self.execute()['reason'],'legacy_receipt_protected_no_scoring')
 def test_protected_event_rejected(self):
  rows=self.market('train');rows[0]['partition']='protected_holdout_observation';self.rewrite(self.m['files']['train'],rows,True)
  self.assertEqual(self.execute()['reason'],'protected_observation')
 def test_hash_change_is_retained_failure(self):
  p=self.base/'data/train.jsonl';p.write_text(p.read_text()+'\n');r=self.execute();self.assertEqual(r['reason'],'dataset_hash_mismatch')
  self.assertEqual(self.j.db.execute("SELECT count(*) FROM records WHERE kind='finished'").fetchone()[0],1)
 def test_static_cost_evidence_required(self):
  self.m['static_costs_unchanged_verified']=False;self.assertEqual(self.execute()['reason'],'static_cost_coverage_unverified')
 def test_cost_coverage_shorter_than_study_rejected(self):
  self.c['TEST']['valid_until']='2026-01-08T21:00:00Z';self.assertEqual(self.execute()['reason'],'contract_cost_evidence_does_not_cover_study')
 def test_future_contract_evidence_rejected(self):
  self.c['TEST']['evidence_available_at']='2026-01-06T00:00:00Z';self.assertEqual(self.execute()['reason'],'contract_cost_evidence_does_not_cover_study')
 def test_complete_admin_history_required(self):
  self.m['administrative']['complete']=False;self.assertEqual(self.execute()['reason'],'complete_administrative_history_required')
 def test_pre_window_margin_announced_in_embargo_is_applied(self):
  self.rewrite(self.m['administrative'],[self.margin('2026-01-06T23:00:00Z','2026-01-07T00:00:00Z')])
  r=self.execute();self.assertEqual(r['trials'][0]['status'],'completed_research')
  self.assertTrue(all(t['skip_counts'].get('margin_and_loss_reserve')==1 for t in r['trials'][1:]));self.assertFalse(r['all_validation_windows_positive'])
 def test_future_announced_retroactive_margin_does_not_leak_back(self):
  self.rewrite(self.m['administrative'],[self.margin('2026-01-09T01:00:00Z','2026-01-07T00:00:00Z')])
  r=self.execute();self.assertEqual(len(r['trials'][1]['trades']),1)
  self.assertEqual(r['trials'][3]['skip_counts']['margin_and_loss_reserve'],1)
 def test_training_failure_does_not_open_validation(self):
  rows=self.market('train');rows[-1].update(bid=101,ask=101.25);self.rewrite(self.m['files']['train'],rows,True)
  (self.base/'data/validation.jsonl').unlink();(self.base/'data/validation-sessions.json').unlink()
  self.assertEqual(self.execute()['status'],'rejected_training')
 def test_same_id_cannot_restart_after_admission_failure(self):
  self.m['quote_path_verified']=False;self.execute();self.m['quote_path_verified']=True
  with self.assertRaises(sqlite3.IntegrityError):self.execute()
 def test_same_validation_rejected_under_new_experiment_id(self):
  self.execute();self.assertEqual(self.execute('second')['reason'],'validation_consumed_or_overlapping')
 def test_alternate_encoding_same_interval_is_not_fresh(self):
  self.execute();self.rewrite(self.m['files']['validation'],self.market('validation'),True)
  p=self.base/'data/validation.jsonl';p.write_text(p.read_text().replace(': ',':  '));self.m['files']['validation']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
  self.assertEqual(self.execute('second')['reason'],'validation_consumed_or_overlapping')
 def test_fold_overlap_rejected(self):
  self.plan['validation_windows'][1]['start']=self.plan['validation_windows'][0]['start'];self.assertEqual(self.execute()['reason'],'fold_overlap_or_missing_embargo')
 def test_short_calendar_rejected(self):
  spec=self.m['calendars']['train'];sessions=json.loads((self.base/'data'/spec['path']).read_text());next(iter(sessions.values()))['close']='2026-01-06T18:00:00Z';self.rewrite(spec,sessions)
  self.assertEqual(self.execute()['reason'],'short_or_invalid_regular_session')
 def test_unverified_calendar_rejected(self):
  spec=self.m['calendars']['train'];sessions=json.loads((self.base/'data'/spec['path']).read_text());next(iter(sessions.values()))['calendar_verified']=False;self.rewrite(spec,sessions)
  self.assertEqual(self.execute()['reason'],'verified_calendar_required')
 def test_changing_registered_plan_is_blocked(self):
  p=register(self.j,'test',self.plan,self.m,self.c);p['risk']['budget']=600
  self.assertEqual(run(self.j,'test',p,self.m,self.c,self.base/'data',self.base/'test')['reason'],'plan_not_registered')
 def test_risk_relaxation_blocked(self):
  self.plan['risk']['trade_risk']=.01;self.assertEqual(self.execute()['reason'],'fixed_risk_and_cost_scenarios_required')
 def test_unlocked_holdout_rejected(self):
  self.m['final_holdout']['access']='open';self.assertEqual(self.execute()['reason'],'final_holdout_not_locked')
 def test_external_evidence_path_rejected(self):
  self.m['administrative']['path']='../outside.json';self.assertEqual(self.execute()['reason'],'evidence_path_outside_dataset')
 def test_out_of_order_market_events_rejected(self):
  rows=self.market('train');rows[0],rows[1]=rows[1],rows[0];self.rewrite(self.m['files']['train'],rows,True)
  self.assertEqual(self.execute()['reason'],'out_of_order_events')
 def test_duplicate_quote_timestamp_rejected(self):
  rows=self.market('train');rows[-1]['quote_at']=rows[-2]['quote_at'];rows[-1]['available_at']=rows[-2]['available_at'];self.rewrite(self.m['files']['train'],rows,True)
  self.assertEqual(self.execute()['reason'],'ambiguous_or_regressing_quote')

 def test_consumed_validation_cannot_be_relabelled_training(self):
  prior=copy.deepcopy(self.m);prior['files']['validation']=copy.deepcopy(self.m['files']['train'])
  self.j.consume_validation('earlier-experiment',prior,self.c)
  (self.base/'data/train.jsonl').unlink()
  self.assertEqual(self.execute()['reason'],'training_reuses_consumed_validation')
 def test_fold_cannot_omit_previous_close_warmup(self):
  self.plan['validation_windows'][0]['start']='2026-01-08T00:00:00Z'
  r=self.execute();self.assertEqual(r['trials'][1]['status'],'failed')
  self.assertEqual(r['trials'][1]['reason'],'whole_session_and_prior_close_required')
  self.assertFalse(r['all_validation_windows_positive'])
