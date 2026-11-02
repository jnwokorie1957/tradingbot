"""Independent ledger/quote reconstruction and explicitly defined statistics."""
from datetime import date,datetime,timedelta,timezone
from itertools import combinations
import math
import numpy as np
from .audited_run import NY

FIRST='2025-12-15';END_EXCLUSIVE='2026-10-31'


def weekdays(first=FIRST,end=END_EXCLUSIVE):
    a=date.fromisoformat(first);b=date.fromisoformat(end)
    return [(a+timedelta(days=i)).isoformat() for i in range((b-a).days) if (a+timedelta(days=i)).weekday()<5]


def local_day(t):return datetime.fromtimestamp(t,timezone.utc).astimezone(NY).date().isoformat()


def streak(values):
    maximum=current=0
    for value in values:
        current=current+1 if value<0 else 0;maximum=max(maximum,current)
    return maximum


def metrics(fills,initial=500.,first=FIRST,end=END_EXCLUSIVE):
    days=weekdays(first,end);byday={d:0. for d in days};values=np.array([f['pnl'] for f in fills],dtype=float)
    intraday=all(local_day(f['entry_at'])==local_day(f['exit_at']) for f in fills)
    for f in fills:
        d=local_day(f['exit_at'])
        if d not in byday:raise ValueError('Fill outside funded weekday calendar')
        byday[d]+=f['pnl']
    pnl=np.array(list(byday.values()));balances=initial+np.cumsum(pnl);prior=np.r_[initial,balances[:-1]];returns=pnl/prior
    std=float(np.std(returns,ddof=1)) if len(returns)>1 else 0.;downside=float(np.sqrt(np.mean(np.minimum(returns,0.)**2))) if len(returns) else 0.
    gains=values[values>0];losses=values[values<0];net=float(values.sum());elapsed=(date.fromisoformat(end)-date.fromisoformat(first)).days;annual=((initial+net)/initial)**(365.2425/elapsed)-1 if initial+net>0 else None
    rvals=[f['pnl']/f['planned_risk'] for f in fills if f.get('planned_risk',0)>0]
    m=dict(initial_balance=initial,ending_balance=initial+net,net_pnl=net,return_pct=100*net/initial,elapsed_calendar_days=elapsed,business_day_observations=len(days),annualized_extrapolation_pct=annual*100 if annual is not None else None,profit_factor=float(gains.sum()/-losses.sum()) if len(losses) else None,expectancy_dollars=float(values.mean()) if len(values) else None,expectancy_planned_R=float(np.mean(rvals)) if rvals else None,sharpe_annualized_rf0=math.sqrt(252)*float(np.mean(returns))/std if std else None,sortino_annualized_MAR0=math.sqrt(252)*float(np.mean(returns))/downside if downside else None,average_win=float(gains.mean()) if len(gains) else None,average_loss=float(losses.mean()) if len(losses) else None,max_consecutive_losses=streak(values),trades=len(fills),wins=len(gains),losses=len(losses),flats=int(sum(values==0)),win_rate=100*len(gains)/len(values) if len(values) else None,all_positions_closed_intraday=intraday,daily_dates=days,daily_pnl=pnl.tolist(),daily_returns=returns.tolist(),daily_balance=balances.tolist())
    if not intraday:m['daily_ratios_warning']='Daily close cash may omit open positions;ratios must not be treated as validated'
    return m


