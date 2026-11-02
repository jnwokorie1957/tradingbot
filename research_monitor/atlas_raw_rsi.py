"""Causal RSI-2 rule reproduced from the repository diagnostic, with explicit exits."""
import math
from collections import deque
from datetime import datetime,timezone
from .audited_run import NY


def rsi_series(closes):
    out=[None]*len(closes);gains=[];losses=[];g=l=None
    for i in range(1,len(closes)):
        change=closes[i]-closes[i-1];gain=max(change,0);loss=max(-change,0)
        if i<=2:gains.append(gain);losses.append(loss)
        if i==2:g=sum(gains)/2;l=sum(losses)/2
        elif i>2:g=(g+gain)/2;l=(l+loss)/2
        else:continue
        out[i]=50. if g==0 and l==0 else 100. if l==0 else 100-100/(1+g/l)
    return out


def rsi_signals(native,minutes,start_clock=0,end_clock=1439):
    rsis=rsi_series([b['close'] for b in native]);out={};exits=[];closes=deque(maxlen=200);previous=None;atr=None;trs=[];ema=None;ema_history=deque(maxlen=6)
    for i,b in enumerate(native):
        end=b['t']+minutes*60;at=datetime.fromtimestamp(end,timezone.utc).astimezone(NY);clock=at.hour*60+at.minute
        closes.append(b['close']);tr=max(b['high']-b['low'],abs(b['high']-previous),abs(b['low']-previous)) if previous is not None else b['high']-b['low'];previous=b['close'];trs.append(tr)
        if len(trs)==14:atr=sum(trs)/14
        elif len(trs)>14:atr=(atr*13+tr)/14
        ema=b['close'] if ema is None else ema+2/51*(b['close']-ema);ema_history.append(ema)
        r=rsis[i]
        if r is not None:
            if r>75:exits.append((end+60,1))
            if r<25:exits.append((end+60,-1))
        if i<199 or not start_clock<=clock<=end_clock or atr is None:continue
        a,c,d=rsis[i-2:i+1];sma=sum(closes)/200
        side=1 if b['close']>sma and a<65 and a>c>d else -1 if b['close']<sma and a>35 and a<c<d else 0
        if not side:continue
        entry=end+60;step=minutes*60;first_full=math.ceil(entry/step)*step;deadline=at.replace(hour=15,minute=55,second=0,microsecond=0).astimezone(timezone.utc).timestamp()
        trend=(side*(b['close']-ema)>0 and len(ema_history)==6 and side*(ema-ema_history[0])>0)
        width=b['high']-b['low'];location=(b['close']-b['low'])/width if width else .5
        out[end]=dict(side=side,reference=b['close'],decision=end,entry_at=entry,stop_distance=atr,atr14=atr,trend_aligned=trend,strong_close=(location>=.65 if side==1 else location<=.35),deadline=deadline,expiry_at=min(deadline,first_full+12*step+60))
    return out,sorted(exits)
