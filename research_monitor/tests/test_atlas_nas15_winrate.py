import unittest
from datetime import datetime, timezone
from research_monitor.atlas_nas15_winrate_study import PROFILES, choose, gap_pass, wilson


class NAS15ResearchGuardChecks(unittest.TestCase):
    def rows(self):
        return [dict(profile=n,cost=c,nas15=dict(trades=40,net_pnl=100.,win_rate=50.),
                     portfolio=dict(net_pnl=300.),portfolio_quote_drawdown_pct=4.)
                for n in PROFILES for c in ['standard','higher']]

    def test_high_rate_with_fewer_fills_cannot_displace_capture_qualified_candidate(self):
        rows=self.rows()
        for r in rows:
            if r['profile']=='strong_close':r['nas15'].update(trades=30,win_rate=65.)
            elif r['profile']=='efficient_all':r['nas15'].update(trades=15,win_rate=90.)
        result=choose(rows)
        self.assertEqual(result['selected'],'strong_close')
        self.assertTrue(result['development_qualified'])
        self.assertNotIn('efficient_all',result['eligible'])

    def test_profit_and_drawdown_failures_remain_explicit_despite_high_win_rate(self):
        rows=self.rows()
        for r in rows:
            if r['profile']=='strong_close':
                r['nas15'].update(net_pnl=70.,win_rate=90.)
                r['portfolio_quote_drawdown_pct']=5.
        result=choose(rows)
        self.assertNotIn('strong_close',result['eligible'])
        self.assertTrue(any('profit retention' in s for s in result['vetoes']['strong_close']))
        self.assertTrue(any('drawdown worsens' in s for s in result['vetoes']['strong_close']))

    def test_missing_context_and_unfinished_opening_minute_cannot_pass_gap_gate(self):
        # January: 14:30UTC is09:30NewYork. Opening minute is not complete.
        t=datetime(2026,1,5,14,30,tzinfo=timezone.utc).timestamp()
        s=dict(atr14=2.,features=dict(session_open=101.,prior_close=100.))
        self.assertFalse(gap_pass(t,s))
        self.assertTrue(gap_pass(t+60,s))
        self.assertFalse(gap_pass(t+60,dict(atr14=2.,features={})))

    def test_tiny_observed_high_rate_has_wide_confidence_interval(self):
        low,high=wilson(4,5)
        self.assertLess(low,60.)
        self.assertGreater(high,90.)


if __name__=='__main__':unittest.main()
