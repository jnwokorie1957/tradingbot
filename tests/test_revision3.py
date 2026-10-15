import json
import unittest
from simulator import Engine,Ledger,Hypothesis,utc
from tests.test_simulator import contract,bar,quote


class Revision3Tests(unittest.TestCase):
    def setUp(self): self.ledger=Ledger(':memory:')
    def tearDown(self): self.ledger.close()
    def engine(self,contracts=None):
        return Engine(self.ledger,'r3',contracts or {'TEST':contract()},hypothesis=Hypothesis(lookback=2),synthetic=True)
    def signal(self,e):
        for b in (bar(0,100),bar(1,100),bar(2,101,100.5,101)): e.apply(b)
    def margin(self,**kw):
        return dict(id='m1',kind='margin_update',contract='TEST',available_at='2026-01-01T00:03:02Z',
            effective_at='2026-01-02T00:00:00Z',valid_until='2026-02-01T00:00:00Z',
            initial_margin=200,maintenance_margin=180,currency='USD',verified=True,source='fixture bulletin')|kw

    def test_emergency_after_future_bulletin_is_applied_now(self):
        e=self.engine(); self.signal(e); e.apply(quote()); e.apply(self.margin())
        e.apply(self.margin(id='emergency',available_at='2026-01-01T00:03:03Z',
            effective_at='2026-01-01T00:03:03Z',initial_margin=600,maintenance_margin=550))
        self.assertEqual(e._margins('TEST',utc('2026-01-01T00:03:03Z'))[:2],(600,550))
        self.assertEqual(e._margins('TEST',utc('2026-01-02T00:00:00Z'))[:2],(200,180))
        self.assertEqual(e.apply(quote(at='2026-01-01T00:03:04Z'))['reason'],'maintenance_margin_breach')
        self.assertEqual(self.engine().state,e.state)

    def test_explicit_correction_of_future_bulletin_does_not_leak(self):
        e=self.engine(); e.apply(self.margin())
        e.apply(self.margin(id='m2',available_at='2026-01-01T00:03:03Z',supersedes='m1',
                           initial_margin=600,maintenance_margin=550))
        self.assertEqual(e._margins('TEST',utc('2026-01-01T00:03:04Z'))[:2],(100,80))
        self.assertEqual(e._margins('TEST',utc('2026-01-02T00:00:00Z'))[:2],(600,550))
        self.assertEqual([u['observation_sequence'] for u in e.state['margin_updates']['TEST']],[1,2])

    def test_correction_arrival_cannot_reprice_earlier_observations(self):
        e=self.engine(); self.signal(e); e.apply(quote())
        e.apply(self.margin(effective_at='2026-01-01T00:03:02Z'))
        e.apply(quote(at='2026-01-01T00:03:03Z'))
        before=self.ledger.db.execute("SELECT output FROM events WHERE id=?",('q2026-01-01T00:03:03Z',)).fetchone()[0]
        e.apply(self.margin(id='corrected',available_at='2026-01-01T00:03:04Z',
                           effective_at='2026-01-01T00:03:02Z',supersedes='m1',
                           initial_margin=600,maintenance_margin=550))
        self.assertEqual(e._margins('TEST',utc('2026-01-01T00:03:03Z'))[:2],(200,180))
        self.assertEqual(e._margins('TEST',utc('2026-01-01T00:03:04Z'))[:2],(600,550))
        after=self.ledger.db.execute("SELECT output FROM events WHERE id=?",('q2026-01-01T00:03:03Z',)).fetchone()[0]
        self.assertEqual(before,after)
        self.assertEqual(e.apply(quote(at='2026-01-01T00:03:05Z'))['reason'],'maintenance_margin_breach')

    def test_invalid_corrections_are_atomic(self):
        e=self.engine(); e.apply(self.margin())
        e.apply(self.margin(id='m2',available_at='2026-01-01T00:03:03Z',supersedes='m1'))
        before=json.dumps(e.state)
        for kw in ({},{'supersedes':'m1'},{'supersedes':'unknown'},
                   {'supersedes':'m2','effective_at':'2026-01-03T00:00:00Z'},
                   {'supersedes':'m2','source':False},{'supersedes':'m2','initial_margin':-1}):
            with self.assertRaises(ValueError):
                e.apply(self.margin(id='bad',available_at='2026-01-01T00:03:04Z',**kw))
            self.assertEqual(json.dumps(e.state),before)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM events WHERE id='bad'").fetchone()[0],0)

    def roll_contracts(self,**changes):
        old=contract(root='ROOT',exchange='CME',contract_id=1,contract_month='202601',last_trading_date='20260120')
        new=contract(root='ROOT',exchange='CME',contract_id=2,contract_month='202602',last_trading_date='20260220',
                     exit_before='2026-02-15T00:00:00Z')|changes
        return {'TEST':old,'NEXT':new}
    def roll(self,**kw):
        return dict(id='roll',kind='roll',contract='TEST',new_contract='NEXT',available_at='2026-01-01T00:03:01Z')|kw

    def test_unknown_same_missing_and_malformed_roll_rejected_atomically(self):
        e=self.engine(self.roll_contracts()); self.signal(e); before=json.dumps(e.state)
        for new in ('UNKNOWN','TEST',None,[],42):
            with self.assertRaises(ValueError): e.apply(self.roll(new_contract=new))
            self.assertEqual(json.dumps(e.state),before)
        event=self.roll(); del event['new_contract']
        with self.assertRaises(ValueError): e.apply(event)
        self.assertEqual(json.dumps(e.state),before)

    def test_inappropriate_successor_rejected_atomically(self):
        cases=[dict(root='OTHER'),dict(exchange='COMEX'),dict(multiplier=10),dict(currency='EUR'),
               dict(contract_id=1),dict(contract_month='202501'),dict(last_trading_date='20250120'),
               dict(contract_month='202613'),dict(spec_verified=False),dict(exit_before='2025-01-01T00:00:00Z')]
        for i,changes in enumerate(cases):
            e=Engine(self.ledger,str(i),self.roll_contracts(**changes),hypothesis=Hypothesis(lookback=2),synthetic=True)
            self.signal(e); before=json.dumps(e.state)
            with self.assertRaises(ValueError): e.apply(self.roll())
            self.assertEqual(json.dumps(e.state),before)

    def test_known_same_product_later_expiry_roll_clears_old_history(self):
        e=self.engine(self.roll_contracts()); self.signal(e)
        self.assertEqual(e.apply(self.roll())['status'],'roll_boundary')
        self.assertNotIn('TEST',e.state['pending']); self.assertNotIn('TEST',e.state['bars'])
        self.assertEqual(e.state['cash'],500)

    def test_valid_successor_cannot_roll_with_open_position(self):
        e=self.engine(self.roll_contracts()); self.signal(e); e.apply(quote()); before=json.dumps(e.state)
        with self.assertRaises(ValueError): e.apply(self.roll(available_at='2026-01-01T00:03:02Z'))
        self.assertEqual(json.dumps(e.state),before)


if __name__=='__main__': unittest.main()
