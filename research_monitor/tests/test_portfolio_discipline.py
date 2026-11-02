import unittest
from research_monitor.portfolio_discipline_rules import reject_state
from research_monitor.risk_review import RiskReview


class PortfolioDisciplineChecks(unittest.TestCase):
    def test_efficiency_gate_depends_only_on_realized_streak(self):
        g=RiskReview('recovery_trend');s={'features':{'directional_efficiency':.2}};lane={'efficiency_after_losses':2}
        self.assertIsNone(reject_state(lane,s,g,1,[]));g.exited(-1,1);self.assertIsNone(reject_state(lane,s,g,2,[]));g.exited(-1,2)
        self.assertEqual(reject_state(lane,s,g,3,[]),'recovery_efficiency_below_030')
        g.exited(1,3);self.assertIsNone(reject_state(lane,s,g,4,[]))

    def test_daily_halt_resets_but_loss_streak_persists(self):
        g=RiskReview('recovery_trend');g.session_start('2026-01-05');g.exited(-1,1)
        self.assertEqual(reject_state({'daily_loss_limit':1},{},g,2,[]),'daily_loss_entry_halt')
        g.session_start('2026-01-06');self.assertIsNone(reject_state({'daily_loss_limit':1},{},g,100000,[]));self.assertEqual(g.loss_streak,1)

    def test_portfolio_pause_expires_and_positive_exit_breaks_it(self):
        g=RiskReview('recovery_trend');lane={'portfolio_two_loss_pause_seconds':1800}
        self.assertEqual(reject_state(lane,{},g,120,[(0,-1),(60,-1)]),'portfolio_loss_cluster_pause')
        self.assertIsNone(reject_state(lane,{},g,1860,[(0,-1),(60,-1)]))
        self.assertIsNone(reject_state(lane,{},g,121,[(0,-1),(60,-1),(120,1)]))


if __name__=='__main__':unittest.main()
