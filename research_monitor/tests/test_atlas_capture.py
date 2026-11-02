import unittest
from research_monitor.atlas_capture_core import allocation,PaperBook
from research_monitor.risk_review import RiskReview


class SharedAdmissionChecks(unittest.TestCase):
    def setUp(self):
        self.m=dict(trade_tick_size=.1,trade_tick_value_loss=10.,trade_contract_size=100.,assumed_margin_rate=.005,volume_min=.01,volume_step=.01,volume_max=1000.);self.g=RiskReview('recovery_trend');self.policy=dict(governed=True,risk_pct=.01)
    def allocate(self,positions,side=1):return allocation(self.m,100.,1.,.1,6.,500.,500.,positions,'NAS100',side,self.g,self.policy)
    def test_direction_aware_admission_allows_same_direction(self):
        p={'a':dict(symbol='NAS100',side=1,risk=3.,margin=10.)};r=self.allocate(p)
        self.assertNotIn('conflicting_same_symbol_exposure',r['reasons']);self.assertGreaterEqual(r['quantity'],.01);self.assertLessEqual(r['quantity']*r['perlot']+3,10)
        p['a']['side']=-1;self.assertIn('conflicting_same_symbol_exposure',self.allocate(p)['reasons'])
    def test_correlation_is_gross_and_no_cross_asset_netting_credit(self):
        p={'a':dict(symbol='SPX500',side=-1,risk=9.,margin=10.)};r=self.allocate(p)
        self.assertNotIn('conflicting_same_symbol_exposure',r['reasons']);self.assertIn('shared_gross_risk_budget',r['reasons'])
    def test_minimum_lot_is_not_fractionalized_to_force_frequency(self):
        r=allocation(self.m,100.,10.,.1,6.,500.,500.,{},'NAS100',1,self.g,self.policy)
        self.assertEqual(r['quantity'],0);self.assertIn('minimum_lot_above_trade_risk',r['reasons'])
    def test_causal_defer_of_busy_gate_and_duplicates(self):
        from datetime import datetime,timezone
        t=datetime(2026,1,5,15,tzinfo=timezone.utc).timestamp();s=dict(side=1,stop=90.,decision=t,entry_at=t+60);lane=dict(symbol='NAS100',signals={},exits=[],rr=1.5,start=540,end=900,direction='all',hypothesis='baseline',quality='control',confirmation='control')
        book=PaperBook({'NAS15':lane},{'NAS100':self.m});book._submit('NAS15',s,t);book._submit('NAS15',s,t)
        self.assertEqual(book.decisions[-1]['reason'],'duplicate_intent')
    def test_zero_unverified_events_not_called_validation(self):
        self.assertLessEqual(self.allocate({})['quantity']*self.allocate({})['perlot'],5.)
    def test_received_execution_waits_for_post_deadline_source_quote(self):
        from research_monitor.atlas_live_core import PaperBook as LiveBook,shared_allocation
        from research_monitor.atlas_capture_core import allocation
        from datetime import datetime,timezone
        self.assertIs(shared_allocation,allocation)
        t=datetime(2026,1,5,15,tzinfo=timezone.utc).timestamp();s=dict(side=1,stop=90.,decision=t,entry_at=t+60);lane=dict(symbol='NAS100',signals={t:s},exits=[],rr=1.5,start=540,end=900,direction='all',hypothesis='baseline',quality='control',confirmation='control')
        b=LiveBook({'NAS15':lane},{'NAS100':self.m});b.quote('NAS100',t+60,100,101,source_time=t+59.9);self.assertFalse(b.positions)
        b.quote('NAS100',t+61,100,101,source_time=t+60.5);self.assertTrue(b.positions);self.assertEqual(next(iter(b.positions.values()))['at'],t+61)


if __name__=='__main__':unittest.main()
