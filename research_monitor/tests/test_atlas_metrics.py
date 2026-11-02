import unittest
from datetime import datetime,timezone
import numpy as np
from research_monitor.atlas_metrics import metrics,reconstruct
from research_monitor.atlas_audit_engine import replay


class AtlasMetricChecks(unittest.TestCase):
    def case(self,delay=0):
        t=datetime(2026,1,5,15,tzinfo=timezone.utc).timestamp()
        q=np.array([(int((t+i)*1000),b,a) for i,b,a in [(0,100.,101.),(1,117.,118.),(2,80.,81.)]],dtype=[('time_msc','i8'),('bid','f8'),('ask','f8')])
        meta={'SPX500':dict(trade_tick_size=.1,trade_tick_value_loss=10.,trade_contract_size=100.,volume_min=.01,volume_step=.01)}
        lane=dict(symbol='SPX500',signals={t-60:dict(entry_at=t,side=1,stop=91.1)},exits=[],rr=1.5,hypothesis='baseline',quality='control',confirmation='control',direction='all',start=540,end=900)
        cfg=dict(spread=1.,fee=6.,slip_ticks=1,exit_delay=delay,margin_multiplier=1.)
        r=replay({'SPX500':[('2026-01-05',q,0)]},{'SPX15':lane},meta,scenario=cfg,capture=True)
        return r,meta,cfg

    def test_quote_cash_reconstruction_and_costs(self):
        r,meta,cfg=self.case();audit=reconstruct(r['trace'],r['private_fills'],meta,r['symbol_ids'],cfg,r['quote_marked_drawdown_pct'])
        self.assertLess(audit['max_equity_reconstruction_error'],1e-8)
        self.assertAlmostEqual(audit['commission_dollars'],sum(f['quantity']*6 for f in r['private_fills']))
        self.assertLess(audit['reserve_overlay']['quote_drawdown_pct'],audit['quote_drawdown_pct'])

    def test_exit_latency_is_causal_and_can_worsen_a_target(self):
        immediate,_,_=self.case();delayed,meta,cfg=self.case(1)
        self.assertGreater(immediate['net_pnl'],0);self.assertLess(delayed['net_pnl'],0)
        self.assertTrue(delayed['private_fills'][0]['reason'].endswith('_delayed'))
        reconstruct(delayed['trace'],delayed['private_fills'],meta,delayed['symbol_ids'],cfg,delayed['quote_marked_drawdown_pct'])

    def test_profit_factor_expectancy_and_loss_streak(self):
        t=datetime(2026,1,5,15,tzinfo=timezone.utc).timestamp();fills=[dict(entry_at=t+i,exit_at=t+i,pnl=v,planned_risk=10.) for i,v in enumerate([20.,-10.,-5.,15.])]
        m=metrics(fills,first='2026-01-05',end='2026-01-10')
        self.assertAlmostEqual(m['profit_factor'],35/15);self.assertAlmostEqual(m['expectancy_dollars'],5.)
        self.assertEqual(m['max_consecutive_losses'],2);self.assertEqual(m['win_rate'],50.)
        self.assertEqual(len(m['daily_returns']),5);self.assertAlmostEqual(m['daily_returns'][0],.04)


if __name__=='__main__':unittest.main()
