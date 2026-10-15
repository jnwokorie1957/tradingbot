import unittest
from datetime import datetime,timedelta,timezone
from trading_pipeline.metrics import summarize,assess

class MetricsTests(unittest.TestCase):
 def trades(self):
  start=datetime(2020,1,1,tzinfo=timezone.utc)
  return [dict(net_pnl=2 if i%10<7 else -1,exit_at=(start+timedelta(days=i//5)).isoformat()) for i in range(300)]
 def test_daily_block_bootstrap_is_deterministic(self):
  a=summarize(self.trades(),[500,499,501]);b=summarize(self.trades(),[500,499,501])
  self.assertEqual(a,b);self.assertGreater(a['expectancy_day_block_bootstrap_95'][0],0)
  self.assertAlmostEqual(a['win_rate'],.7);self.assertEqual(a['trade_days'],60)
 def test_threshold_pass_never_activates_paper(self):
  m=summarize(self.trades(),[500,499,501]);result=assess(m,synthetic=False,clean=True)
  self.assertTrue(result['statistical_screen_pass']);self.assertFalse(result['qualified_for_paper']);self.assertFalse(result['broker_execution_enabled'])
  self.assertIn('independent_review_required',result['reasons'])
 def test_marked_drawdown_and_unclean_paths_reject(self):
  m=summarize(self.trades(),[500,550,490]);r=assess(m,synthetic=False,clean=False)
  self.assertGreater(m['maximum_drawdown_fraction'],.1);self.assertIn('drawdown_limit_reached',r['reasons']);self.assertIn('incomplete_or_invalid_trial',r['reasons'])

if __name__=='__main__':unittest.main()
