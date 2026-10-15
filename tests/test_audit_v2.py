import copy,unittest
from trading_pipeline.engine_v4 import Engine,Ledger,Hypothesis
from trading_pipeline.runner import fold_rows,register,run
from trading_pipeline.journal import Journal
from trading_pipeline.metrics import summarize
from test_simulator import contract,bar,quote
import test_pipeline

class AuditEngineTests(unittest.TestCase):
 def setUp(self):self.l=Ledger(':memory:')
 def tearDown(self):self.l.close()
 def engine(self,**kw):return Engine(self.l,'test',{'TEST':contract(**kw)},hypothesis=Hypothesis(lookback=2),synthetic=True)
 def signal(self,e):
  for b in [bar(0,100),bar(1,100),bar(2,101,100.5,101)]:e.apply(b)
 def enter(self,e):self.signal(e);self.assertEqual(e.apply(quote())['status'],'entry')
 def test_profit_equity_fixed_ceiling_includes_fees(self):
  e=self.engine(fee_per_side=.7);e.state.update(cash=600,equity=600,peak=600,day_start=600)
  self.signal(e);r=e.apply(quote());self.assertEqual(r['reason'],'one_contract_trade_risk');self.assertAlmostEqual(r['risk'],2.65)
 def test_losing_equity_reduces_ceiling_includes_fees(self):
  e=self.engine(fee_per_side=.4);e.state.update(cash=400,equity=400,peak=400,day_start=400)
  self.signal(e);r=e.apply(quote());self.assertEqual(r['reason'],'one_contract_trade_risk');self.assertAlmostEqual(r['risk'],2.05)
 def test_timeout_requires_post_decision_quote_and_survives_resume(self):
  e=self.engine();self.enter(e)
  r=e.apply(quote(at='2026-01-01T01:03:01Z',quote_at='2026-01-01T01:02:59Z'))
  self.assertEqual(r['status'],'exit_pending');self.assertTrue(e.state['positions'])
  e=self.engine();r=e.apply(quote(at='2026-01-01T01:03:02Z'))
  self.assertEqual(r['reason'],'time_exit');self.assertEqual(r['status'],'exit')
 def test_expiry_requires_post_decision_quote(self):
  e=self.engine(exit_before='2026-01-01T00:04:00Z');self.enter(e)
  r=e.apply(quote(at='2026-01-01T00:04:00Z',quote_at='2026-01-01T00:03:59Z'))
  self.assertEqual(r['status'],'exit_pending')
  self.assertEqual(e.apply(quote(at='2026-01-01T00:04:01Z'))['reason'],'expiry_or_roll_cutoff')
 def margin(self,at='2026-01-01T00:04:00Z',effective='2026-01-01T00:04:00Z'):
  return dict(id='margin',kind='margin_update',contract='TEST',available_at=at,effective_at=effective,valid_until='2026-01-31T00:00:00Z',initial_margin=600,maintenance_margin=600,verified=True,source='synthetic',currency='USD')
 def test_margin_requires_post_announcement_quote(self):
  e=self.engine();self.enter(e);e.apply(self.margin())
  self.assertEqual(e.apply(quote(at='2026-01-01T00:04:00Z',quote_at='2026-01-01T00:03:59Z'))['status'],'exit_pending')
  self.assertEqual(e.apply(quote(at='2026-01-01T00:04:01Z'))['reason'],'maintenance_margin_breach')
 def test_resting_stop_can_fill_older_quote(self):
  e=self.engine();self.enter(e)
  self.assertEqual(e.apply(quote(bid=100,ask=100.25,at='2026-01-01T00:04:00Z',quote_at='2026-01-01T00:03:59Z'))['reason'],'stop')
 def test_expired_costs_invalid_even_target_exit(self):
  e=self.engine(valid_until='2026-01-01T00:04:00Z');self.enter(e)
  r=e.apply(quote(bid=105,ask=105.25,at='2026-01-01T00:04:01Z'))
  self.assertEqual(r['status'],'exit');self.assertFalse(r['cost_evidence_valid']);self.assertEqual(e.state['invalid_cost_fills'],1)
 def test_fold_replays_known_margin_not_signals_or_future_announcement(self):
  w=dict(start='2026-01-01T00:01:00Z',end='2026-01-01T00:05:00Z')
  known=self.margin(at='2026-01-01T00:00:00Z',effective='2026-01-01T00:00:00Z')
  future=self.margin(at='2026-01-01T00:06:00Z')|{'id':'future'}
  rows=fold_rows([known,future],w);self.assertEqual(rows,[known])
  e=self.engine();e.apply(rows[0]);self.signal(e)
  self.assertEqual(e.apply(quote())['reason'],'margin_and_loss_reserve')
 def test_known_future_effective_margin_does_not_leak(self):
  e=self.engine();e.apply(self.margin(at='2026-01-01T00:00:00Z',effective='2026-01-01T01:00:00Z'));self.enter(e)
 def test_compact_and_extended_utc_same_day(self):
  times=['20260101T01:00:00Z','2026-01-01T11:00:00+00:00','20260101T21:00:00Z']
  r=summarize([dict(exit_at=t,net_pnl=1) for t in times],[500,503]);self.assertEqual(r['trade_days'],1);self.assertIsNone(r['expectancy_day_block_bootstrap_95'])

class AuditRegistryTests(unittest.TestCase):
 def test_hash_and_overlap_registry_durable(self):
  j=Journal(':memory:');c={'T':{'contract_id':123}}
  m={'files':{'validation':dict(sha256='a',start='2026-01-01T00:00:00Z',end='2026-01-03T00:00:00Z')}}
  j.consume_validation('A',m,c)
  for h in ['a','different-encoding']:
   n=copy.deepcopy(m);n['files']['validation']['sha256']=h
   with self.assertRaisesRegex(ValueError,'validation_consumed'):j.consume_validation('B'+h,n,c)
  j.close()

class AuditFlowTests(unittest.TestCase):
 setUp=test_pipeline.PipelineTests.setUp
 tearDown=test_pipeline.PipelineTests.tearDown
 execute=test_pipeline.PipelineTests.execute
 def test_new_experiment_cannot_reuse_validation(self):
  self.execute();p=register(self.j,'new',self.plan,self.m,self.c)
  r=run(self.j,'new',p,self.m,self.c,self.base/'data',self.base/'new-results')
  self.assertEqual(r['reason'],'validation_consumed_or_overlapping')
  self.assertFalse(any(t['phase']=='validation' for t in r['trials']))

 def test_cost_expired_exit_makes_trial_inconclusive(self):
  self.c['TEST']['valid_until']='2026-01-01T00:03:02Z'
  r=self.execute()
  self.assertEqual(r['status'],'rejected_training_no_eligible_candidate')
  self.assertEqual(r['trials'][0]['status'],'inconclusive')
  self.assertEqual(r['trials'][0]['invalid_cost_fills'],1)
  self.assertFalse(r['trials'][0]['assessment']['statistical_screen_pass'])
