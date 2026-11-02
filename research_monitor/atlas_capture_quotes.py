"""Keep every quote on any feasible position path; omit only guaranteed idle spans."""
from datetime import datetime,timezone
import numpy as np
from .audited_run import NY,up,down


def feasible_envelopes(sessions,signals,meta,stress,start_clock,end_clock,direction='all',exit_delay=0.):
    lengths=[len(q) for _,q,_ in sessions];ends=np.cumsum(lengths);total=int(ends[-1]) if len(ends) else 0
    if not total:return sessions,dict(raw_quotes=0,kept_quotes=0,envelopes=0)
    times=np.concatenate([q['time_msc'].astype(float)/1000-offset*3600 for _,q,offset in sessions]);assert np.all(np.diff(times)>=0)
    tick=meta['trade_tick_size'];mult=meta['trade_tick_value_loss']/tick;slip=tick*(2 if stress else 1);fee=12. if stress else 6.;intervals=[]
    for _,s in sorted(signals.items()):
        side=s['side']
        if direction=='long_only' and side!=1 or direction=='short_only' and side!=-1:continue
        i=int(np.searchsorted(times,s['entry_at']))
        if i>=total:continue
        local=datetime.fromtimestamp(times[i],timezone.utc).astimezone(NY);clock=local.hour*60+local.minute
        if not start_clock<=clock<=end_clock:continue
        intervals.append((i,i+1))
        decision_i=int(np.searchsorted(times,s['decision']))
        if decision_i<total:intervals.append((decision_i,decision_i+1))
        if times[i]-s['entry_at']>5:continue
        block=int(np.searchsorted(ends,i,side='right'));offset_in_block=i-(int(ends[block-1]) if block else 0);q=sessions[block][1][offset_in_block]
        bid=float(q['bid']);ask=float(q['ask']);ask=bid+(ask-bid)*(1.5 if stress else 1.)
        entry=(ask if side==1 else bid)+side*slip
        if 'stop_distance' in s:distance=up(s['stop_distance'],tick);stop=entry-side*distance
        else:stop=down(s['stop'],tick) if side==1 else up(s['stop'],tick);distance=side*(entry-stop)
        if distance<tick-1e-8 or (bid<=stop if side==1 else ask>=stop):continue
        if ((distance+slip)*mult+fee)*meta['volume_min']>25+1e-8:continue
        expiry=min(s.get('expiry_at',times[i]+3600),s.get('deadline',float('inf')))
        edge=int(np.searchsorted(times,expiry))
        if edge<total and exit_delay>0:edge=int(np.searchsorted(times,times[edge]+exit_delay))
        j=min(edge+1,total)
        intervals.append((i,max(j,i+1)))
    merged=[]
    for lo,hi in sorted(intervals):
        if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
        else:merged.append((lo,hi))
    kept=[];begin=0;cursor=0
    for day,q,offset in sessions:
        finish=begin+len(q);pieces=[]
        while cursor<len(merged) and merged[cursor][1]<=begin:cursor+=1
        k=cursor
        while k<len(merged) and merged[k][0]<finish:
            lo=max(begin,merged[k][0])-begin;hi=min(finish,merged[k][1])-begin
            if lo<hi:pieces.append(q[lo:hi])
            k+=1
        subset=np.concatenate(pieces) if len(pieces)>1 else pieces[0] if pieces else q[:0]
        kept.append((day,subset,offset));begin=finish
    return kept,dict(raw_quotes=total,kept_quotes=sum(len(q) for _,q,_ in kept),envelopes=len(intervals),method='Outcome-independent maximum25USD feasibility and scheduled-expiry envelopes; all possible intratrade quotes retained; no profit/stop/target outcomes used for pruning.')
