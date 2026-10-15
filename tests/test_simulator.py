import json
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from simulator import Engine, Hypothesis, Ledger, Policy
from research import walk_forward as registered_walk_forward, preregister
from data_quality import inspect_history


def walk_forward(ledger,contracts,events,hypotheses,train_size,validation_size,holdout_start,**kwargs):
    identity=uuid.uuid4().hex
    preregister(ledger,identity,'fixture-'+identity,contracts,hypotheses,train_size,validation_size,
                holdout_start,**kwargs)
    return registered_walk_forward(ledger,contracts,events,hypotheses,train_size,validation_size,
                holdout_start,experiment_id=identity,**kwargs)


def contract(**kw):
    c=dict(currency='USD',multiplier=1,tick=.25,initial_margin=100,maintenance_margin=80,
           fee_per_side=.1,daily_carry_fee=0,spec_verified=True,permission_verified=True,
           costs_verified=True,data_verified=True,evidence_source='SYNTHETIC TEST ONLY',
           valid_from='2026-01-01T00:00:00Z',valid_until='2026-02-01T00:00:00Z',
           exit_before='2026-01-30T00:00:00Z',requires_adjustment=False)
    return c|kw


def bar(i, close, low=None, high=None):
    return dict(id=f'b{i}',kind='bar',contract='TEST',start=f'2026-01-01T00:0{i}:00Z',
        end=f'2026-01-01T00:0{i+1}:00Z',available_at=f'2026-01-01T00:0{i+1}:00Z',
        open=close,high=high if high is not None else close,low=low if low is not None else close,
        close=close,volume=10)


def quote(bid=101,ask=101.25,at='2026-01-01T00:03:01Z',**kw):
    if kw.get('adjustment_verified'):
        kw=dict(adjustment_source='synthetic accounting fixture',adjustment_at=at)|kw
    return dict(id='q'+at,kind='quote',contract='TEST',available_at=at,quote_at=at,
                bid=bid,ask=ask,bid_size=1,ask_size=1,quality='verified')|kw


