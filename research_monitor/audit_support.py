"""Explicit clock scenarios and conservative observed adverse-excursion diagnostics."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

def clock_epoch(raw,scenario):
 if isinstance(scenario,int):return raw-scenario*3600
 if scenario=='api_utc':return raw
 if scenario in ('fixed2','fixed3'):return raw-int(scenario[-1])*3600
 if scenario=='ny_dst_inferred':
  candidates=[raw-h*3600 for h in [2,3] if bool(datetime.fromtimestamp(raw-h*3600,timezone.utc).astimezone(ZoneInfo('America/New_York')).dst())==(h==3)]
  if len(candidates)!=1:raise ValueError('Ambiguous broker DST conversion; do not silently guess')
  return candidates[0]
 raise ValueError('Unknown preregistered clock scenario')

def adverse_equity(cash,p,bar,spread,slip,mult,commission):
 side=p['side'];q=spread if side==-1 else 0;op=bar['open']+q
 if (op<=p['stop'] if side==1 else op>=p['stop']):price=op
 elif bar['t']>=p['expiry']:price=op
 elif (op>=p['target'] if side==1 else op<=p['target']):price=p['target']
 else:price=max(bar['low']+q,p['stop']) if side==1 else min(bar['high']+q,p['stop'])
 return cash+((price-side*slip-p['entry'])*side*mult-commission)*p['quantity']
