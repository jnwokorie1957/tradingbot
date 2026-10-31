import unittest
import json
from pathlib import Path
from trading_pipeline.research_profiles import preflight, PROFILE

class ProfileTests(unittest.TestCase):
    def test_profile_guards(self):
        d=json.loads((Path(__file__).resolve().parents[1]/'RESEARCH-PROFILE-5000-V1.json').read_text())
        self.assertEqual(d['profile_id'], PROFILE)
        self.assertEqual((d['starting_equity'],d['aspirational_equity'],d['trade_dollar_cap']), (5000,25000,25))
        self.assertEqual((d['trade_fraction'],d['portfolio_fraction'],d['daily_pause'],d['drawdown_pause']),(.005,.01,.02,.10))
        self.assertFalse(d['live_execution_enabled'] or d['broker_orders_enabled'] or d['automatic_claim_replay'])
        self.assertTrue(d['preserve_session_duplicate_and_opposing_exposure_guards'])

    def test_equity_caps(self):
        self.assertEqual(preflight(PROFILE, 2000, 9, 1, 0)['trade_cap'], '10.000')
        self.assertEqual(preflight(PROFILE, 5000, 24, 1, 0)['trade_cap'], '25.000')
        self.assertEqual(preflight(PROFILE, 8000, 24, 1, 0)['trade_cap'], '25')

    def test_costs_consume_budget(self):
        self.assertTrue(preflight(PROFILE,5000,23.78,1.22,0)['arithmetic_pass'])
        self.assertIn('all_in_trade_risk', preflight(PROFILE,5000,23.79,1.22,0)['reasons'])
        self.assertIn('all_in_trade_risk', preflight(PROFILE,5000,1,25,0)['reasons'])

    def test_portfolio(self):
        self.assertTrue(preflight(PROFILE,5000,24,1,25)['arithmetic_pass'])
        self.assertEqual(preflight(PROFILE,5000,24,1,25.01)['reasons'],['open_portfolio_risk'])

    def test_lower_cap(self):
        self.assertFalse(preflight(PROFILE,5000,2,1,0,lower_cap=2.5)['arithmetic_pass'])

    def test_other_profiles_are_not_reconfigured(self):
        for profile in ('legacy-500', '', None):
            with self.assertRaises(ValueError):preflight(profile,500,1,1,0)

    def test_invalid_unknown_and_fractional(self):
        for cost in (None, float('nan'), float('inf'), -1, True):
            with self.assertRaises(ValueError):preflight(PROFILE,5000,1,cost,0)
        for quantity in (0,.5,True):
            with self.assertRaises(ValueError):preflight(PROFILE,5000,1,1,0,quantity)

    def test_pass_is_not_execution_permission(self):
        self.assertFalse(preflight(PROFILE,5000,1,1,0)['execution_authorized'])

if __name__ == '__main__':unittest.main()
