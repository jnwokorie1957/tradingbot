"""Synthetic fixtures only. Prices are invented and are not market observations."""
from datetime import datetime,timedelta

def create(summer=False):
    day,prior,offset=('2026-07-14','2026-07-13',4) if summer else ('2026-01-06','2026-01-05',5)
    close=datetime.fromisoformat(day+f'T{16+offset}:00:00+00:00');decision=close-timedelta(minutes=30)
    session=dict(contract='TEST',calendar_verified=True,source_reference='SYNTHETIC TEST CALENDAR',
        available_at=prior+'T00:00:00Z',open=day+f'T{9+offset}:30:00Z',close=close.isoformat(),previous_close=prior+f'T{16+offset}:00:00Z')
    c=dict(root='TEST',contract_id=1,contract_month='202612',last_trading_date='20261218',exchange='SYNTHETIC',currency='USD',
        multiplier=1,tick=.25,initial_margin=100,maintenance_margin=80,fee_per_side=.1,daily_carry_fee=0,
        spec_verified=True,permission_verified=True,costs_verified=True,data_verified=True,evidence_source='SYNTHETIC SOFTWARE FIXTURE',
        valid_from='2026-01-01T00:00:00Z',valid_until='2027-01-01T00:00:00Z',exit_before='2026-12-01T00:00:00Z',requires_adjustment=False)
    def bar(end,price,identity):
        return dict(id=identity,kind='bar',contract='TEST',start=(end-timedelta(minutes=5)).isoformat(),end=end.isoformat(),
            available_at=end.isoformat(),open=price,high=price+.5,low=price-.5,close=price,volume=10,quality='verified',bar_kind='TRADES')
    events=[bar(datetime.fromisoformat(session['previous_close'].replace('Z','+00:00')),100,'prior-close')]
    events += [bar(decision-timedelta(minutes=5*(20-i)),101,f'warmup-{i}') for i in range(21)]
    events += [dict(id='decision',kind='decision',contract='TEST',session_id='session',available_at=decision.isoformat()),
        quote(decision+timedelta(seconds=1),'entry'),dict(id='close-clock',kind='clock',contract='TEST',available_at=close.isoformat()),
        quote(close+timedelta(seconds=1),'exit')]
    return dict(synthetic=True,contracts={'TEST':c},sessions={'session':session},events=events)

def quote(at,identity,bid=101,ask=101.25,quote_at=None):
    return dict(id=identity,kind='quote',contract='TEST',available_at=at.isoformat(),quote_at=(quote_at or at).isoformat(),
        bid=bid,ask=ask,bid_size=1,ask_size=1,quality='verified')
