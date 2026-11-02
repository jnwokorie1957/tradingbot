import unittest
from research_monitor.entry_quality_v2 import confirm_retests,reject

class StructuralEntryChecks(unittest.TestCase):
 def test_retest_cannot_use_signal_minute_or_future_observation(self):
  impulse={60:dict(side=1,decision=60,stop=98,reference=101,features=dict(breakout_level=100))}
  bars=[dict(t=0,low=99,high=102,close=101),dict(t=60,low=99.9,high=101,close=100.5)]
  self.assertEqual(confirm_retests(bars[:1],impulse),{})
  plans=confirm_retests(bars,impulse);self.assertEqual(set(plans),{120});self.assertEqual(plans[120]['entry_at'],180)
 def test_stop_breach_and_expiry_cancel_retest(self):
  impulse={60:dict(side=1,decision=60,stop=98,reference=101,features=dict(breakout_level=100))}
  self.assertFalse(confirm_retests([dict(t=0,low=99,high=102,close=101),dict(t=60,low=97,high=102,close=101)],impulse))
  self.assertFalse(confirm_retests([dict(t=0,low=99,high=102,close=101),dict(t=960,low=99,high=102,close=101)],impulse))
 def test_prior_boundary_needs_both_signal_and_entry_confirmation(self):
  s=dict(side=1,reference=101,features=dict(prior_high=100))
  self.assertIsNone(reject('beyond_prior_session',s,100.5,1,1.5))
  self.assertEqual(reject('beyond_prior_session',s,99.5,1,1.5),'still_inside_prior_session')
