import unittest
import numpy as np
from .data import DTYPE
from .engine import path

META=dict(trade_tick_size=.1,trade_tick_value_loss=10.,volume_min=.01,volume_step=.01)
COST=dict(spread=1.,fee=6.,slip_ticks=1,exit_delay=0.)


class ExitChecks(unittest.TestCase):
    def run_path(self,prices,style,quantity=.02,structure=None,delay=0.):
        q=np.empty(len(prices),dtype=DTYPE);q['t']=1000+np.arange(len(q));q['bid']=prices;q['ask']=q['bid']+.1
        return path(q,q['t'],0,100.,99.,1,quantity,dict(expiry_at=1000+len(q)-1),dict(rr=1.5),style,META,dict(COST,exit_delay=delay),[],structure or (np.array([]),np.array([])))

    def test_fixed_original_and_one_point_five_are_identical(self):
        a=self.run_path([100.,100.5,101.6,100.], 'original');b=self.run_path([100.,100.5,101.6,100.],'fixed_1_5');self.assertEqual(a,b);self.assertAlmostEqual(a['legs'][-1]['price'],101.4)

    def test_trailing_uses_prior_quote_and_retains_gap_loss(self):
        r=self.run_path([100.,102.,102.8,100.], 'trailing');self.assertEqual(r['legs'][-1]['index'],3);self.assertAlmostEqual(r['legs'][-1]['price'],99.9);self.assertGreater(r['final_stop_R'],1.)
        gap=self.run_path([100.,95.,95.],'fixed_4');self.assertAlmostEqual(gap['legs'][-1]['price'],94.9)

    def test_partial_lots_and_fee_quantity_reconcile(self):
        r=self.run_path([100.,101.6,103.,101.,100.],'partial_trailing',.03);self.assertEqual(len(r['legs']),2);self.assertAlmostEqual(sum(x['quantity'] for x in r['legs']),.03);self.assertAlmostEqual(r['legs'][0]['quantity'],.01)
        small=self.run_path([100.,101.6,103.,101.,100.],'partial_trailing',.01);self.assertTrue(small['partial_fallback']);self.assertEqual(len(small['legs']),1)

    def test_structure_unavailable_before_completed_bar(self):
        r=self.run_path([100.,102.,102.,100.,100.],'structure',structure=(np.array([1004.]),np.array([101.9])));self.assertEqual(r['legs'][-1]['index'],4)

    def test_severe_delay_uses_later_observed_quote(self):
        r=self.run_path([100.,98.8,97.,96.],'fixed_2',delay=1.);self.assertEqual(r['legs'][-1]['index'],2);self.assertAlmostEqual(r['legs'][-1]['price'],96.9)


if __name__=='__main__':unittest.main()
