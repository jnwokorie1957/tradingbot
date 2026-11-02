"""Same causal breakout generator with predefined entry-window starts."""
from collections import deque
from datetime import datetime,timezone
from .audited_run import NY,iso
from trading_pipeline.engine_v4 import Engine,Hypothesis,Policy

def signals(native,symbol,minutes,lookback,filter_,end_clock=720,family=None,start_clock=600):
    engine=object.__new__(Engine);engine.state={'bars':{},'pending':{},'positions':{}}
    engine.hypothesis=Hypothesis(family=family or ('pullback' if symbol=='NAS100' else 'breakout'),lookback=lookback)
    engine.policy=Policy();out={};ema=None;history=deque(maxlen=6);previous=None;atr=None;true_ranges=[]
    for b in native:
        end=b['t']+minutes*60;at=datetime.fromtimestamp(end,timezone.utc);local=at.astimezone(NY)
        ema=b['close'] if ema is None else ema+(2/51)*(b['close']-ema);history.append(ema)
        tr=max(b['high']-b['low'],abs(b['high']-previous),abs(b['low']-previous)) if previous is not None else b['high']-b['low']
        previous=b['close'];true_ranges.append(tr)
        if len(true_ranges)==14:atr=sum(true_ranges)/14
        elif len(true_ranges)>14:atr=(13*atr+tr)/14
        e=dict(contract=symbol,start=iso(b['t']),end=iso(end),available_at=iso(end),**{k:b[k] for k in ('open','high','low','close','volume')})
        result=Engine._bar(engine,e,at,{})
        side=result['side'];clock=local.hour*60+local.minute
        trend=(side==1 and b['close']>ema and len(history)==6 and ema>history[0]) or (side==-1 and b['close']<ema and len(history)==6 and ema<history[0])
        width=b['high']-b['low'];location=(b['close']-b['low'])/width if width else .5
        strong=(side==1 and location>=.65) or (side==-1 and location<=.35)
        passes={'none':True,'ema50':trend,'close65':strong,'long_only':side==1,'close65_long':strong and side==1,
            'short_only':side==-1,'max_stop_atr':True,'short_range':side==-1}.get(filter_)
        if passes is None:raise ValueError('Unknown preregistered entry filter')
        if side and start_clock<=clock<=end_clock and passes:
            out[end]=dict(side=side,stop=b['low'] if side==1 else b['high'],reference=b['close'],decision=end,entry_at=end+60,atr14=atr,trend_aligned=trend,strong_close=strong)
    return out