class Tests(unittest.TestCase):
    def setUp(self):
        self.test_path=Path(__file__).resolve().parent/('test-'+uuid.uuid4().hex+'.sqlite')
        self.ledger=Ledger(str(self.test_path))

    def tearDown(self):
        self.ledger.close()
        self.test_path.unlink()

    def engine(self,c=None,p=Policy(),run='test'):
        return Engine(self.ledger,run,{'TEST':c or contract()},p,Hypothesis(lookback=2),True)

    def signal(self,e):
        for b in (bar(0,100),bar(1,100),bar(2,101,100.5,101)): e.apply(b)

    def test_next_quote_only_and_resume(self):
        e=self.engine(); self.signal(e)
        self.assertEqual(e.apply(quote(at='2026-01-01T00:03:00Z'))['status'],'no_executable_signal')
        q=quote(); self.assertEqual(e.apply(q)['status'],'entry')
        cash=e.state['cash']; self.assertEqual(e.apply(q)['status'],'entry'); self.assertEqual(e.state['cash'],cash)
        resumed=self.engine(); self.assertEqual(resumed.state,e.state)
        with self.assertRaises(ValueError): resumed.apply(q|{'bid':100})

    def test_future_and_bad_bars_atomic(self):
        e=self.engine()
        for b in (bar(0,100)|{'end':'2026-01-01T00:02:00Z'},bar(0,100)|{'high':99},bar(0,float('nan'))):
            with self.assertRaises(ValueError): e.apply(b)
        self.assertIsNone(e.state['last_time'])

    def test_stop_gap_costs(self):
        e=self.engine(); self.signal(e); e.apply(quote())
        out=e.apply(quote(90,90.25,at='2026-01-01T00:03:02Z'))
        self.assertEqual(out['reason'],'stop'); self.assertEqual(out['fill'],89.75)
        self.assertAlmostEqual(out['net_pnl'],-11.95)
        self.assertTrue(e.state['daily_paused'])

    def test_risk_margin_and_unknown_skip(self):
        for i,(c,reason) in enumerate([(contract(initial_margin=501),'margin_and_loss_reserve'),
            (contract(multiplier=100),'one_contract_trade_risk'),
            (contract(permission_verified=False),'unverified_contract_permission_cost_or_data'),
            (contract(valid_until='2026-01-01T00:01:00Z'),'stale_or_future_evidence')]):
            e=self.engine(c,run=str(i)); self.signal(e)
            self.assertEqual(e.apply(quote())['reason'],reason)
            self.assertEqual(e.state['cash'],500)

    def test_stale_crossed_quotes_no_fill(self):
        e=self.engine(); self.signal(e)
        self.assertEqual(e.apply(quote(ask=100))['status'],'skip')
        self.assertEqual(e.apply(quote(at='2026-01-01T00:03:02Z',quote_at='2026-01-01T00:02:00Z'))['status'],'skip')
        self.assertFalse(e.state['positions'])

    def test_financing_required_and_applied(self):
        e=self.engine(contract(requires_adjustment=True)); self.signal(e)
        self.assertEqual(e.apply(quote())['reason'],'missing_verified_financing_adjustment')
        e.apply(quote(at='2026-01-01T00:03:02Z',adjustment=10,adjustment_verified=True))
        out=e.apply(quote(102,102.25,at='2026-01-01T01:03:02Z',adjustment=9,adjustment_verified=True))
        self.assertAlmostEqual(out['net_pnl'],-.95)

    def test_roll_no_stitched_fill(self):
        e=self.engine(); self.signal(e); e.apply(quote())
        with self.assertRaises(ValueError): e.apply(dict(id='r',kind='roll',contract='TEST',new_contract='NEW',available_at='2026-01-01T01:00:00Z'))
        self.assertTrue(e.state['positions'])

    def test_policy_validation(self):
        for kw in ({'budget':-1},{'trade_risk':0},{'slippage_ticks':.5}):
            with self.assertRaises(ValueError): Policy(**kw)

    def test_chronological_and_holdout_not_touched(self):
        events=[bar(0,100),bar(1,100),bar(2,101),quote()]
        # Invalid holdout event would fail if it were evaluated.
        events.append(dict(available_at='2026-01-02T00:00:00Z',id='holdout',kind='INVALID'))
        r=walk_forward(self.ledger,{'TEST':contract()},events,[Hypothesis(lookback=2)],2,1,'2026-01-02T00:00:00Z',synthetic=True)
        self.assertEqual(r['holdout']['status'],'untouched')
        self.assertFalse(r['validated_edge'])
        self.assertGreater(len(r['trials']),0)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM events WHERE id='holdout'").fetchone()[0],0)

    def test_failed_trials_retained(self):
        events=[bar(0,100)|{'high':99},bar(1,100),bar(2,101)]
        r=walk_forward(self.ledger,{'TEST':contract()},events,[Hypothesis(lookback=2)],2,1,'2026-01-02T00:00:00Z',synthetic=True)
        self.assertEqual(r['trials'][0]['result']['status'],'failed')
        self.assertEqual(self.ledger.db.execute('SELECT count(*) FROM trials').fetchone()[0],1)

    def test_intake_quarantine(self):
        d=dict(time=['2026-01-01T00:00:00Z'],open=[10],high=[11],low=[9],close=[12],volume=[1],chart_step=3600)
        r=inspect_history(d,'2026-01-01T00:30:00Z')
        self.assertIn('ohlc_bounds',r['quarantined'][0]['reasons'])
        self.assertIn('incomplete_bar',r['quarantined'][0]['reasons'])
        self.assertFalse(r['execution_eligible'])

    def test_portfolio_risk_with_fresh_marks(self):
        e=Engine(self.ledger,'portfolio',{'TEST':contract(),'SECOND':contract()},
                 replace(Policy(),portfolio_risk=.005),Hypothesis(lookback=2),True)
        for b in (bar(0,100),bar(1,100),bar(2,101,100.5,101)):
            e.apply(b)
            e.apply(b|{'id':b['id']+'s','contract':'SECOND'})
        self.assertEqual(e.apply(quote())['status'],'entry')
        out=e.apply(quote(at='2026-01-01T00:03:02Z',contract='SECOND'))
        self.assertEqual(out['reason'],'portfolio_risk')

    def test_drawdown_persists_across_utc_day(self):
        e=self.engine(); self.signal(e); e.apply(quote())
        e.apply(quote(40,40.25,at='2026-01-01T00:03:02Z'))
        self.assertTrue(e.state['paused'])
        e.apply(quote(at='2026-01-02T00:00:00Z'))
        self.assertFalse(e.state['daily_paused'])
        self.assertTrue(e.state['paused'])

    def test_short_fill_and_stop(self):
        e=self.engine()
        for b in (bar(0,100),bar(1,100),bar(2,99,99,99.5)): e.apply(b)
        self.assertEqual(e.apply(quote(98.75,99))['fill'],98.5)
        out=e.apply(quote(101,101.25,at='2026-01-01T00:03:02Z'))
        self.assertEqual(out['fill'],101.5)
        self.assertAlmostEqual(out['net_pnl'],-3.2)

    def test_evidence_expiry_closes_position(self):
        e=self.engine(contract(valid_until='2026-01-01T00:04:00Z'))
        self.signal(e); e.apply(quote())
        self.assertEqual(e.apply(quote(at='2026-01-01T00:04:00Z'))['reason'],'evidence_expired')

    def test_reject_off_tick_and_changed_resume(self):
        e=self.engine(); self.signal(e)
        self.assertEqual(e.apply(quote(101.01,101.25))['reason'],'off_tick_quote')
        with self.assertRaises(ValueError): self.engine(contract(initial_margin=200))

    def test_out_of_order_rejected(self):
        e=self.engine(); self.signal(e)
        with self.assertRaises(ValueError): e.apply(quote(at='2026-01-01T00:00:00Z'))

    def test_daily_carry_cost(self):
        e=self.engine(contract(daily_carry_fee=.1)); self.signal(e); e.apply(quote())
        out=e.apply(quote(at='2026-01-02T00:00:00Z'))
        self.assertAlmostEqual(out['net_pnl'],-1.05)


if __name__=='__main__': unittest.main()
