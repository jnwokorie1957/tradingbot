"""Execution and causality checks for the independent discovery implementation."""
import unittest
from datetime import datetime,timezone
import numpy as np
from .data import candles, BARS
from .engine import Account,COSTS
from .signals import Signals

META=dict(trade_tick_size=.1,trade_tick_value_loss=10.,trade_contract_size=100.,assumed_margin_rate=.005,volume_min=.01,volume_step=.01,volume_max=1000.)


class Checks(unittest.TestCase):
    def plan(self,t):return dict(decision=t-60,entry_at=t,side=1,stop=99.,room=None,deadline=t+100,hold_seconds=50)

    def test_stop_gap_can_exceed_planned_risk(self):
        b=Account(META,COSTS['standard'],1.5);t=np.array([1000.,1001.,1002.,1050.]);bid=np.array([100.,100.,95.,95.]);ask=bid+.1
        b.run_day('2026-01-01',t,bid,ask,[self.plan(1000.)]);f=b.fills[0]
        self.assertGreater(-f['pnl'],f['planned_risk']);self.assertLessEqual(f['planned_risk'],25);self.assertEqual(f['reason'],'stop_quote')
        self.assertAlmostEqual(f['quantity']/.01,round(f['quantity']/.01))

    def test_minimum_lot_not_forced(self):
        b=Account(META,COSTS['standard'],1.5);s=self.plan(1000.);s['stop']=50.
        b.run_day('2026-01-01',np.array([1000.,1050.]),np.array([100.,100.]),np.array([100.1,100.1]),[s])
        self.assertFalse(b.fills);self.assertEqual(b.decisions[0]['reason'],'minimum_lot_or_margin_or_risk')

    def test_intratrade_loss_pauses_entries_even_after_recovery(self):
        b=Account(META,COSTS['standard'],1.5);b.day='2026-01-01';b.day_start=5100.
        t=np.array([1000.,1001.,1002.,1050.,1100.,1150.]);bid=np.array([100.,99.7,102.,102.,100.,102.]);ask=bid+.1
        b.run_day('2026-01-01',t,bid,ask,[self.plan(1000.),self.plan(1100.)])
        self.assertEqual(len(b.fills),1);self.assertTrue(b.daily_paused);self.assertEqual(b.decisions[-1]['reason'],'daily_2pct_loss_pause')

    def test_incomplete_five_minute_bar_excluded(self):
        t=np.array([0.,60.,180.,240.,300.,360.,420.,480.,540.]);bid=np.arange(len(t),dtype=float)+100
        b=candles(t,bid,5);self.assertEqual(len(b),1);self.assertEqual(b[0]['t'],300.)

    def test_signals_prefix_does_not_change_with_future(self):
        base=datetime(2026,1,5,14,0,tzinfo=timezone.utc).timestamp();rng=np.random.default_rng(44);x=100+np.cumsum(rng.normal(0,.4,200));b=np.zeros(200,dtype=BARS)
        b['t']=base+np.arange(200)*60;b['open']=x;b['close']=x+rng.normal(0,.2,200);b['high']=np.maximum(b['open'],b['close'])+.2;b['low']=np.minimum(b['open'],b['close'])-.2
        first=Signals(1,.1).generate(b[:120]);all_=Signals(1,.1).generate(b)
        for family in first:self.assertEqual(first[family],[s for s in all_[family] if s['decision']<=base+120*60])

    def test_target_room_and_delayed_fresh_quote_gate(self):
        b=Account(META,COSTS['standard'],1.5);s=self.plan(1000.);s['room']=100.5
        b.run_day('2026-01-01',np.array([1000.,1050.]),np.array([100.,100.]),np.array([100.1,100.1]),[s]);self.assertEqual(b.decisions[0]['reason'],'insufficient_preentry_target_room')
        c=Account(META,COSTS['standard'],1.5);c.run_day('2026-01-01',np.array([1006.,1050.]),np.array([100.,100.]),np.array([100.1,100.1]),[self.plan(1000.)]);self.assertEqual(c.decisions[0]['reason'],'no_fresh_entry_quote')


if __name__=='__main__':unittest.main()
