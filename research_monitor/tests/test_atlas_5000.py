import unittest
from datetime import datetime,timezone
from research_monitor.atlas_portfolio_controller import APPROVED,allocate
from research_monitor.atlas_live_core import PaperBook


class ApprovedFiveThousandChecks(unittest.TestCase):
    def setUp(self):self.meta=dict(trade_tick_size=.1,trade_tick_value_loss=10.,trade_contract_size=100.,assumed_margin_rate=.005,volume_min=.01,volume_step=.01,volume_max=1000.)
    def test_fifty_combined_is_enforced_instead_of_old_twentyfive(self):
        p={'old':dict(symbol='NAS100',side=1,risk=24.,margin=500.)};r=allocate(self.meta,100.,10.,.1,6.,5000.,5000.,p,'NAS100',1,5000.,5000.)
        self.assertEqual(r['total_budget'],50);self.assertEqual(r['lane_budget'],25);self.assertFalse(r['reasons']);self.assertGreater(r['quantity']*r['perlot']+24,25);self.assertLessEqual(r['quantity']*r['perlot']+24,50)
    def test_current_equity_limits_and_transaction_costs(self):
        r=allocate(self.meta,100.,10.,.2,12.,4800.,4900.,{},'NAS100',1,4800.,5000.)
        self.assertEqual(r['total_budget'],49);self.assertEqual(r['lane_budget'],24.5);self.assertAlmostEqual(r['perlot'],1032.)
    def test_daily_and_drawdown_pause_independent_of_trade_count(self):
        r=allocate(self.meta,100.,10.,.1,6.,4899.,4899.,{},'NAS100',1,5000.,5000.)
        self.assertIn('daily_2pct_loss_pause',r['reasons'])
        r=allocate(self.meta,100.,10.,.1,6.,4499.,4499.,{},'NAS100',1,4499.,5000.)
        self.assertIn('portfolio_10pct_drawdown_pause',r['reasons']);self.assertIsNone(APPROVED['daily_trade_count_limit'])
    def test_runtime_books_can_hold_more_than_twentyfive_and_no_old_recovery_sizing(self):
        t=datetime(2026,1,5,15,tzinfo=timezone.utc).timestamp();s=dict(side=1,stop=90.,decision=t,entry_at=t+60);base=dict(symbol='NAS100',exits=[],rr=1.5,start=540,end=900,direction='all',hypothesis='baseline',quality='control',confirmation='control')
        lanes={'a':dict(base,signals={t:s}),'b':dict(base,signals={t+1:dict(s,decision=t+1,entry_at=t+61,stop=90.1)})};b=PaperBook(lanes,{'NAS100':self.meta},dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True),initial=5000.)
        b.quote('NAS100',t+60,100.,101.);b.quote('NAS100',t+61,100.,101.)
        self.assertEqual(len(b.positions),2);self.assertGreater(b.max_risk,25);self.assertLessEqual(b.max_risk,50)
        self.assertEqual(b.result()['active_limits']['daily_trade_count_limit'],None)
    def test_intrapoll_stop_breach_not_hidden_by_rebound_and_no_preentry_path(self):
        t=datetime(2026,1,5,15,tzinfo=timezone.utc).timestamp();s=dict(side=1,stop=90.,decision=t,entry_at=t+60);lane=dict(symbol='NAS100',signals={t:s},exits=[],rr=1.5,start=540,end=900,direction='all',hypothesis='baseline',quality='control',confirmation='control')
        b=PaperBook({'NAS15':lane},{'NAS100':self.meta},dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True),initial=5000.);b.quote('NAS100',t+60,100.,101.)
        b.received_path('NAS100',t+60.5,100.,101.,[(t+59,80.,81.)]);self.assertEqual(len(b.positions),1)
        b.received_path('NAS100',t+62,100.,101.,[(t+61,89.,90.),(t+61.5,100.,101.)]);self.assertEqual(len(b.positions),0);self.assertLess(b.fills[-1]['pnl'],0);self.assertEqual(b.fills[-1]['exit_at'],t+62)


if __name__=='__main__':unittest.main()
