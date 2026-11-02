"""Independent vectorized historical quote execution; no broker interface."""
import math
from collections import Counter
from datetime import datetime,timezone
import numpy as np
from .data import NY

COSTS={'standard':dict(spread=1.,slip_ticks=1,fee_per_lot=6.),'higher':dict(spread=1.5,slip_ticks=2,fee_per_lot=12.)}
RISK=dict(initial_equity=5000.,per_trade_pct=.005,per_trade_ceiling=25.,total_open_pct=.01,daily_loss_pct=.02,drawdown_pause_pct=.10,daily_trade_count_limit=None)


def floor_step(x,step):return math.floor(x/step+1e-9)*step
def ceil_step(x,step):return math.ceil(x/step-1e-9)*step


class Account:
    def __init__(self,meta,cost,rr):
        self.meta=meta;self.cost=cost;self.rr=rr;self.cash=self.peak=5000.;self.dd=0.;self.paused=False;self.daily_paused=False;self.day=None;self.day_start=5000.;self.last_exit=-float('inf');self.fills=[];self.decisions=[];self.maximum_risk=0.;self.maximum_margin=0.;self.maximum_gap_seconds=0.

    def run_day(self,date,t,bid,ask,plans):
        if self.day!=date:self.day=date;self.day_start=self.cash;self.daily_paused=False
        tick=self.meta['trade_tick_size'];mult=self.meta['trade_tick_value_loss']/tick;slip=self.cost['slip_ticks']*tick;fee=self.cost['fee_per_lot'];adjusted=bid+(ask-bid)*self.cost['spread']
        for s in sorted(plans,key=lambda x:x['decision']):
            row=dict(decision=s['decision'],entry_at=s['entry_at'],side=s['side'],status='REJECTED');reason=None
            if s['decision']<=self.last_exit:reason='position_open_at_decision'
            elif self.paused:reason='drawdown_10pct_pause'
            elif self.daily_paused:reason='daily_2pct_loss_pause'
            i=int(np.searchsorted(t,s['entry_at']))
            if reason is None and (i>=len(t) or t[i]-s['entry_at']>5):reason='no_fresh_entry_quote'
            if reason:row['reason']=reason;self.decisions.append(row);continue
            side=s['side'];entry=(adjusted[i] if side==1 else bid[i])+side*slip
            stop=floor_step(s['stop'],tick) if side==1 else ceil_step(s['stop'],tick);distance=side*(entry-stop)
            executable=bid if side==1 else adjusted
            if distance<tick-1e-8 or (executable[i]<=stop if side==1 else executable[i]>=stop):reason='invalid_or_breached_stop'
            reward=floor_step(self.rr*max(0.,distance),tick)
            if reason is None and s.get('room') is not None and side*(s['room']-entry)<reward:reason='insufficient_preentry_target_room'
            perlot=(distance+slip)*mult+fee;budget=min(25.,max(0.,self.cash)*.005);total=max(0.,self.cash)*.01
            margin_perlot=entry*self.meta.get('trade_contract_size',100.)*self.meta.get('assumed_margin_rate',.005)
            quantity=floor_step(min(budget/perlot,total/perlot,self.cash/(margin_perlot+perlot),self.meta.get('volume_max',1000.)),self.meta['volume_step']) if perlot>0 else 0.
            row.update(entry_quote=entry,stop=stop,trade_budget=budget,minimum_legal_risk=perlot*self.meta['volume_min'])
            if reason is None and quantity<self.meta['volume_min']-1e-8:reason='minimum_lot_or_margin_or_risk'
            if reason:row['reason']=reason;self.decisions.append(row);continue
            expiry=min(t[i]+s['hold_seconds'],s['deadline']);edge=int(np.searchsorted(t,expiry));last=min(edge+1,len(t));prices=executable[i:last]
            hit_stop=np.flatnonzero(prices<=stop if side==1 else prices>=stop);target=entry+side*reward;hit_target=np.flatnonzero(prices>=target if side==1 else prices<=target)
            choices=[]
            if len(hit_stop):choices.append((int(hit_stop[0]),0,'stop_quote'))
            if len(hit_target):choices.append((int(hit_target[0]),1,'target_quote'))
            if edge<len(t):choices.append((edge-i,2,'time_exit_quote'))
            if not choices:raise ValueError('Incomplete position-price path; no forced end-of-data fill')
            offset,_,why=min(choices);j=i+offset
            price=target if why=='target_quote' else executable[j];exit_price=price-side*slip
            pnl=((exit_price-entry)*side*mult-fee)*quantity
            equity=self.cash+((executable[i:j+1]-side*slip-entry)*side*mult-fee)*quantity;equity[-1]=self.cash+pnl
            peaks=np.maximum.accumulate(np.r_[self.peak,equity])[1:];dd=(peaks-equity)/peaks
            self.dd=max(self.dd,float(dd.max()));self.peak=float(peaks[-1]);self.daily_paused=self.daily_paused or float(equity.min())<=self.day_start*.98;self.paused=self.paused or self.dd>=.10
            self.cash+=pnl;self.last_exit=float(t[j]);risk=perlot*quantity;margin=margin_perlot*quantity
            assert risk<=budget+1e-7 and risk<=total+1e-7 and risk+margin<=self.cash-pnl+1e-7
            self.maximum_risk=max(self.maximum_risk,risk);self.maximum_margin=max(self.maximum_margin,margin)
            if j>i:self.maximum_gap_seconds=max(self.maximum_gap_seconds,float(np.diff(t[i:j+1]).max()))
            f=dict(decision=s['decision'],entry_at=float(t[i]),exit_at=float(t[j]),side=side,quantity=quantity,entry=entry,exit=exit_price,stop=stop,target=target,rr=self.rr,planned_risk=risk,margin=margin,pnl=pnl,reason=why)
            f.update(equity_after=self.cash,peak_equity=self.peak,maximum_drawdown_to_date_pct=self.dd*100,trade_equity_min=float(equity.min()),trade_equity_max=float(equity.max()))
            self.fills.append(f);row.update(status='EXECUTED',reason='simulated_quote_fill',quantity=quantity);self.decisions.append(row)

    def result(self,first='2025-12-15',end='2026-10-31',fills=None):
        fills=self.fills if fills is None else fills;values=[f['pnl'] for f in fills];wins=[p for p in values if p>0];losses=[p for p in values if p<0];net=sum(values)
        if fills is self.fills:assert abs(self.cash-5000.-net)<1e-7
        return dict(initial_equity=5000.,ending_balance=5000.+net,net_pnl=net,trades=len(values),wins=len(wins),win_rate=100*len(wins)/len(values) if values else None,profit_factor=sum(wins)/-sum(losses) if losses else None,expectancy=net/len(values) if values else None,average_win=sum(wins)/len(wins) if wins else None,average_loss=sum(losses)/len(losses) if losses else None,drawdown_pct=self.dd*100,drawdown_scope='continuous account from development start',maximum_planned_risk=self.maximum_risk,maximum_margin=self.maximum_margin,maximum_observed_quote_gap_seconds=self.maximum_gap_seconds,veto_reasons=dict(Counter(x['reason'] for x in self.decisions if x['status']!='EXECUTED')),period=[first,end],paper_only=True,independently_validated=False)
