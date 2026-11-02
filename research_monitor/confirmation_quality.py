"""Two existing causal candle-quality thresholds, fixed before the 60% study."""
VARIANTS=('control','strong_close','efficient','both')


def reject_confirmation(name,signal):
    if name not in VARIANTS:raise ValueError('Unregistered confirmation rule')
    if name in ('strong_close','both') and not signal.get('strong_close'):
        return 'signal_close_not_in_outer_35pct'
    if name in ('efficient','both') and signal.get('features',{}).get('directional_efficiency',-1)<.3:
        return 'prior20_directional_efficiency_below_030'
    return None
