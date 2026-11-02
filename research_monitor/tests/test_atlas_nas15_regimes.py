import unittest
from research_monitor.atlas_nas15_regimes import h4_context, h4_pass, make_variants


class RegimeCausalityChecks(unittest.TestCase):
    def bars(self):
        return [dict(t=i*60,open=100+i/6000,high=101+i/6000,low=99+i/6000,close=100+i/6000,volume=1,spread=1.) for i in range(96*60)]

    def test_forming_four_hour_and_future_prices_do_not_change_context(self):
        one=self.bars();t=90*3600;plans={t:dict(side=1,reference=103.,features={})}
        a=h4_context(one,plans);prefix=h4_context([b for b in one if b['t']+60<=t],plans)
        self.assertEqual(a,prefix)
        mutated=[dict(b,close=99999.,high=100000.) if b['t']>=t else b for b in one]
        self.assertEqual(a,h4_context(mutated,plans))
        self.assertEqual(a[t]['features']['h4_utc']['end'],88*3600)
        self.assertTrue(h4_pass(a[t]))

    def test_incomplete_four_hour_bucket_is_not_filled(self):
        one=self.bars();t=80*3600
        s=h4_context([b for b in one if b['t']!=60],{t:dict(side=1,reference=103.,features={})})[t]
        self.assertFalse(h4_pass(s))

    def test_short_addition_does_not_modify_base_or_spx(self):
        plans={100:dict(side=1,reference=100.,strong_close=False,features={}),200:dict(side=-1,reference=90.,strong_close=True,features=dict(directional_efficiency=.4)),300:dict(side=-1,reference=90.,strong_close=False,features=dict(directional_efficiency=.1))}
        base={'NAS15':dict(direction='long_only',signals=plans,rr=1.5),'SPX15':dict(direction='long_only',signals={},rr=1.5)}
        variants=make_variants(base,{'NAS100':[]})
        self.assertEqual(base['NAS15']['direction'],'long_only')
        self.assertEqual(variants['add_short']['NAS15']['direction'],'all')
        self.assertEqual(set(variants['confirmed_short']['NAS15']['signals']),{100,200})
        for lanes in variants.values():
            self.assertEqual(lanes['SPX15'],base['SPX15']);self.assertEqual(lanes['NAS15']['rr'],1.5)


if __name__=='__main__':unittest.main()
