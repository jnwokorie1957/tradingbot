"""User-approved5000USD paper portfolio controller. No execution transport."""
from .audited_run import down

APPROVED=dict(initial_equity=5000.,per_trade_equity_pct=.005,per_trade_dollar_ceiling=25.,portfolio_equity_pct=.01,daily_loss_pause_pct=.02,drawdown_pause_pct=.10,daily_trade_count_limit=None,paper_only=True)


def allocate(meta,entry,distance,slip,fee,cash,equity,positions,symbol,side,day_start,peak,daily_paused=False,drawdown_paused=False,margin_multiplier=1.):
    safe=max(0.,min(cash,equity));budget=min(25.,max(0.,equity)*.005);total=max(0.,equity)*.01;used=sum(p['risk'] for p in positions.values());margin=sum(p['margin'] for p in positions.values());mult=meta['trade_tick_value_loss']/meta['trade_tick_size'];perlot=(distance+slip)*mult+fee;minimum=perlot*meta['volume_min'];margin_perlot=entry*meta.get('trade_contract_size',100.)*meta.get('assumed_margin_rate',.005)*margin_multiplier
    # The two index instruments form one correlated gross-risk basket. No netting credit.
    remaining=max(0.,min(budget,total-used));free=max(0.,safe-margin-used);quantity=down(min(remaining/perlot,free/(margin_perlot+perlot),meta.get('volume_max',1000.)),meta['volume_step']);reasons=[]
    if daily_paused or equity<=day_start*.98:reasons.append('daily_2pct_loss_pause')
    if drawdown_paused or equity<=peak*.9:reasons.append('portfolio_10pct_drawdown_pause')
    if any(p['symbol']==symbol and p['side']!=side for p in positions.values()):reasons.append('conflicting_same_symbol_exposure')
    if minimum>budget+1e-8:reasons.append('minimum_lot_above_trade_risk')
    if minimum>total-used+1e-8:reasons.append('shared_gross_risk_budget')
    if (margin_perlot+perlot)*meta['volume_min']>free+1e-8:reasons.append('broker_margin_plus_loss_reserve')
    return dict(quantity=max(0.,quantity),perlot=perlot,margin_perlot=margin_perlot,minimum_legal_risk=minimum,lane_budget=budget,total_budget=total,used_risk=used,free_margin=free,reasons=reasons)
