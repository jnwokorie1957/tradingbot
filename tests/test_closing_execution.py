import copy,json,unittest
from datetime import timedelta
from trading_pipeline.closing_execution import ClosingEngine
from trading_pipeline.closing_fixtures import create,quote
from trading_pipeline.closing_run import run_once
from trading_pipeline.engine_v4 import Ledger,Policy,utc,Engine,Hypothesis

class ClosingExecutionTests(unittest.TestCase):
 def setUp(self):self.l=Ledger(':memory:');self.bundle=create()
 def tearDown(self):self.l.close()
 def engine(self,b=None,**kwargs):
  b=b or self.bundle
  return ClosingEngine(self.l,'test',b['contracts'],b['sessions'],synthetic=True,**kwargs)
 def prepared(self,b=None):
  b=b or self.bundle;e=self.engine(b)
  for event in b['events'][:23]:out=e.apply(event)
  return e,out
 def test_winter_and_summer_entry_and_session_close(self):
  for summer in [False,True]:
   b=create(summer);l=Ledger(':memory:')
   try:r=run_once(l,'fixture',b)
   finally:l.close()
   self.assertEqual(r['status'],'completed_synthetic_verification')
   self.assertEqual(r['observations'][23]['result']['status'],'entry')
   self.assertEqual(r['observations'][-1]['result']['reason'],'session_close')
   self.assertEqual(r['engine']['state']['trades'],1)
   self.assertEqual(utc(b['events'][22]['available_at']).hour,19 if summer else 20)
   self.assertFalse(r['profit_claim'])
 def test_next_quote_minimum_one_second_and_stop_from_fill(self):
  e,r=self.prepared();at=utc(self.bundle['events'][22]['available_at']);self.assertEqual(r['status'],'signal')
  for offset in [0,.5]:self.assertEqual(e.apply(quote(at+timedelta(seconds=offset),str(offset)))['status'],'no_executable_signal')
  r=e.apply(quote(at+timedelta(seconds=1),'entry'));p=e.state['positions']['TEST']
  self.assertEqual(r['status'],'entry');self.assertEqual(p['entry']-p['stop'],1);self.assertIsNone(p['target'])
  self.assertAlmostEqual(r['risk'],1.45)
 def test_large_favorable_move_has_no_target(self):
  e,_=self.prepared();e.apply(self.bundle['events'][23]);at=utc(self.bundle['events'][23]['available_at'])+timedelta(seconds=1)
  self.assertEqual(e.apply(quote(at,'favorable',110,110.25))['status'],'mark');self.assertTrue(e.state['positions'])
 def test_stop_gap_uses_actual_quote_and_costs(self):
  e,_=self.prepared();e.apply(self.bundle['events'][23]);at=utc(self.bundle['events'][23]['available_at'])+timedelta(seconds=1)
  r=e.apply(quote(at,'gap',99,99.25));self.assertEqual(r['reason'],'stop');self.assertEqual(r['fill'],98.75);self.assertAlmostEqual(r['net_pnl'],-2.95)
 def test_close_decision_rejects_pretrigger_quote(self):
  e,_=self.prepared();e.apply(self.bundle['events'][23]);clock=self.bundle['events'][24];e.apply(clock);at=utc(clock['available_at'])
  r=e.apply(quote(at,'oldquote',quote_at=at-timedelta(seconds=1)));self.assertEqual(r['status'],'exit_pending')
  self.assertEqual(e.apply(quote(at+timedelta(seconds=1),'later'))['reason'],'session_close')
 def test_missing_close_quote_retains_position(self):
  self.bundle['events']=self.bundle['events'][:-1];r=run_once(self.l,'missingquote',self.bundle)
  self.assertEqual(r['status'],'inconclusive');self.assertEqual(r['engine']['unresolved_positions'],1)
 def test_missing_previous_close(self):
  self.bundle['events'].pop(0);e=self.engine()
  for event in self.bundle['events'][:22]:r=e.apply(event)
  self.assertEqual(r['reason'],'missing_previous_regular_close');self.assertFalse(e.state['pending'])
 def test_insufficient_warmup(self):
  self.bundle['events'].pop(1);e=self.engine()
  for event in self.bundle['events'][:22]:r=e.apply(event)
  self.assertEqual(r['reason'],'insufficient_completed_warmup')
 def test_gap_in_warmup(self):
  for b in self.bundle['events'][1:6]:
   for k in ['start','end','available_at']:b[k]=(utc(b[k])-timedelta(seconds=1)).isoformat()
  e,r=self.prepared();self.assertEqual(r['reason'],'warmup_gap')
 def test_one_decision_per_session_and_no_reentry(self):
  e,_=self.prepared();again=dict(self.bundle['events'][22],id='seconddecision')
  self.assertEqual(e.apply(again)['reason'],'session_already_decided')
  e.apply(self.bundle['events'][23]);at=utc(self.bundle['events'][23]['available_at'])+timedelta(seconds=1)
  e.apply(quote(at,'stop',99,99.25));self.assertEqual(e.apply(quote(at+timedelta(seconds=1),'retry'))['status'],'no_executable_signal')
 def test_stale_quote_skipped_then_fresh_within_ttl(self):
  e,_=self.prepared();at=utc(self.bundle['events'][22]['available_at'])
  self.assertEqual(e.apply(quote(at+timedelta(seconds=10),'stale',quote_at=at+timedelta(seconds=1)))['status'],'skip')
  self.assertEqual(e.apply(quote(at+timedelta(seconds=11),'fresh'))['status'],'entry')
 def test_expired_signal_cannot_enter(self):
  e,_=self.prepared();at=utc(self.bundle['events'][22]['available_at'])+timedelta(seconds=61)
  self.assertEqual(e.apply(quote(at,'late'))['reason'],'signal_expired');self.assertFalse(e.state['positions'])
 def test_whole_contract_risk_rejection_no_retry(self):
  self.bundle['contracts']['TEST']['multiplier']=20;e,_=self.prepared()
  r=e.apply(self.bundle['events'][23]);self.assertEqual(r['reason'],'one_contract_trade_risk');self.assertEqual(e.state['cash'],500)
  at=utc(self.bundle['events'][23]['available_at'])+timedelta(seconds=1)
  self.assertEqual(e.apply(quote(at,'retry'))['status'],'no_executable_signal')
 def test_margin_rejection(self):
  self.bundle['contracts']['TEST']['initial_margin']=600;e,_=self.prepared()
  self.assertEqual(e.apply(self.bundle['events'][23])['reason'],'margin_and_loss_reserve')
 def test_invalid_costs_cannot_complete(self):
  self.bundle['contracts']['TEST']['valid_until']=self.bundle['sessions']['session']['close']
  r=run_once(self.l,'costs',self.bundle);self.assertEqual(r['status'],'inconclusive');self.assertFalse(r['engine']['cost_evidence_valid'])
 def test_strategy_identity_resume_and_changed_calendar_rejection(self):
  e,_=self.prepared();e.apply(self.bundle['events'][23]);r=self.engine();self.assertEqual(r.state,e.state)
  with self.assertRaises(ValueError):Engine(self.l,'test',self.bundle['contracts'],hypothesis=Hypothesis(lookback=2),synthetic=True)
  b=copy.deepcopy(self.bundle);b['sessions']['session']['source_reference']='different evidence'
  with self.assertRaises(ValueError):self.engine(b)
 def test_real_data_runner_blocked_and_failed_trial_retained(self):
  self.bundle['synthetic']=False;r=run_once(self.l,'real',self.bundle)
  self.assertEqual(r['status'],'failed');self.assertEqual(r['reason'],'real_data_admission_not_integrated')
  self.assertEqual(json.loads(self.l.db.execute('SELECT result FROM trials').fetchone()[0])['status'],'failed')
 def test_short_session_and_future_calendar_rejected(self):
  for field,value in [('close','2026-01-06T18:00:00Z'),('available_at','2026-01-06T20:00:00Z')]:
   b=copy.deepcopy(self.bundle);b['sessions']['session'][field]=value
   with self.assertRaises(ValueError):self.engine(b)
 def test_policy_cannot_relax_portfolio_cap(self):
  with self.assertRaises(ValueError):self.engine(policy=Policy(portfolio_risk=.02))
 def test_duplicate_one_shot_run_does_not_mutate(self):
  run_once(self.l,'oneshot',self.bundle);n=self.l.db.execute('SELECT count(*) FROM events').fetchone()[0]
  with self.assertRaises(ValueError):run_once(self.l,'oneshot',self.bundle)
  self.assertEqual(self.l.db.execute('SELECT count(*) FROM events').fetchone()[0],n)

 def test_short_direction_and_ask_side_stop(self):
  prior=self.bundle['events'][0]
  prior.update(open=102,high=102.5,low=101.5,close=102)
  e,r=self.prepared();self.assertEqual(r['side'],-1)
  entry=e.apply(self.bundle['events'][23]);p=e.state['positions']['TEST']
  self.assertEqual(p['stop']-p['entry'],1)
  at=utc(self.bundle['events'][23]['available_at'])+timedelta(seconds=1)
  out=e.apply(quote(at,'shortstop',102,102.25));self.assertEqual(out['reason'],'stop');self.assertEqual(out['fill'],102.5)
 def test_late_decision_and_zero_return_skip(self):
  e=self.engine()
  for event in self.bundle['events'][:22]:e.apply(event)
  d=dict(self.bundle['events'][22]);d['available_at']=(utc(d['available_at'])+timedelta(seconds=1)).isoformat()
  self.assertEqual(e.apply(d)['reason'],'outside_decision_time');self.assertFalse(e.state['pending'])
 def test_zero_return_skip(self):
  prior=self.bundle['events'][0];prior.update(open=101,high=101.5,low=100.5,close=101)
  e,r=self.prepared();self.assertEqual(r['reason'],'zero_return_skip');self.assertFalse(e.state['pending'])
 def test_future_bar_rejected_atomically(self):
  e=self.engine();b=dict(self.bundle['events'][0]);b['available_at']=b['start']
  with self.assertRaises(ValueError):e.apply(b)
  self.assertFalse(e.state.get('closing_bars',{}))
