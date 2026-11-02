import unittest,numpy as np
from .breakeven import protected_path,ORIGINAL_PATH
from atlas_exit_research.data import DTYPE


def path(prices,side=1,cost=None):
    t=np.arange(len(prices),dtype=float);q=np.array([(float(i),p,p)for i,p in enumerate(prices)],dtype=DTYPE);cost=cost or dict(spread=1.,fee=0.,slip_ticks=0,exit_delay=0.);return protected_path(q,t,0,100.,100-side*10,side,1.,dict(expiry_at=t[-1]),dict(cost_covered_breakeven=True),'fixed_2',dict(trade_tick_size=1.,trade_tick_value_loss=1.),cost,[],None)


class BreakEvenChecks(unittest.TestCase):
    def test_initial_stop_stays_natural_before_one_R(self):
        r=path([100,109,99,90,100]);self.assertEqual(r['legs'][0]['index'],3);self.assertEqual(r['legs'][0]['price'],90);self.assertEqual(r['legs'][0]['reason'],'stop_quote')
    def test_one_R_then_reversal_activates_only_next_quote(self):
        r=path([100,110,100,120]);self.assertEqual(r['legs'][0]['index'],2);self.assertEqual(r['legs'][0]['price'],100);self.assertEqual(r['legs'][0]['reason'],'cost_covered_stop_quote')
    def test_cost_cover_includes_fee_and_exit_slippage(self):
        c=dict(spread=1.,fee=2.,slip_ticks=1,exit_delay=0.);r=path([100,110,103,120],cost=c);self.assertEqual(r['legs'][0]['price'],102);self.assertEqual((r['legs'][0]['price']-100)-2,0)
    def test_uninterrupted_winner_keeps_two_R_target(self):
        r=path([100,110,115,120,125]);self.assertEqual(r['legs'][0]['index'],3);self.assertEqual(r['legs'][0]['price'],120)
    def test_short_stop_and_target_symmetry(self):
        r=path([100,90,100,80],side=-1);self.assertEqual(r['legs'][0]['index'],2);self.assertEqual(r['legs'][0]['price'],100)
    def test_gap_and_severe_delay_not_clipped(self):
        c=dict(spread=1.,fee=2.,slip_ticks=1,exit_delay=1.);r=path([100,110,102,85,100],cost=c);self.assertEqual(r['legs'][0]['index'],3);self.assertEqual(r['legs'][0]['price'],84);self.assertEqual(r['legs'][0]['reason'],'cost_covered_stop_quote_delayed')


if __name__=='__main__':unittest.main()
