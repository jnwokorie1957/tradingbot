"""Strict IBKR OHLCV intake. Raw records retained separately, never repaired."""
from datetime import timedelta
from simulator import utc, finite


def unwrap(response):
    import json
    if 'structuredContent' in response:
        return response['structuredContent']
    return json.loads(next(c['text'] for c in response['content'] if c['type']=='text'))


def inspect_history(history, as_of, timestamp_semantics='unknown'):
    data = unwrap(history) if 'content' in history else history
    result = dict(raw_count=len(data.get('time',[])),accepted=[],quarantined=[],
                  execution_eligible=False,timestamp_semantics=timestamp_semantics,
                  notes=['Trade bars are not executable bid/ask quotes. Exchange session calendar has not been validated.'])
    keys = ('time','open','high','low','close','volume')
    step=data.get('chart_step')
    try:
        finite(step)
        if step not in (30,60,120,300,600,900,1800,3600,7200,14400,86400,604800):
            raise ValueError('unsupported fixed bar duration')
    except (ValueError,TypeError):
        result['error']='invalid_or_unsupported_chart_step'
        result['quarantined']=[dict(index=i,time=t,reasons=['invalid_or_unsupported_chart_step']) for i,t in enumerate(data.get('time',[]))]
        return result
    if not all(isinstance(data.get(k),list) for k in keys) or len({len(data[k]) for k in keys}) != 1:
        result['error']='missing_or_misaligned_arrays'
        return result
    previous = None
    for i,t in enumerate(data['time']):
        reasons=[]
        try:
            stamp=utc(t)
            finite(*(data[k][i] for k in keys[1:]))
            o,h,l,c,v=(data[k][i] for k in keys[1:])
            if not l <= min(o,c) <= max(o,c) <= h: reasons.append('ohlc_bounds')
            if v <= 0: reasons.append('nonpositive_volume')
            if previous and stamp <= previous: reasons.append('nonmonotonic_timestamp')
            previous=stamp
            if timestamp_semantics != 'bar_start': reasons.append('unverified_timestamp_semantics')
            if stamp+timedelta(seconds=data['chart_step']) > utc(as_of): reasons.append('incomplete_bar')
            if stamp.minute != 0 and data['chart_step']==3600: reasons.append('irregular_hour_boundary')
        except (ValueError,KeyError,TypeError) as exc:
            reasons.append('invalid_record:'+str(exc))
        if reasons: result['quarantined'].append(dict(index=i,time=t,reasons=reasons))
        else: result['accepted'].append(i)
    return result
