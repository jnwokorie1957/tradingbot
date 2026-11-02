"""Two literature-motivated hypotheses, fixed before financial screening.

CFD adaptations, not reproductions of exchange-volume/auction studies.
Only current completed bars and already completed prior sessions are eligible.
"""
from collections import Counter
from datetime import datetime,timezone,timedelta
from statistics import median
from atlas_exit_research.data import NY
from short_horizon_research.signals import HOLIDAYS,EARLY_CLOSE

SOURCES={'late_momentum':'https://doi.org/10.1016/j.jfineco.2018.05.009','gap_reversal':'https://doi.org/10.1016/j.jbankfin.2004.04.006'}
RULES={'late_momentum':'5m decision15:30NY. Sign of prior RTH close to10:00 return must agree with15:00–15:30 return. Complete30min blocks required. Entry first observed quote >=decision+1s; stop preceding complete5min extreme plus1tick;2R;time exit15:59. Early closes excluded.', 'gap_reversal':'1m decision09:40–10:00NY: opening gap >=20bp versus prior completedRTHclose. First completed1m reversal after first10min, requiring opposite candle and close-to-close direction while gap remains unfilled. Entry >=decision+1s; stop observed opening range extreme plus1tick;1.5R;expiry<=60min and11:00. One first-confirmation event per opening gap,not a daily trade quota.'}


def generate(one,tick):
    groups={}
    for bar in one:
        at=datetime.fromtimestamp(bar['t'],timezone.utc).astimezone(NY);slot=at.hour*60+at.minute
        if 570<=slot<EARLY_CLOSE.get(at.date().isoformat(),960):groups.setdefault(at.date().isoformat(),{})[slot]=bar
    out={n:{} for n in RULES};prior=None;prior_day=None;past_ranges=[];quality=Counter()
    for day,bars in sorted(groups.items()):
        dt=datetime.fromisoformat(day).replace(tzinfo=NY);close=EARLY_CLOSE.get(day,960)
        if dt.weekday()>4 or day in HOLIDAYS:continue
        if prior_day:
            cursor=datetime.fromisoformat(prior_day)+timedelta(days=1)
            while cursor.date().isoformat()<day:
                if cursor.weekday()<5 and cursor.date().isoformat()not in HOLIDAYS:prior=None;past_ranges=[]
                cursor+=timedelta(days=1)
        def block(a,b):return [bars[x] for x in range(a,b)] if all(x in bars for x in range(a,b)) else None
        def emit(family,when,side,stop,ref,deadline,vol):
            regime='unknown' if len(past_ranges)<20 else 'high_prior_relative_range' if vol>median(past_ranges[-20:]) else 'low_prior_relative_range'
            out[family][when]=dict(decision=when,entry_at=when+1,side=side,stop=stop,reference=ref,deadline=deadline,expiry_at=min(when+3600,deadline),features={'preentry_regime':regime,'observed_range_fraction':vol},trend_aligned=True)
        if prior is not None:
            opening=block(570,600);late=block(900,930);last5=block(925,930)
            if close==960 and opening and late and last5:
                first=opening[-1]['close']/prior-1;second=late[-1]['close']/late[0]['open']-1
                if first*second>0:
                    side=1 if first>0 else -1;stop=min(b['low'] for b in last5)-tick if side==1 else max(b['high'] for b in last5)+tick;when=late[-1]['t']+60;deadline=dt.replace(hour=15,minute=59).timestamp();emit('late_momentum',when,side,stop,late[-1]['close'],deadline,(max(b['high'] for b in late)-min(b['low'] for b in late))/prior)
            else:quality['late_context_or_session_unavailable']+=1
            first10=block(570,580)
            if first10:
                gap=first10[0]['open']/prior-1
                if abs(gap)>=.002:
                    side=-1 if gap>0 else 1
                    for end in range(580,601):
                        observed=block(570,end);b=bars.get(end-1);prev=bars.get(end-2)
                        if not observed or not b or not prev:continue
                        if side*(b['close']-b['open'])>0 and side*(b['close']-prev['close'])>0 and side*(prior-b['close'])>0:
                            stop=min(x['low'] for x in observed)-tick if side==1 else max(x['high'] for x in observed)+tick;when=b['t']+60;emit('gap_reversal',when,side,stop,b['close'],dt.replace(hour=11,minute=0).timestamp(),(max(x['high'] for x in observed)-min(x['low'] for x in observed))/prior);break
            else:quality['gap_context_unavailable']+=1
        else:quality['previous_complete_session_unavailable']+=1
        # This is used on the NEXT session only; no current-session eligibility
        # check depends on future coverage or future high/low/close.
        if set(bars)==set(range(570,close)):
            prior=bars[close-1]['close'];past_ranges.append((max(b['high'] for b in bars.values())-min(b['low'] for b in bars.values()))/bars[570]['open'])
        else:prior=None;past_ranges=[];quality['incomplete_prior_session_for_next_day']+=1
        prior_day=day
    return out,dict(quality)
