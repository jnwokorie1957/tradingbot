"""Three frozen entry hypotheses. No feature uses prices after the signal decision."""
from collections import deque
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
NY=ZoneInfo('America/New_York')
HYPOTHESES=('baseline','trend_efficiency','prior_session_room','opening_gap')

def enrich(native,one,signals):
 days={}
 for b in one:
  at=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY);clock=at.hour*60+at.minute
  if 570<=clock<960:days.setdefault(str(at.date()),[]).append(b)
 dates=sorted(days);previous={d:dates[i-1] if i else None for i,d in enumerate(dates)}
 prior=deque(maxlen=20);out={k:dict(v) for k,v in signals.items()}
 for b in native:
  end=b['t']+900
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

def reject(name,signal,entry,distance,rr):
 if name not in HYPOTHESES:raise ValueError('Unregistered entry hypothesis')
 f=signal.get('features',{})
 if name=='trend_efficiency' and f.get('directional_efficiency',-1)<.30:return 'efficiency_below_030'
 if name=='prior_session_room':
  key='prior_high' if signal['side']==1 else 'prior_low'
  if key not in f:return 'prior_complete_session_unavailable'
  room=signal['side']*(f[key]-entry)
  if 0<room<rr*distance:return 'prior_boundary_inside_target'
 if name=='opening_gap':
  if not {'prior_close','session_open'}<=f.keys() or not signal.get('atr14'):return 'gap_context_unavailable'
  if abs(f['session_open']-f['prior_close'])>2*signal['atr14']:return 'opening_gap_above_2ATR'
 return None
