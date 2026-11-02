import unittest,tempfile
from datetime import datetime,timezone
from unittest.mock import patch
from research_monitor.exits import next_stop,target_rr
from research_monitor.local_run import run_case
from research_monitor.telemetry import Reporter

class ExitChecks(unittest.TestCase):
 def test_fixed_target_protection_preserves_1_5R_and_waits_for_close(self):
  for policy in ['protect_half','protect_close','protect_recovery']:self.assertEqual(target_rr(policy,1.5,{}),1.5)
  p=dict(side=1,entry=100.,distance=2.,stop=98.,recovery=True)
  self.assertEqual(next_stop('protect_close',p,103.,99.,.1,101.),98.)
  self.assertEqual(next_stop('protect_close',p,103.,99.,.1,102.),100.)
  self.assertEqual(next_stop('protect_half',p,103.,99.,.1,101.),99.)
  p['recovery']=False;self.assertEqual(next_stop('protect_recovery',p,103.,99.,.1,101.),98.)
 def test_extension_requires_preentry_conditions(self):
  self.assertEqual(target_rr('conditional_2',1,dict(trend_aligned=True,strong_close=False)),1)
  self.assertEqual(target_rr('conditional_2',1,dict(trend_aligned=True,strong_close=True)),2)
 def test_trails_never_loosen_in_either_direction(self):
  for side in [1,-1]:
   p=dict(side=side,entry=100.,distance=2.,stop=100-side*2.)
   s=next_stop('trail_3',p,104,96,.1);p['stop']=s
   after=next_stop('trail_3',p,101,99,.1)
   self.assertEqual(s,after);self.assertGreaterEqual(side*(s-(100-side*2)),0)
 def test_trail_is_effective_only_after_trigger_bar(self):
  at=int(datetime(2026,10,1,14,tzinfo=timezone.utc).timestamp())
  bars=[dict(t=at-60+i*60,open=100.,high=100.,low=100.,close=100.,spread=0.,volume=1) for i in range(6)]
  bars[2].update(high=101.8,low=99.5,close=101.5)
  bars[3].update(open=100.5,high=100.6,low=100.4,close=100.5)
  sig={at:dict(side=1,stop=99.,reference=100.,decision=at,entry_at=at+60)}
  meta=dict(trade_tick_size=.01,trade_tick_value_loss=.01,volume_min=1,volume_step=1,point=.01)
  with tempfile.TemporaryDirectory() as d,patch('research_monitor.local_run.signals',return_value=sig):
   r=Reporter(d);result=run_case({('NAS100',1):bars,('NAS100',5):[]},'NAS100',5,meta,dict(lookback=20,rr=1,filter='none',exit_policy='trail_3'),'Development',['2026-10-01'],r,0,1,1)
  exits=[e for e in r.state['events'] if e['kind']=='exit'];revisions=[e for e in r.state['events'] if e['kind']=='stop_revision']
  self.assertEqual(len(exits),1);self.assertEqual(len(revisions),1)
  self.assertEqual(exits[0]['reason'],'stop_gap');self.assertEqual(exits[0]['price'],100.49)

if __name__=='__main__':unittest.main()