def reconstruct(trace,fills,metadata,symbol_ids,scenario,reported_dd=None):
    """No use of the replay's peak/equity calculations to construct the curve."""
    n=len(trace);flows=np.zeros(n);unreal=np.zeros(n);risk=np.zeros(n);margin=np.zeros(n);gross=np.zeros(n);count=np.zeros(n,dtype=np.int16);exposure={s:np.zeros(n) for s in symbol_ids};last={}
    for s,ident in symbol_ids.items():last[s]=np.maximum.accumulate(np.where(trace['symbol']==ident,np.arange(n),-1))
    max_pnl_error=0.;commission=slip_cost=spread_proxy=0.
    for f in fills:
        start=f['entry_event']-1;end=f['exit_event']-1;assert 0<=start<=end<n
        s=f['symbol'];m=metadata[s];mult=m['trade_tick_value_loss']/m['trade_tick_size'];slip=m['trade_tick_size']*scenario['slip_ticks'];fee=scenario['fee'];q=f['quantity'];side=f['side']
        recomputed=((f['exit']-f['entry'])*side*mult-fee)*q;max_pnl_error=max(max_pnl_error,abs(recomputed-f['pnl']));assert abs(recomputed-f['pnl'])<1e-7
        flows[end]+=recomputed
        if end>start:
            ix=last[s][start:end];assert np.all(ix>=0)
            executable=trace['bid'][ix] if side==1 else trace['ask'][ix]
            unreal[start:end]+=((executable-side*slip-f['entry'])*side*mult-fee)*q
            notional=(trace['bid'][ix]+trace['ask'][ix])*.5*m.get('trade_contract_size',100.)*q
            gross[start:end]+=notional;exposure[s][start:end]+=side*notional;risk[start:end]+=f['planned_risk'];margin[start:end]+=f['entry_margin'];count[start:end]+=1
        commission+=q*fee;slip_cost+=2*slip*mult*q
        which=start if side==1 else end;spread_proxy+=(trace['ask'][which]-trace['bid'][which])*mult*q
    cash=500+np.cumsum(flows);equity=cash+unreal;peaks=np.maximum.accumulate(np.r_[500.,equity])[1:];dd=(peaks-equity)/peaks
    cash_error=float(np.max(np.abs(cash-trace['cash']))) if n else 0.;equity_error=float(np.max(np.abs(equity-trace['equity']))) if n else 0.;assert cash_error<1e-7 and equity_error<1e-7,(cash_error,equity_error)
    drawdown=100*float(dd.max()) if n else 0.;assert reported_dd is None or abs(drawdown-reported_dd)<1e-7
    k=int(np.argmax(dd)) if n else 0;dt=np.r_[np.maximum(0,np.diff(trace['t'])),0.] if n else np.array([])
    # No positions cross overnight; zero exposure at the last quote before an omitted idle span.
    overlap=[]
    for a,b in combinations(sorted({f['strategy'] for f in fills}),2):
        pairs=[]
        for x in fills:
            if x['strategy']!=a:continue
            for y in fills:
                if y['strategy']!=b:continue
                seconds=min(x['exit_at'],y['exit_at'])-max(x['entry_at'],y['entry_at'])
                if seconds>0:pairs.append(dict(seconds=seconds,both_lost=x['pnl']<0 and y['pnl']<0))
        overlap.append(dict(a=a,b=b,overlapping_trade_pairs=len(pairs),both_losing_pairs=sum(x['both_lost'] for x in pairs),overlap_minutes=sum(x['seconds'] for x in pairs)/60))
    sample=np.r_[np.arange(0,n,max(1,n//1800)),k,n-1] if n else np.array([],int);sample=np.unique(sample)
    reserve=750.;resdd=100*float(np.max((peaks-equity)/(peaks+reserve))) if n else 0.
    risk_fraction=np.divide(risk,equity,out=np.zeros_like(risk),where=equity>0)
    return dict(max_pnl_formula_error=max_pnl_error,max_cash_reconstruction_error=cash_error,max_equity_reconstruction_error=equity_error,quote_drawdown_pct=drawdown,max_drawdown_dollars=float(np.max(peaks-equity)) if n else 0.,max_drawdown_at_utc=datetime.fromtimestamp(float(trace['t'][k]),timezone.utc).isoformat() if n else None,max_gross_notional=float(gross.max()) if n else 0.,max_gross_notional_to_equity=float(np.max(gross/equity)) if n else 0.,max_open_planned_risk=float(risk.max()) if n else 0.,max_open_risk_to_equity_pct=100*float(risk_fraction.max()) if n else 0.,max_reserved_entry_margin=float(margin.max()) if n else 0.,max_simultaneous_positions=int(count.max()) if n else 0.,minutes_multiple_positions=float(np.sum(dt[count>1]))/60 if n else 0.,commission_dollars=commission,modeled_roundtrip_slippage_dollars=slip_cost,embedded_spread_proxy_dollars=spread_proxy,overlap_pairs=overlap,reserve_overlay=dict(initial_total=1250.,segregated_cash=reserve,active_sleeve=500.,planned_risk_initial_total_pct=2.,quote_drawdown_pct=resdd,interpretation='Arithmetic overlay on unchanged frozen fills. Reserve is segregated,earns0,and unavailable to margin/sizing;not a new deployable replay or independent validation.'),curve=[dict(t=float(trace['t'][i]),equity=float(equity[i]),cash=float(cash[i]),drawdown_pct=float(dd[i]*100),gross_notional=float(gross[i]),open_risk=float(risk[i])) for i in sample])


def contribution_metrics(fills):
    individual={name:metrics([f for f in fills if f['strategy']==name]) for name in sorted({f['strategy'] for f in fills})};pairs=[]
    for a,b in combinations(individual,2):
        x=np.array(individual[a]['daily_pnl']);y=np.array(individual[b]['daily_pnl']);active=(x!=0)&(y!=0);coloss=(x<0)&(y<0)
        pairs.append(dict(a=a,b=b,weekday_pnl_correlation=float(np.corrcoef(x,y)[0,1]) if np.std(x)>0 and np.std(y)>0 else None,both_active_days=int(active.sum()),both_losing_days=int(coloss.sum()),co_loss_share_of_joint_active_days=float(coloss.sum()/active.sum()) if active.sum() else None,combined_pnl_on_co_loss_days=float((x+y)[coloss].sum())))
    return dict(strategies=individual,pairs=pairs,interpretation='Contributions use shared-account allocations,not independent500USD accounts. Correlations include zero weekdays;few jointly active days make them unreliable diversification evidence.')
