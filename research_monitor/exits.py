"""Predeclared exit hypotheses. Trail revisions apply only to the next observation."""
POLICIES=('baseline','fixed_1_5','fixed_2','conditional_2','trail_3','breakeven_2','protect_half','protect_close','protect_recovery')

def target_rr(policy,base,signal):
    if policy not in POLICIES:raise ValueError('Unknown exit policy')
    if policy=='fixed_1_5':return 1.5
    if policy in ('fixed_2','breakeven_2'):return 2.
    if policy=='trail_3':return 3.
    if policy=='conditional_2':return max(base,2.) if signal.get('trend_aligned') and signal.get('strong_close') else base
    return base

def next_stop(policy,p,high,low,tick,close_=None):
    from .local_run import up,down
    side=p['side'];best=max(p.get('best',p['entry']),high) if side==1 else min(p.get('best',p['entry']),low)
    p['best']=best;excursion=side*(best-p['entry'])/p['distance'];stop=p['stop']
    if policy=='protect_half' and excursion>=1:proposed=p['entry']-side*.5*p['distance']
    elif policy=='protect_close' and close_ is not None and side*(close_-p['entry'])/p['distance']>=1:proposed=p['entry']
    elif policy=='protect_recovery' and p.get('recovery') and excursion>=1:proposed=p['entry']
    elif policy=='breakeven_2' and excursion>=1:proposed=p['entry']
    elif policy=='trail_3' and excursion>=1.5:proposed=best-side*.75*p['distance']
    else:return stop
    proposed=down(proposed,tick) if side==1 else up(proposed,tick)
    return max(stop,proposed) if side==1 else min(stop,proposed)
