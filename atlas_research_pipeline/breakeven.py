"""One registered exit-only hypothesis. No broker/terminal/order transport."""
import numpy as np
from atlas_exit_research import engine
from atlas_exit_research.holding_pair import HoldingBook
from research_monitor.audited_run import up,down

ORIGINAL_PATH=engine.path
RULE='NAS15 only:after a received sourcequote reaches>=1initial price-distance R and at least1tick beyond cost-covered break-even,arm cost-covered stop from NEXT quote only. Keep2Rtarget,NAS90minute deadline,original entry,natural initialstop,initial grossriskreservation and all risklimits. SPX15 unchanged1.5R/60minutes.'


def protected_path(q,t,i,entry,stop,side,quantity,signal,lane,style,meta,cost,indicator_times,structure):
    if not lane.get('cost_covered_breakeven'):return ORIGINAL_PATH(q,t,i,entry,stop,side,quantity,signal,lane,style,meta,cost,indicator_times,structure)
    assert style=='fixed_2';tick=meta['trade_tick_size'];slip=tick*cost['slip_ticks'];mult=meta['trade_tick_value_loss']/tick;distance=side*(entry-stop);expiry=min(signal.get('expiry_at',t[i]+3600),signal.get('deadline',float('inf')));edge=int(np.searchsorted(t,expiry));end=min(len(t),edge+1);raw=q[i:end];ask=raw['bid']+(raw['ask']-raw['bid'])*cost['spread'];prices=np.asarray(raw['bid']if side==1 else ask);target=entry+side*down(2.*distance,tick)
    # Exit-side slip plus the roundtrip fee remain payable at the moved stop.
    cover=up(entry+slip+cost['fee']/mult,tick)if side==1 else down(entry-slip-cost['fee']/mult,tick);min_gap=max(tick,meta.get('trade_stops_level',0)*meta.get('point',tick));arm=(side*(prices-entry)>=distance-1e-9)&(side*(prices-cover)>=min_gap-1e-9);armed_before=np.r_[False,np.maximum.accumulate(arm)[:-1]];levels=np.where(armed_before,cover,stop);choices=[];hit=np.flatnonzero(prices<=levels if side==1 else prices>=levels)
    if len(hit):choices.append((int(hit[0]),0,'cost_covered_stop_quote'if armed_before[hit[0]]else'stop_quote'))
    if edge<len(t):choices.append((edge-i,1,'time_exit_quote'))
    hit=np.flatnonzero(prices>=target if side==1 else prices<=target)
    if len(hit):choices.append((int(hit[0]),3,'target_quote'))
    if not choices:return dict(legs=[],incomplete=True,partial_fallback=False,expiry=expiry)
    offset,_,why=min(choices);trigger=i+offset;actual=int(np.searchsorted(t,t[trigger]+cost.get('exit_delay',0.)))
    if actual>=len(t):return dict(legs=[],incomplete=True,partial_fallback=False,expiry=expiry)
    bid=float(q['bid'][actual]);ask=bid+float(q['ask'][actual]-bid)*cost['spread'];price=bid if side==1 else ask
    if why=='target_quote'and not cost.get('exit_delay',0.):price=target
    leg=dict(index=actual,quantity=quantity,price=price-side*slip,reason=why+('_delayed'if cost.get('exit_delay',0.)else''),terminal=True)
    return dict(legs=[leg],incomplete=False,partial_fallback=False,expiry=expiry,maximum_observed_gap_seconds=float(np.max(np.diff(t[i:actual+1])))if actual>i else 0.)


class ProtectedBook(HoldingBook):
    def enter(self,*a,**kw):
        # Private finite offline process only;restore before returning. Original
        # source and the separate frozen collector/evaluators never change.
        assert engine.path is ORIGINAL_PATH
        engine.path=protected_path
        try:return super().enter(*a,**kw)
        finally:engine.path=ORIGINAL_PATH
