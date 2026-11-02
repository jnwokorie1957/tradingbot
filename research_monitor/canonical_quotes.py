"""Quote-derived bid candles; no interpolation or use of forming intervals."""
import numpy as np

def minute_bars(quotes,completed_before,point=.1):
 if not len(quotes):return []
 if np.any(np.diff(quotes['time_msc'])<0):raise ValueError('Unordered quote stream')
 mins=quotes['time_msc']//60000*60;starts=np.r_[0,np.flatnonzero(np.diff(mins))+1];ends=np.r_[starts[1:],len(quotes)];out=[]
 for a,b in zip(starts,ends):
  t=int(mins[a])
  if t+60>completed_before:continue
  q=quotes[a:b];bid=q['bid']
  out.append(dict(t=t,open=float(bid[0]),high=float(bid.max()),low=float(bid.min()),close=float(bid[-1]),volume=len(q),spread=float(np.min(q['ask']-q['bid']))/point))
 return out

def fifteen_bars(one):
 buckets={}
 for b in one:buckets.setdefault(b['t']//900*900,[]).append(b)
 out=[]
 for t,rows in sorted(buckets.items()):
  if len(rows)!=15 or [b['t'] for b in rows]!=list(range(t,t+900,60)):continue
  out.append(dict(t=t,open=rows[0]['open'],high=max(b['high'] for b in rows),low=min(b['low'] for b in rows),close=rows[-1]['close'],volume=sum(b['volume'] for b in rows),spread=min(b['spread'] for b in rows)))
 return out
