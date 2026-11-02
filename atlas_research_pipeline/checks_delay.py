import copy,unittest
from .execution_delay import delayed,setup_identity,checks_for_development
from research_monitor.atlas_live_core import intent_id


class DelayChecks(unittest.TestCase):
    def test_delay_changes_only_execution_time_and_not_original(self):
        lanes={'NAS15':dict(symbol='NAS100',rr=1.5,signals={1000:dict(decision=1000,entry_at=1060,stop=90.,side=1,features={'hourly':{'end':900}},reference=100.)},native=[{'t':100}])};before=copy.deepcopy(lanes);new=delayed(lanes,10);self.assertEqual(new['NAS15']['signals'][1000]['entry_at'],1010);self.assertEqual(lanes,before);self.assertEqual(setup_identity(new),setup_identity(lanes));self.assertEqual(intent_id('NAS15',new['NAS15']['signals'][1000]),intent_id('NAS15',lanes['NAS15']['signals'][1000]))
    def test_unregistered_or_instant_delays_rejected(self):
        for delay in [-1,0,1,20,90]:
            with self.assertRaises(ValueError):delayed({},delay)
    def test_sensitivity_cannot_rescue_failed_primary(self):
        rows=[]
        for cost in ['standard','higher','severe']:
            for profile,net in [('control60',100),('primary10',99 if cost=='severe' else 101),('sensitivity5',1000)]:rows.append(dict(cost=cost,profile=profile,metrics=dict(trades=40,net_pnl=net,profit_factor=1.5),account=dict(quote_drawdown_pct=3,open_positions=0,incomplete_paths=0)))
        self.assertIn('severe: net below60second control',checks_for_development(rows))


if __name__=='__main__':unittest.main()
