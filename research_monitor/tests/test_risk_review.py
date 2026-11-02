import unittest
import tempfile
from datetime import datetime,timezone
from unittest.mock import patch
from research_monitor.risk_review import RiskReview
from research_monitor.local_run import run_case
from research_monitor.telemetry import Reporter

class RiskChecks(unittest.TestCase):
 def test_ten_dollar_recovery_requires_two_wins_to_restore(self):
  r=RiskReview('recovery_slow10');r.exited(-1,0);r.exited(-1,1);self.assertEqual(r.cap(498),10)
  r.exited(1,2);self.assertEqual(r.cap(499),10);r.session_start('next');r.exited(0,3);self.assertEqual(r.cap(499),10)
  r.exited(1,4);self.assertEqual(r.cap(500),25)
 def test_trend_confirmation_only_filters_during_recovery(self):
  r=RiskReview('recovery_trend');self.assertIsNone(r.entry_reason({'trend_aligned':False},0,0,1))
  r.exited(-1,0);r.exited(-1,1);self.assertEqual(r.cap(498),10)
  self.assertEqual(r.entry_reason({'trend_aligned':False},0,0,1),'recovery_trend_not_aligned')
  self.assertIsNone(r.entry_reason({'trend_aligned':True},0,0,1));r.exited(1,2);self.assertEqual(r.cap(499),25)
 def test_staircase_and_slow_restore(self):
  r=RiskReview('streak_staircase');r.exited(-1,0);r.exited(-1,1);self.assertEqual(r.cap(498),15)
  r.exited(-1,2);self.assertEqual(r.cap(497),10);r.exited(1,3);self.assertEqual(r.cap(498),25)
  r=RiskReview('streak_slow_restore');r.exited(-1,0);r.exited(-1,1);r.exited(1,2);self.assertEqual(r.cap(499),15)
  r.exited(1,3);self.assertEqual(r.cap(500),25)
 def test_recovery_gates_use_only_prior_losses(self):
  r=RiskReview('streak_strength');self.assertIsNone(r.entry_reason({},0,0,1))
  r.exited(-1,0);r.exited(-1,1);self.assertEqual(r.entry_reason({},0,0,1),'recovery_weak_close')
  r=RiskReview('streak_pause90');r.exited(-1,0);r.exited(-1,1);self.assertEqual(r.reason(2),'streak_pause90');self.assertIsNone(r.reason(5401))
 def test_loss_sizing_persists_until_profitable_exit(self):
  r=RiskReview('loss_step20');self.assertEqual(r.cap(500),25);r.exited(-1,0);self.assertEqual(r.cap(499),20)
  r.session_start('next');self.assertEqual(r.cap(499),20);r.exited(2,100);self.assertEqual(r.cap(501),25)
 def test_streak_reduction_is_for_future_fills_until_profit(self):
  r=RiskReview('streak_step15');r.exited(-1,0);self.assertEqual(r.cap(499),25)
  r.exited(-1,60);self.assertEqual(r.cap(498),15);r.session_start('next');r.exited(0,120);self.assertEqual(r.cap(498),15)
  r.exited(1,180);self.assertEqual(r.cap(499),25)
 def test_drawdown_hysteresis_and_new_high(self):
  r=RiskReview('drawdown_step20');r.observe_equity(440);self.assertEqual(r.cap(440),20)
  r.observe_equity(460);self.assertEqual(r.cap(460),20);r.observe_equity(480);self.assertEqual(r.cap(480),25)
  r.observe_equity(600);r.observe_equity(530);self.assertEqual(r.cap(530),20)
 def test_two_daily_losses_reset_next_session(self):
  r=RiskReview('two_daily_losses');r.session_start('a');r.exited(-1,0);r.exited(2,60);r.exited(-1,120)
  self.assertEqual(r.reason(10000),'two_daily_losses');r.session_start('b');self.assertIsNone(r.reason(10000))
 def test_fractional_risk_cannot_exceed_cap_or_risk_negative_cash(self):
  r=RiskReview('equity2pct');self.assertEqual(r.cap(500),10);self.assertEqual(r.cap(2000),25);self.assertEqual(r.cap(-1),0)
 def test_session_halt_latches_and_resets_next_day(self):
  r=RiskReview('stop_after_loss');r.session_start('a');r.exited(-1,100);r.exited(2,200)
  self.assertEqual(r.reason(10000),'loss_session_halt');r.session_start('b');self.assertIsNone(r.reason(10000))
 def test_cooldown_does_not_reset_on_calendar_change(self):
  r=RiskReview('cooldown_loss30');r.session_start('a');r.exited(-1,100);r.session_start('b')
  self.assertEqual(r.reason(101),'loss_cooldown');self.assertIsNone(r.reason(1900))
 def test_one_entry_counts_fills_not_skipped_candidates(self):
  r=RiskReview('one_entry');r.session_start('a');self.assertIsNone(r.reason(0));r.entered();self.assertEqual(r.reason(0),'one_entry_session_limit')
 def test_runner_enforces_one_fill_while_comparator_takes_both(self):
  at=int(datetime(2026,10,1,14,tzinfo=timezone.utc).timestamp())
  bars=[dict(t=at-60+i*60,open=100.,high=100.,low=100.,close=100.,spread=0.,volume=1) for i in range(12)]
  bars[2]['high']=103.;bars[6]['high']=103.
  sig={t:dict(side=1,stop=99.,reference=100.,decision=t,entry_at=t+60) for t in [at,at+240]}
  meta=dict(trade_tick_size=.01,trade_tick_value_loss=.01,volume_min=1,volume_step=1,point=.01)
  results=[]
  with tempfile.TemporaryDirectory() as folder,patch('research_monitor.local_run.signals',return_value=sig):
   for name in ['baseline','one_entry']:
    results.append(run_case({('SPX500',1):bars,('SPX500',15):[]},'SPX500',15,meta,dict(lookback=20,rr=1.5,filter='none',risk_policy=name),'Development',['2026-10-01'],Reporter(folder),0,1,2))
  self.assertEqual(results[0]['outcomes'],2);self.assertEqual(results[1]['outcomes'],1)
  self.assertEqual(results[1]['skips']['one_entry_session_limit'],1)
