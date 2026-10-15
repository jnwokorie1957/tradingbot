import json
import unittest
from dataclasses import replace
from simulator import Engine,Ledger,Hypothesis,Policy
from research import preregister,walk_forward
from data_quality import inspect_history
from tests.test_simulator import contract,bar,quote


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self): self.ledger=Ledger(':memory:')
    def tearDown(self): self.ledger.close()
    def engine(self,contracts=None):
        return Engine(self.ledger,'review',contracts or {'TEST':contract()},hypothesis=Hypothesis(lookback=2),synthetic=True)
    def signal(self,e):
        for b in (bar(0,100),bar(1,100),bar(2,101,100.5,101)): e.apply(b)

    def test_regressing_and_equal_quotes_cannot_exit(self):
        e=self.engine(); self.signal(e); e.apply(quote())
        before=json.dumps(e.state['positions'])
        for i,stamp in enumerate(('2026-01-01T00:02:59Z','2026-01-01T00:03:01Z')):
            out=e.apply(quote(90,90.25,at=f'2026-01-01T00:03:0{i+2}Z',quote_at=stamp))
            self.assertEqual(out['reason'],'nonprogressing_quote_timestamp')
        self.assertEqual(json.dumps(e.state['positions']),before)
        self.assertAlmostEqual(e.state['cash'],499.9)

    def test_quote_after_market_entry_but_before_observed_fill_cannot_exit(self):
        e=self.engine(); self.signal(e)
        e.apply(quote(at='2026-01-01T00:03:04Z',quote_at='2026-01-01T00:03:01Z'))
        out=e.apply(quote(90,90.25,at='2026-01-01T00:03:05Z',quote_at='2026-01-01T00:03:03Z'))
        self.assertEqual(out['reason'],'pre_entry_quote')

    def test_ordinary_adjustment_cannot_credit_profit(self):
        e=self.engine(); self.signal(e); e.apply(quote())
        for i,kw in enumerate((dict(adjustment=1000),dict(adjustment=1000,adjustment_verified=True))):
            out=e.apply(quote(at=f'2026-01-01T01:03:0{i+1}Z',**kw))
            self.assertEqual(out['reason'],'unsupported_financing_adjustment')
            self.assertAlmostEqual(e.state['cash'],499.9)

    def test_financing_provenance_and_timestamp_required(self):
        e=self.engine({'TEST':contract(requires_adjustment=True)}); self.signal(e)
        q=quote(adjustment=10,adjustment_verified=True); del q['adjustment_source']
        self.assertEqual(e.apply(q)['reason'],'missing_financing_provenance')
        q=quote(at='2026-01-01T00:03:02Z',adjustment=10,adjustment_verified=True,
                adjustment_at='2026-01-02T00:00:00Z')
        self.assertEqual(e.apply(q)['reason'],'invalid_financing_timestamp')

    def test_contracts_defensively_frozen_and_identity_checked(self):
        original={'TEST':contract()}; e=self.engine(original); self.signal(e); e.apply(quote())
        original['TEST']['multiplier']=1000
        with self.assertRaises(TypeError): e.contracts['TEST']['multiplier']=1000
        snapshot=e.config; snapshot['contracts']['TEST']['multiplier']=1000
        e.apply(quote(104,104.25,at='2026-01-01T00:03:02Z'))
        self.assertAlmostEqual(e.state['cash'],502.05)
        e.policy=replace(Policy(),trade_risk=.02)
        with self.assertRaises(ValueError): e.apply(quote(at='2026-01-01T00:03:03Z'))

    def test_zero_volume_rejected_without_lookback_mutation(self):
        e=self.engine(); e.apply(bar(0,100)); before=json.dumps(e.state)
        for b in (bar(1,1),bar(2,1)):
            with self.assertRaises(ValueError): e.apply(b|{'volume':0})
            self.assertEqual(json.dumps(e.state),before)
        self.assertEqual(e.apply(bar(3,2))['status'],'no_signal')

    def test_bad_chart_durations_quarantined(self):
        for step in (0,-3600,float('nan'),float('inf'),True,'3600',None,1,3600.5):
            d=dict(time=['2026-01-01T00:00:00Z'],open=[100],high=[100],low=[100],close=[100],volume=[1],chart_step=step)
            r=inspect_history(d,'2026-01-01T01:00:00Z','bar_start')
            self.assertEqual(r['accepted'],[])
            self.assertEqual(r['error'],'invalid_or_unsupported_chart_step')

    def plan(self,events,**kw):
        args=(self.ledger,'experiment','dataset',{'TEST':contract()},[Hypothesis(lookback=2)],5,1,'2026-01-02T00:00:00Z')
        preregister(*args,synthetic=True,**kw)
        return walk_forward(self.ledger,{'TEST':contract()},events,[Hypothesis(lookback=2)],5,1,
                            '2026-01-02T00:00:00Z',synthetic=True,experiment_id='experiment')

    def test_utc_aliases_never_duplicate_validation(self):
        rows=[bar(0,100),bar(1,100),bar(2,101,100.5,101),quote(),
              quote(104,104.25,at='2026-01-01T00:03:02Z'),
              quote(at='2026-01-01T00:04:00Z',id='v1'),
              quote(at='2026-01-01T00:04:00+00:00',id='v2'),
              quote(at='2026-01-01T00:05:00Z',id='v3')]
        r=self.plan(rows)
        vals=[t for t in r['trials'] if t['metadata']['phase']=='validation']
        self.assertEqual(len(vals),2)
        sets=[]
        for t in vals:
            run=t['result']['run_id']
            sets.append({r[0] for r in self.ledger.db.execute('SELECT id FROM events WHERE run=?',(run,))})
        self.assertEqual(sets,[{'v1','v2'},{'v3'}])
        self.assertFalse(sets[0]&sets[1])

    def test_durable_preregistration_and_consumption(self):
        with self.assertRaises(ValueError):
            walk_forward(self.ledger,{},[],[Hypothesis()],2,1,'2026-01-02T00:00:00Z')
        self.plan([])
        with self.assertRaises(ValueError): self.plan([])
        with self.assertRaises(ValueError):
            preregister(self.ledger,'new','dataset',{'TEST':contract()},[Hypothesis(lookback=2)],5,1,
                        '2026-01-03T00:00:00Z',synthetic=True)
        with self.assertRaises(ValueError):
            preregister(self.ledger,'real','realdata',{},[Hypothesis()],2,1,'2020-01-01T00:00:00Z')

    def test_changed_plan_rejected_before_trials(self):
        preregister(self.ledger,'p','d',{},[Hypothesis()],2,1,'2026-01-02T00:00:00Z',synthetic=True)
        with self.assertRaises(ValueError):
            walk_forward(self.ledger,{},[],[Hypothesis(lookback=3)],2,1,'2026-01-02T00:00:00Z',synthetic=True,experiment_id='p')

    def update(self,at='2026-01-01T00:03:02Z',effective='2026-01-01T00:03:03Z',**kw):
        return dict(id='margin'+at,kind='margin_update',contract='TEST',available_at=at,
            effective_at=effective,valid_until='2026-02-01T00:00:00Z',initial_margin=600,
            maintenance_margin=550,currency='USD',verified=True,source='synthetic margin bulletin')|kw

    def test_margin_update_activates_at_effective_time_and_survives_resume(self):
        e=self.engine(); self.signal(e); e.apply(quote()); e.apply(self.update())
        self.assertEqual(e.apply(quote(at='2026-01-01T00:03:02Z'))['status'],'mark')
        e=self.engine()
        out=e.apply(quote(at='2026-01-01T00:03:03Z'))
        self.assertEqual(out['reason'],'maintenance_margin_breach')
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM events WHERE id LIKE 'margin%'").fetchone()[0],1)

    def test_margin_invalid_and_expired_evidence(self):
        e=self.engine(); self.signal(e); e.apply(quote())
        with self.assertRaises(ValueError): e.apply(self.update(verified=False))
        e.apply(self.update(effective='2026-01-01T00:03:02Z',initial_margin=100,maintenance_margin=80,
                            valid_until='2026-01-01T00:03:03Z'))
        self.assertEqual(e.apply(quote(at='2026-01-01T00:03:03Z'))['reason'],'margin_evidence_expired')

    def test_actual_qndx_remains_explicitly_blocked(self):
        e=self.engine({'TEST':contract(root='QNDX',requires_adjustment=True)})
        self.signal(e)
        self.assertEqual(e.apply(quote(adjustment=0,adjustment_verified=True))['reason'],
                         'qndx_quarterly_fee_accounting_not_supported')


if __name__=='__main__': unittest.main()
