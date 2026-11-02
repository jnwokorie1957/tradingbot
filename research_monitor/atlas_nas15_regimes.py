"""Fixed, causal direction/regime hypotheses; no risk or exit changes."""
from collections import deque
from copy import deepcopy
from .native_data import aggregate

PROFILES = ('control', 'add_short', 'confirmed_short', 'h4_long', 'h4_both')


def h4_context(one, plans):
    states = []
    ema = None
    history = deque(maxlen=4)
    for count, bar in enumerate(aggregate(one, 240), 1):
        ema = bar['close'] if ema is None else ema + 2 / 21 * (bar['close'] - ema)
        history.append(ema)
        states.append(dict(end=bar['t'] + 14400, close=bar['close'], ema20=ema,
                           slope=ema-history[0] if len(history)==4 else None,
                           count=count))
    out, index, last = {}, 0, None
    for t, signal in sorted(plans.items()):
        while index < len(states) and states[index]['end'] <= t:
            last = states[index]
            index += 1
        s = deepcopy(signal)
        if last:
            s.setdefault('features', {})['h4_utc'] = dict(last, available=(last['count']>=20 and last['slope'] is not None and t-last['end']<=14400))
        out[t] = s
    return out


def h4_pass(signal):
    h = signal.get('features', {}).get('h4_utc')
    side = signal['side']
    return bool(h and h['available'] and side*(h['close']-h['ema20'])>0 and
                side*(signal['reference']-h['ema20'])>0 and side*h['slope']>0)


def make_variants(base, one):
    nas = h4_context(one['NAS100'], base['NAS15']['signals'])
    out = {}
    for name in PROFILES:
        lanes = deepcopy(base)
        if name in ('add_short', 'confirmed_short', 'h4_both'):
            lanes['NAS15']['direction'] = 'all'
        if name == 'confirmed_short':
            lanes['NAS15']['signals'] = {t:s for t,s in nas.items() if s['side']==1 or
                                         (s.get('strong_close') and s.get('features',{}).get('directional_efficiency',-1)>=.30)}
        elif name in ('h4_long', 'h4_both'):
            lanes['NAS15']['signals'] = {t:s for t,s in nas.items() if h4_pass(s)}
        out[name] = lanes
    return out
