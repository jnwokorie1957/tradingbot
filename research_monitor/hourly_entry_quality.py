"""Exactly the two entry rules proposed before the eight-case comparison."""
from collections import deque
import math

VARIANTS=('control','completed_hour_trend','no_chase','both')


def complete_hours(one):
    buckets={};previous=None
    for b in one:
        if previous is not None and b['t']<=previous:
            raise ValueError('Minute candles must be chronological and unique')
        previous=b['t'];buckets.setdefault(b['t']//3600*3600,[]).append(b)
    out=[]
    for t,rows in sorted(buckets.items()):
        if len(rows)!=60 or [b['t'] for b in rows]!=list(range(t,t+3600,60)):
            continue
        out.append(dict(t=t,end=t+3600,open=rows[0]['open'],high=max(b['high'] for b in rows),
                        low=min(b['low'] for b in rows),close=rows[-1]['close'],
                        volume=sum(b['volume'] for b in rows)))
    return out


def attach_hourly(signals,one):
    states=[];ema=None;history=deque(maxlen=4)
    for count,b in enumerate(complete_hours(one),1):
        ema=b['close'] if ema is None else ema+(2/21)*(b['close']-ema)
        history.append(ema)
        states.append(dict(end=b['end'],close=b['close'],ema20=ema,count=count,
                           slope=ema-history[0] if len(history)==4 else None))
    index=0;last=None;out={}
    for t,s in sorted(signals.items()):
        while index<len(states) and states[index]['end']<=t:
            last=states[index];index+=1
        result=dict(s);result['features']=dict(s.get('features',{}))
        if last is not None:
            result['features']['hourly']=dict(last,available=(last['count']>=20 and t-last['end']<=3600 and last['slope'] is not None))
        out[t]=result
    return out


def reject_quality(variant,signal,entry):
    if variant not in VARIANTS:raise ValueError('Unregistered entry-quality variant')
    if variant in ('completed_hour_trend','both'):
        h=signal.get('features',{}).get('hourly')
        if not h or not h['available']:return 'hourly_context_unavailable'
        side=signal['side']
        if not (side*(h['close']-h['ema20'])>0 and side*(signal['reference']-h['ema20'])>0 and side*h['slope']>0):
            return 'hourly_trend_not_aligned'
    if variant in ('no_chase','both'):
        atr=signal.get('atr14')
        if atr is None or not math.isfinite(atr) or atr<=0:return 'signal_ATR_unavailable'
        if signal['side']*(entry-signal['reference'])>.25*atr+1e-12:return 'entry_extended_beyond_quarter_ATR'
    return None
