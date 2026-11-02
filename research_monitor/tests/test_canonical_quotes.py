import unittest,numpy as np
from research_monitor.canonical_quotes import minute_bars,fifteen_bars

class CanonicalQuoteChecks(unittest.TestCase):
 def test_forming_minute_cannot_enter_signal_bar(self):
  q=np.array([(0,100.,101.),(30000,102.,103.),(60000,999.,1000.)],dtype=[('time_msc','i8'),('bid','f8'),('ask','f8')])
  one=minute_bars(q,60);self.assertEqual(len(one),1);self.assertEqual(one[0]['close'],102.);self.assertEqual(one[0]['high'],102.)
 def test_missing_minute_invalidates_quarter_without_fill(self):
  one=[dict(t=i*60,open=100.,high=101.,low=99.,close=100.,volume=1,spread=1.) for i in range(15)]
  self.assertEqual(len(fifteen_bars(one)),1);self.assertEqual(fifteen_bars(one[:7]+one[8:]),[])
