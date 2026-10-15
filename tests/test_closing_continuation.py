import unittest
from datetime import datetime,timedelta
from trading_pipeline.closing_continuation import decide

def fixture(summer=False):
 date,previous,offset=('2026-07-14','2026-07-13',4) if summer else ('2026-01-06','2026-01-05',5)
 close=datetime.fromisoformat(date+f'T{16+offset}:00:00+00:00');decision=close-timedelta(minutes=30)
 session=dict(contract='TEST',calendar_verified=True,source_reference='SYNTHETIC TEST CALENDAR',open=date+f'T{9+offset}:30:00Z',close=close.isoformat(),previous_close=previous+f'T{16+offset}:00:00Z')
 def bar(end,price):return dict(contract='TEST',start=(end-timedelta(minutes=5)).isoformat(),end=end.isoformat(),available_at=end.isoformat(),open=price,high=price+.25,low=price-.25,close=price,volume=10)
 rows=[bar(datetime.fromisoformat(session['previous_close'].replace('Z','+00:00')),100)]
 rows += [bar(decision-timedelta(minutes=5*(20-i)),101) for i in range(21)]
 return rows,session,decision.isoformat()

class ContinuationTests(unittest.TestCase):
 def test_winter_and_summer_iana_timezones(self):
  for summer in [False,True]:
   rows,s,at=fixture(summer);r=decide(rows,s,.25,at)
   self.assertEqual(r['status'],'unqualified_signal_only');self.assertEqual(r['side'],1);self.assertEqual(r['stop_distance'],.5);self.assertIsNone(r['target']);self.assertFalse(r['execution_eligible'])
 def test_future_bar_cannot_change_decision(self):
  rows,s,at=fixture();expected=decide(rows,s,.25,at)
  rows.append({'end':s['close'],'available_at':s['close']})
  self.assertEqual(decide(rows,s,.25,at),expected)
 def test_late_signal_bar_is_not_available(self):
  rows,s,at=fixture();rows[-1]['available_at']=s['close']
  self.assertEqual(decide(rows,s,.25,at)['status'],'insufficient_completed_warmup')
 def test_missing_prior_session_close(self):
  rows,s,at=fixture();self.assertEqual(decide(rows[1:],s,.25,at)['status'],'missing_previous_regular_close')
 def test_gap_and_short_session_fail_closed(self):
  rows,s,at=fixture();rows[2]['start']=rows[1]['start'];rows[2]['end']=rows[1]['end']
  with self.assertRaises(ValueError):decide(rows,s,.25,at)
  rows,s,at=fixture();s['close']=s['close'].replace('21:00','18:00')
  with self.assertRaises(ValueError):decide(rows,s,.25,at)
 def test_cross_contract_not_silently_transferred(self):
  rows,s,at=fixture();rows[0]['contract']='OTHER'
  with self.assertRaises(ValueError):decide(rows,s,.25,at)

if __name__=='__main__':unittest.main()
