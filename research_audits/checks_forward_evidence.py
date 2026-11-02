import unittest
from datetime import datetime,timezone
from .forward_evidence import complete_hours,clock_windows,reconcile


class EvidenceChecks(unittest.TestCase):
    def test_complete_hour_requires_all_sixty_unique_minutes(self):
        self.assertEqual(complete_hours(list(range(0,3600,60))),[3600]);self.assertFalse(complete_hours(list(range(60,3600,60))));self.assertFalse(complete_hours([0]+list(range(0,3600,60))))

    def test_intraday_window_never_counts_as_completed(self):
        opening=int(datetime(2026,11,2,14,30,tzinfo=timezone.utc).timestamp());minutes=list(range(opening,opening+390*60,60))
        self.assertFalse(clock_windows(minutes,opening+3600)[0]['eligible_completed_clock_window']);self.assertTrue(clock_windows(minutes,opening+405*60)[0]['eligible_completed_clock_window'])

    def test_cash_and_commission_are_independently_reconciled(self):
        meta={'SPX500':dict(trade_tick_size=.1,trade_tick_value_loss=10.,volume_min=.01,volume_step=.01)};fill=dict(id='one',symbol='SPX500',strategy='SPX15',quantity=.01,entry=100.,exit=101.5,side=1,pnl=1.44,planned_risk=1.16,stop=99.,target=101.5)
        book=dict(fills=[fill],cash=5001.44,positions={},dd=.01);self.assertEqual(reconcile(book,5000.,meta,6.)['closed_spx_net'],1.44)
        with self.assertRaises(AssertionError):reconcile(book,5000.,meta,12.)
        book['cash']+=1
        with self.assertRaises(AssertionError):reconcile(book,5000.,meta,6.)


if __name__=='__main__':unittest.main()
