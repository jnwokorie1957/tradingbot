"""Risk monotonicity and causal-prefix checks for the isolated offline overlay."""
from datetime import date, timedelta

from .variance_budget import capped
from .variance_preflight import features


def main():
    base = dict(quantity=2.5, perlot=10., lane_budget=25., minimum_legal_risk=10.,
                total_budget=50., used_risk=20., margin_perlot=100., reasons=[])
    reduced = capped(base, .5, .1, 1.)
    assert abs(reduced['quantity'] - 1.2) < 1e-9 and reduced['lane_budget'] == 12.5
    assert capped(base, None, .1, 1.) is base
    assert capped(base, 1., .1, 1.)['quantity'] == base['quantity']
    blocked = capped(base, .2, .1, 1.)
    assert blocked['quantity'] < 1 and 'variance_budget_below_legal_minimum' in blocked['reasons']
    assert base['reasons'] == [] and base['quantity'] == 2.5
    limited = dict(base, quantity=.7, used_risk=43., reasons=['daily_2pct_loss_pause'])
    row = capped(limited, .9, .1, .1)
    assert row['quantity'] == .7 and row['used_risk'] == 43. and row['total_budget'] == 50.
    assert row['reasons'] == limited['reasons'] and row['quantity'] * row['perlot'] <= 7.
    equity_limited = dict(base, lane_budget=20., quantity=2.)
    assert capped(equity_limited, .5, .1, .1)['lane_budget'] == 10.
    rejected = 0
    for scale in [0., -1., 1.01]:
        try:
            capped(base, scale, .1, 1.)
        except AssertionError:
            rejected += 1
    assert rejected == 3
    days, current = [], date(2026, 1, 1)
    while len(days) < 63:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    variances = {d: 1. for d in days[:60]}
    variances[days[60]] = 4.
    original = features(variances, [days[61]])[0]
    assert original['scale'] == .25  # Inverse variance, not inverse volatility.
    variances[days[61]] = 1e20
    variances[days[62]] = 1e-20
    assert features(variances, [days[61]])[0] == original
    assert features({}, [days[61]])[0]['status'] == 'previous_reference_window_incomplete_or_absent'
    print('{"synthetic_checks":10,"all_pass":true,"financial_cases":0}')


if __name__ == '__main__':
    main()
