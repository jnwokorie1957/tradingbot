"""Non-executing risk preflight for the separately authorized research profile.

This does not replace engine admission, create claims, or activate a runner.
Existing engine policies and their serialized identities remain unchanged.
"""
from decimal import Decimal, InvalidOperation

PROFILE = 'research-5000-v1'

def amount(value):
    if isinstance(value, bool):
        raise ValueError('numeric amount required')
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('numeric amount required') from None
    if not number.is_finite() or number < 0:
        raise ValueError('nonnegative finite amount required')
    return number

def preflight(profile_id, equity, stop_risk, costs, open_risk, quantity=1,
              lower_cap=None):
    """Amounts are total USD across quantity; costs include every applicable cost.

    A passing result is only arithmetic feasibility, never execution permission.
    Unknown inputs raise; callers must skip rather than substitute zero costs.
    """
    if profile_id != PROFILE:
        raise ValueError('unrelated profile; use its existing policy')
    if type(quantity) is not int or quantity < 1:
        raise ValueError('positive whole tradable quantity required')
    e, stop, fee, opened = map(amount, (equity, stop_risk, costs, open_risk))
    if e <= 0 or stop <= 0:
        raise ValueError('positive equity and structural stop risk required')
    cap = min(e * Decimal('.005'), Decimal('25'))
    if lower_cap is not None:
        cap = min(cap, amount(lower_cap))
    total = stop + fee
    reasons = []
    if total > cap:
        reasons.append('all_in_trade_risk')
    if opened + total > e * Decimal('.01'):
        reasons.append('open_portfolio_risk')
    return dict(arithmetic_pass=not reasons, reasons=reasons,
                all_in_risk=str(total), trade_cap=str(cap),
                execution_authorized=False)
