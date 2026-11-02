import unittest
from datetime import datetime,timedelta
from atlas_exit_research.data import NY
from .signals import generate
from .monthly import calculate


def bars(day,until=960,opening=100.):
    begin=datetime.fromisoformat(day).replace(hour=9,minute=30,tzinfo=NY).timestamp();out=[]
    for n in range(until-570):
        price=opening+n*.001;out.append(dict(t=begin+60*n,open=price,high=price+.02,low=price-.02,close=price+.01,volume=1,spread=.01))
    return out


def fill(day,pnl):
    at=datetime.fromisoformat(day).replace(hour=12,tzinfo=NY).timestamp();return dict(entry_at=at,exit_at=at+60,pnl=pnl)


class PipelineChecks(unittest.TestCase):
    def test_future_append_cannot_change_existing_signals(self):
        prior=bars('2026-01-05');current=bars('2026-01-06',930,101.);prefix=generate(prior+current,.01)[0];full=generate(prior+bars('2026-01-06',960,101.)+bars('2026-01-07'),.01)[0];cut=current[-1]['t']+60
        self.assertTrue(prefix['late_momentum']);self.assertEqual(prefix,{family:{t:s for t,s in signals.items()if t<=cut}for family,signals in full.items()})
    def test_missing_completed_context_blocks_late_signal(self):
        prior=bars('2026-01-05');current=bars('2026-01-06',930,101.);del current[5];self.assertFalse(generate(prior+current,.01)[0]['late_momentum'])
    def test_incomplete_previous_session_is_not_replaced_by_older_close(self):
        prior=bars('2026-01-05');del prior[7];self.assertFalse(generate(prior+bars('2026-01-06',930,101.),.01)[0]['late_momentum'])
    def test_monthly_cash_compounds_and_includes_zero_month(self):
        x=calculate([fill('2026-01-05',100),fill('2026-02-03',-50)],5000,'2026-01-01','2026-04-01');self.assertEqual(len(x['months']),3);self.assertAlmostEqual(x['months'][0]['return_pct'],2);self.assertAlmostEqual(x['months'][1]['return_pct'],-50/5100*100);self.assertEqual(x['months'][-1]['return_pct'],0);self.assertEqual(x['statistics']['independent_thresholds']['15']['eligible_months'],0);self.assertIsNone(x['statistics']['independent_thresholds']['15']['frequency_pct'])
    def test_partial_month_preserved_but_excluded_from_headline_average(self):
        x=calculate([fill('2025-12-16',500),fill('2026-01-05',100)],5000,'2025-12-15','2026-02-01');self.assertFalse(x['months'][0]['complete_trading_month']);self.assertEqual(x['months'][-1]['ending_equity'],5600);self.assertAlmostEqual(x['statistics']['average_monthly_net_return_pct'],100/5500*100)


if __name__=='__main__':unittest.main()
