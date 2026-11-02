"""Development-motivated structural confirmations; thresholds fixed before v2 replay."""
from collections import deque
from datetime import datetime,timezone
from .entry_quality import enrich as context,NY
HYPOTHESES=('baseline','beyond_prior_session','opening_range30','retest15')

def enrich(native,one,signals,hypothesis='baseline'):
 if hypothesis not in HYPOTHESES:raise ValueError('Unregistered v2 hypothesis')
 out=context(native,one,signals);prior=deque(maxlen=20);previous_end=None
 for b in native:
  end=b['t']+900
  if previous_end is not None and b['t']-previous_end>7200:prior.clear()
  if end in out and len(prior)==20:
   side=out[end]['side'];out[end]['features']['breakout_level']=max(p['high'] for p in prior) if side==1 else min(p['low'] for p in prior)
  prior.append(b);previous_end=end
 # Opening range is fixed09:30–10:00NY, published only once the30th minute completes.
 ranges={}
 for b in one:
  at=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY);clock=at.hour*60+at.minute
  if 570<=clock<600:ranges.setdefault(str(at.date()),[]).append(b)
 for end,s in out.items():
  day=str(datetime.fromtimestamp(end,timezone.utc).astimezone(NY).date());r=ranges.get(day,[])
  if len(r)==30 and r[-1]['t']+60<=end:s['features'].update(opening_high=max(p['high'] for p in r),opening_low=min(p['low'] for p in r))
 if hypothesis!='retest15':return out
 return confirm_retests(one,out)

def confirm_retests(one,impulses):
 active=None;plans={}
 for b in one:
  t=b['t'];now=t+60
  if active:
   side=active['side'];level=active['features'].get('breakout_level')
   if t>=active['decision']+900 or level is None or (b['low']<=active['stop'] if side==1 else b['high']>=active['stop']):active=None
   elif t>=active['decision'] and (b['low']<=level<b['close'] if side==1 else b['high']>=level>b['close']):
    s=dict(active,impulse_decision=active['decision'],decision=now,entry_at=now+60,reference=b['close']);plans[now]=s;active=None
  # A new completed signal supersedes an older unconfirmed setup; it cannot use its own minute retrospectively.
  if now in impulses:active=dict(impulses[now])
 return plans

def reject(name,signal,entry,distance,rr):
 if name not in HYPOTHESES:raise ValueError('Unknown v2 entry hypothesis')
 f=signal.get('features',{});side=signal['side']
 if name=='beyond_prior_session':
  key='prior_high' if side==1 else 'prior_low'
  if key not in f:return 'prior_session_unavailable'
  if side*(signal['reference']-f[key])<=0 or side*(entry-f[key])<=0:return 'still_inside_prior_session'
 if name=='opening_range30':
  key='opening_high' if side==1 else 'opening_low'
  if key not in f:return 'opening_range_not_complete'
  if side*(signal['reference']-f[key])<=0 or side*(entry-f[key])<=0:return 'inside_opening_range'
 if name=='retest15' and ('breakout_level' not in f or side*(entry-f['breakout_level'])<=0):return 'retest_entry_back_inside_level'
 return None
