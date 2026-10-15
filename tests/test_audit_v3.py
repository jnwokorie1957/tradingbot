"""Direct-engine ceiling regressions; all data are synthetic software fixtures."""
import unittest
from trading_pipeline.engine_v4 import Engine,Ledger,Hypothesis,Policy
from test_simulator import contract,bar,quote

class DirectPolicyInvariantTests(unittest.TestCase):
 def execute(self,equity,percent,fee):
  ledger=Ledger(':memory:')
  try:
   engine=Engine(ledger,'direct',{'TEST':contract(fee_per_side=fee)},Policy(trade_risk=percent),Hypothesis(lookback=2),True)
   engine.state.update(cash=equity,equity=equity,peak=equity,day_start=equity)
   for b in [bar(0,100),bar(1,100),bar(2,101,100.5,101)]:engine.apply(b)
   return engine.apply(quote())
  finally:ledger.close()
 def test_relaxed_policy_cannot_exceed_half_percent_after_loss(self):
  r=self.execute(400,.01,.4)
  self.assertEqual(r['reason'],'one_contract_trade_risk');self.assertAlmostEqual(r['risk'],2.05)
 def test_relaxed_policy_still_admits_risk_below_invariant(self):
  r=self.execute(400,.01,.35)
  self.assertEqual(r['status'],'entry');self.assertAlmostEqual(r['risk'],1.95)
 def test_stricter_policy_is_honored(self):
  r=self.execute(400,.0035,.1)
  self.assertEqual(r['reason'],'one_contract_trade_risk');self.assertAlmostEqual(r['risk'],1.45)
 def test_stricter_policy_admits_within_limit(self):
  r=self.execute(400,.0035,.05)
  self.assertEqual(r['status'],'entry');self.assertAlmostEqual(r['risk'],1.35)
 def test_relaxed_policy_cannot_exceed_absolute_ceiling_after_gain(self):
  r=self.execute(600,.01,.7)
  self.assertEqual(r['reason'],'one_contract_trade_risk');self.assertAlmostEqual(r['risk'],2.65)
