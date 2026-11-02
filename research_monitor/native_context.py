"""Same pre-entry session context with explicit native candle duration."""
from collections import deque
from datetime import datetime,timezone
from .audited_run import NY

def enrich_native(native,one,signals,minutes):
 days={}
 for b in one:
  at=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY);clock=at.hour*60+at.minute
  if 570<=clock<960:days.setdefault(str(at.date()),[]).append(b)
 dates=sorted(days);previous={d:dates[i-1] if i else None for i,d in enumerate(dates)}
 prior=deque(maxlen=20);out={k:dict(v) for k,v in signals.items()}
 for b in native:
  end=b['t']+minutes*60
  if end in out:
   s=out[end];day=str(datetime.fromtimestamp(end,timezone.utc).astimezone(NY).date());features={}
   if len(prior)==20:
    values=[r['close'] for r in prior];path=sum(abs(y-x) for x,y in zip(values,values[1:]))
    features['directional_efficiency']=s['side']*(values[-1]-values[0])/path if path else 0.
   yesterday=days.get(previous.get(day),[])
   if len(yesterday)==390 and yesterday[-1]['t']+60<=end:
    features.update(prior_high=max(r['high'] for r in yesterday),prior_low=min(r['low'] for r in yesterday),prior_close=yesterday[-1]['close'])
   today=days.get(day,[])
   if today and today[0]['t']<=end:
    at=datetime.fromtimestamp(today[0]['t'],timezone.utc).astimezone(NY)
    if at.hour==9 and at.minute==30:features['session_open']=today[0]['open']
   s['features']=features
  prior.append(b)
 return out
