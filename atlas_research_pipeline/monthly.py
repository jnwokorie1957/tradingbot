"""Exact closed-intraday ledger monthly cash returns, with partial periods tagged."""
import calendar,math
from datetime import date,datetime,timedelta,timezone
import numpy as np
from atlas_exit_research.data import NY


def calculate(fills,initial,first='2025-12-15',end='2026-10-31',independent=False):
    first=date.fromisoformat(first);end=date.fromisoformat(end);current=first.replace(day=1);balance=initial;rows=[];all_intraday=all(datetime.fromtimestamp(f['entry_at'],timezone.utc).astimezone(NY).date()==datetime.fromtimestamp(f['exit_at'],timezone.utc).astimezone(NY).date() for f in fills)
    assert all_intraday,'Monthly cash statistics cannot stand in for marked equity with overnight positions'
    while current<end:
        after=(current.replace(day=28)+timedelta(days=4)).replace(day=1);key=current.strftime('%Y-%m');selected=[f for f in fills if datetime.fromtimestamp(f['exit_at'],timezone.utc).astimezone(NY).strftime('%Y-%m')==key];pnl=sum(f['pnl'] for f in selected);omitted=[current+timedelta(days=i) for i in range((after-current).days) if current+timedelta(days=i)>=end];full=first<=current and all(d.weekday()>=5 for d in omitted);r=100*pnl/balance
        rows.append(dict(month=key,starting_equity=balance,ending_equity=balance+pnl,net_pnl=pnl,return_pct=r,trades=len(selected),complete_trading_month=full,partial_reason=None if full else 'Funded window starts/ends within weekday coverage',independent=independent));balance+=pnl;current=after
    assert abs(balance-initial-sum(f['pnl'] for f in fills))<1e-6
    values=np.array([r['return_pct'] for r in rows if r['complete_trading_month']]);longest=streak=0
    for v in values:streak=streak+1 if v<0 else 0;longest=max(longest,streak)
    stats=dict(full_trading_months=len(values),partial_months=sum(not r['complete_trading_month'] for r in rows),average_monthly_net_return_pct=float(np.mean(values)) if len(values) else None,median_monthly_net_return_pct=float(np.median(values)) if len(values) else None,best_month_pct=float(max(values)) if len(values) else None,worst_month_pct=float(min(values)) if len(values) else None,profitable_months_pct=100*float(np.mean(values>0)) if len(values) else None,monthly_sample_std_percentage_points=float(np.std(values,ddof=1)) if len(values)>1 else None,longest_losing_month_streak=longest,thresholds={str(t):dict(months_reached=int(sum(values>=t)),eligible_months=len(values),frequency_pct=100*float(np.mean(values>=t)) if len(values) else None) for t in [15,20,25]},independent_thresholds={str(t):dict(months_reached=int(sum(values>=t)) if independent else None,eligible_months=len(values) if independent else 0,frequency_pct=100*float(np.mean(values>=t)) if independent and len(values) else None) for t in [15,20,25]},independently_evaluated=independent)
    return dict(months=rows,statistics=stats,method='Net cash from all economic fills with every position closed intraday; original all-in cost scenario retained. Zero-trade funded months included. Partial December excluded from headline mean/median/thresholds. October covers all weekday closes. No inference of independent frequency from reused prices.')
