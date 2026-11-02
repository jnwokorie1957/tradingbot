"""Event-driven historical exits with quote-by-quote equity between events.

Future paths only schedule exits. Entry admission sees current/earlier prices,
cash, positions and realized history. No terminal or broker transport exists.
"""
import bisect,heapq,math
from collections import Counter
from datetime import datetime,timezone
import numpy as np
from .data import NY
from research_monitor.risk_review import RiskReview
from research_monitor.entry_quality_v2 import reject
from research_monitor.hourly_entry_quality import reject_quality
from research_monitor.confirmation_quality import reject_confirmation
from research_monitor.portfolio_discipline_rules import reject_state
from research_monitor.atlas_portfolio_controller import allocate
from research_monitor.atlas_live_core import intent_id
from research_monitor.audited_run import up,down

EXITS=('original','fixed_1_5','fixed_2','fixed_3','fixed_4','trailing','partial_trailing','structure')
TARGETS={'fixed_1_5':1.5,'fixed_2':2.,'fixed_3':3.,'fixed_4':4.}


def path(q,t,i,entry,stop,side,quantity,signal,lane,style,meta,cost,indicator_times,structure):
    tick=meta['trade_tick_size'];slip=tick*cost['slip_ticks'];distance=side*(entry-stop);expiry=min(signal.get('expiry_at',t[i]+3600),signal.get('deadline',float('inf')));edge=int(np.searchsorted(t,expiry));end=min(len(t),edge+1)
    raw=q[i:end];ask=raw['bid']+(raw['ask']-raw['bid'])*cost['spread'];prices=np.asarray(raw['bid'] if side==1 else ask);progress=side*(prices-entry)/distance
    rr=lane['rr'] if style=='original' else TARGETS.get(style);reward=down(rr*distance,tick) if rr is not None else None
    stops=np.full(len(prices),-1.)
    if style in ('trailing','partial_trailing','structure'):
        peak=np.maximum.accumulate(progress);prior=np.r_[-np.inf,peak[:-1]];active=prior>=1.5
        if style=='structure':
            ends,levels=structure;indices=np.searchsorted(ends,t[i:end],side='right')-1;level=np.full(len(prices),-np.inf);valid=indices>=0;level[valid]=side*(levels[indices[valid]]-entry)/distance
        else:level=prior-1.
        stops=np.maximum.accumulate(np.maximum(-1.,np.where(active,level,-1.)))
    if style in ('original',*TARGETS):stop_prices=np.full(len(prices),stop)
    else:
        proposed=entry+side*stops*distance;rounded=np.floor(proposed/tick+1e-9)*tick if side==1 else np.ceil(proposed/tick-1e-9)*tick
        stop_prices=np.where(stops<=-1.,stop,rounded)
    choices=[];hit=np.flatnonzero(prices<=stop_prices if side==1 else prices>=stop_prices)
    if len(hit):choices.append((int(hit[0]),0,'stop_quote' if style in ('original',*TARGETS) else 'managed_stop_quote'))
    if edge<len(t):choices.append((edge-i,1,'time_exit_quote'))
    if style=='original':
        j=bisect.bisect_left(indicator_times,float(t[i]))
        if j<len(indicator_times):
            k=int(np.searchsorted(t,indicator_times[j]))
            if k<end:choices.append((k-i,2,'indicator_exit_quote'))
    if reward is not None:
        target=entry+side*reward;hit=np.flatnonzero(prices>=target if side==1 else prices<=target)
        if len(hit):choices.append((int(hit[0]),3,'target_quote'))
    if not choices:return dict(legs=[],incomplete=True,partial_fallback=False,expiry=expiry)
    offset,priority,why=min(choices);trigger=i+offset;actual=int(np.searchsorted(t,t[trigger]+cost.get('exit_delay',0.)))
    if actual>=len(t):return dict(legs=[],incomplete=True,partial_fallback=False,expiry=expiry)
    def fill_price(k,target=None):
        raw_bid=float(q['bid'][k]);raw_ask=raw_bid+float(q['ask'][k]-raw_bid)*cost['spread'];price=raw_bid if side==1 else raw_ask
        if target is not None and not cost.get('exit_delay',0.):price=target
        return price-side*slip
    legs=[];fallback=False;remaining=quantity
    if style=='partial_trailing':
        part=down(quantity*.5,meta['volume_step']);fallback=part<meta['volume_min']-1e-8 or quantity-part<meta['volume_min']-1e-8
        partial_target=entry+side*down(1.5*distance,tick);hits=np.flatnonzero(prices>=partial_target if side==1 else prices<=partial_target)
        if len(hits) and not fallback:
            p_trigger=i+int(hits[0]);p_actual=int(np.searchsorted(t,t[p_trigger]+cost.get('exit_delay',0.)))
            # A protective stop/time exit takes priority while a partial is pending.
            if p_trigger<trigger and p_actual<trigger:
                legs.append(dict(index=p_actual,quantity=part,price=fill_price(p_actual,entry+side*down(1.5*distance,tick)),reason='partial_1_5R',terminal=False));remaining-=part
    target=entry+side*reward if why=='target_quote' else None
    legs.append(dict(index=actual,quantity=remaining,price=fill_price(actual,target),reason=why+('_delayed' if cost.get('exit_delay',0.) else ''),terminal=True))
    return dict(legs=legs,incomplete=False,partial_fallback=fallback,expiry=expiry,maximum_observed_gap_seconds=float(np.max(np.diff(t[i:actual+1]))) if actual>i else 0.,final_stop_R=float(stops[offset]))


class Account:
    def __init__(self,market,lanes,meta,cost,styles):
        self.market=market;self.lanes=lanes;self.meta=meta;self.cost=cost;self.styles=styles;self.cash=self.peak=5000.;self.dd=0.;self.positions={};self.fills=[];self.decisions=[];self.guards={n:RiskReview('recovery_trend') for n in lanes};self.history=[];self.day=None;self.day_start=5000.;self.daily_paused=False;self.drawdown_paused=False;self.cursor=-1;self.serial=0;self.heap=[];self.max_risk=self.max_margin=0.;self.max_positions=0;self.partial_fallbacks=0;self.unknown_paths=0;self.day_balances={};self.structure={};self.indicators={}
        for order,(name,lane) in enumerate(lanes.items()):
            self.indicators[name]={side:[when for when,s in lane.get('exits',[]) if s==side] for side in [-1,1]}
            native=lane.get('native',[]);ends=np.array([b['t']+lane.get('minutes',15)*60+1 for b in native]);low=np.array([b['low'] for b in native]);high=np.array([b['high'] for b in native]);tick=meta[lane['symbol']]['trade_tick_size']
            self.structure[name]={1:(ends[1:],np.minimum(low[:-1],low[1:])-tick),-1:(ends[1:],np.maximum(high[:-1],high[1:])+tick)}
            for _,signal in sorted(lane['signals'].items()):
                local=datetime.fromtimestamp(signal['decision'],timezone.utc).astimezone(NY);clock=local.hour*60+local.minute
                if not lane['start']<=clock<=lane['end']:continue
                s=lane['symbol'];i=int(np.searchsorted(market.t[s],signal['entry_at']))
                if i<len(market.t[s]):self.push(market.event(s,i),order,0,'entry',(name,signal,i))
        self.lane_order={n:i for i,n in enumerate(lanes)}

    def push(self,k,order,stage,kind,data):
        self.serial+=1;heapq.heappush(self.heap,(k,order,stage,self.serial,kind,data))

    def equity(self,k):
        result=self.cash
        for p in self.positions.values():
            q=self.market.quote(p['symbol'],k);bid=float(q['bid']);ask=bid+float(q['ask']-bid)*self.cost['spread'];price=bid if p['side']==1 else ask
            result+=((price-p['side']*p['slip']-p['entry'])*p['side']*p['mult']-self.cost['fee'])*p['quantity']
        return result

    def new_day(self,k,equity):
        day=self.market.dates[int(self.market.day_index[k])]
        if day!=self.day:
            if self.day is not None:self.day_balances[self.day]=self.cash
            self.day=day;self.day_start=equity;self.daily_paused=False
            for g in self.guards.values():g.session_start(day)

    def flag(self,equity):
        self.daily_paused=self.daily_paused or equity<=self.day_start*.98;self.drawdown_paused=self.drawdown_paused or equity<=self.peak*.9

    def point(self,k):
        eq=self.equity(k);self.new_day(k,eq);self.peak=max(self.peak,eq);self.dd=max(self.dd,(self.peak-eq)/self.peak);self.flag(eq)

    def advance(self,k):
        if k<=self.cursor:return
        if not self.positions:
            self.new_day(k,self.cash);self.peak=max(self.peak,self.cash);self.dd=max(self.dd,(self.peak-self.cash)/self.peak);self.flag(self.cash);self.cursor=k;return
        begin=self.cursor+1
        while begin<=k:
            end=min(k+1,begin+200000);days=self.market.day_index[begin:end];change=np.flatnonzero(days!=days[0])
            if len(change):end=begin+int(change[0])
            ix=np.arange(begin,end);eq=np.full(len(ix),self.cash)
            for p in self.positions.values():
                own=np.searchsorted(self.market.indices[p['symbol']],ix,side='right')-1;assert np.all(own>=0);raw=self.market.q[p['symbol']][own];ask=raw['bid']+(raw['ask']-raw['bid'])*self.cost['spread'];price=raw['bid'] if p['side']==1 else ask
                eq+=((price-p['side']*p['slip']-p['entry'])*p['side']*p['mult']-self.cost['fee'])*p['quantity']
            self.new_day(begin,float(eq[0]));peaks=np.maximum.accumulate(np.r_[self.peak,eq])[1:];self.dd=max(self.dd,float(np.max((peaks-eq)/peaks)));self.peak=float(peaks[-1]);self.daily_paused=self.daily_paused or float(eq.min())<=self.day_start*.98;self.drawdown_paused=self.drawdown_paused or self.dd>=.1;begin=end
        self.cursor=k

    def enter(self,k,name,signal,i):
        lane=self.lanes[name];symbol=lane['symbol'];q=self.market.q[symbol][i];t=float(q['t']);side=signal['side'];m=self.meta[symbol];tick=m['trade_tick_size'];mult=m['trade_tick_value_loss']/tick;slip=tick*self.cost['slip_ticks'];bid=float(q['bid']);ask=bid+float(q['ask']-bid)*self.cost['spread'];entry=(ask if side==1 else bid)+side*slip;stop=entry-side*up(signal['stop_distance'],tick) if 'stop_distance' in signal else down(signal['stop'],tick) if side==1 else up(signal['stop'],tick);distance=side*(entry-stop);clock=datetime.fromtimestamp(t,timezone.utc).astimezone(NY);clock=clock.hour*60+clock.minute
        row=dict(id=intent_id(name,signal),lane=name,decision=signal['decision'],entry_at=signal['entry_at'],observed_at=t,side=side,entry_quote=entry,stop=stop);reasons=[]
        if t-signal['entry_at']>5:reasons.append('no_quote_within_5s')
        if not lane['start']<=clock<=lane['end']:reasons.append('entry_outside_session')
        executable=bid if side==1 else ask
        if distance<tick-1e-8 or (executable<=stop if side==1 else executable>=stop):reasons.append('invalid_or_breached_stop')
        guard=self.guards[name]
        for reason in [reject(lane['hypothesis'],signal,entry,distance,lane['rr'] or 1.5),('short_entry_disabled' if lane['direction']=='long_only' and side!=1 else 'long_entry_disabled' if lane['direction']=='short_only' and side!=-1 else None),reject_quality(lane['quality'],signal,entry),reject_confirmation(lane['confirmation'],signal),reject_state(lane,signal,guard,t,self.history),guard.entry_reason(signal,ask-bid,slip,distance)]:
            if reason:reasons.append(reason)
        if distance>=tick-1e-8:
            eq=self.equity(k);self.flag(eq);allocation=allocate(m,entry,distance,slip,self.cost['fee'],self.cash,eq,self.positions,symbol,side,self.day_start,self.peak,self.daily_paused,self.drawdown_paused,self.cost.get('margin_multiplier',1.));reasons.extend(allocation['reasons']);row.update({k:v for k,v in allocation.items() if k!='reasons'})
        else:allocation=dict(quantity=0.)
        if any(p['symbol']==symbol and p['side']==side and p['decision']==signal['decision'] and abs(p['stop']-stop)<tick/2 for p in self.positions.values()):reasons.append('duplicate_economic_intent')
        if reasons:row.update(status='REJECTED',reasons=list(dict.fromkeys(reasons)));self.decisions.append(row);return
        quantity=allocation['quantity']
        if quantity<m['volume_min']-1e-8:row.update(status='BLOCKED',reasons=['quantity_rounding_or_cash']);self.decisions.append(row);return
        pid=row['id'];assert pid not in self.positions;style=self.styles[name];trajectory=path(self.market.q[symbol],self.market.t[symbol],i,entry,stop,side,quantity,signal,lane,style,m,self.cost,self.indicators[name][side],self.structure[name][side]);risk=allocation['perlot']*quantity;margin=allocation['margin_perlot']*quantity
        configured_rr=lane['rr'] if style=='original' else TARGETS.get(style);target=entry+side*down(configured_rr*distance,tick) if configured_rr is not None else None
        p=dict(lane=name,symbol=symbol,side=side,entry=entry,stop=stop,target=target,quantity=quantity,original_quantity=quantity,at=t,decision=signal['decision'],risk=risk,initial_risk=risk,margin=margin,initial_margin=margin,mult=mult,slip=slip,realized=0.,legs=[],style=style,path_gap=trajectory.get('maximum_observed_gap_seconds',0.),incomplete=trajectory['incomplete'])
        self.positions[pid]=p;self.unknown_paths+=int(trajectory['incomplete']);self.partial_fallbacks+=int(trajectory['partial_fallback']);guard.entered();row.update(status='EXECUTED',planned_risk=risk,quantity=quantity,style=style,reasons=[]);self.decisions.append(row)
        self.max_risk=max(self.max_risk,sum(x['risk'] for x in self.positions.values()));self.max_margin=max(self.max_margin,sum(x['margin'] for x in self.positions.values()));self.max_positions=max(self.max_positions,len(self.positions));assert sum(x['risk'] for x in self.positions.values())<=allocation['total_budget']+1e-7
        for leg in trajectory['legs']:self.push(self.market.event(symbol,leg['index']),self.lane_order[name],1,'leg',(pid,leg))

    def close_leg(self,k,pid,leg):
        p=self.positions[pid];qty=leg['quantity'];pnl=((leg['price']-p['entry'])*p['side']*p['mult']-self.cost['fee'])*qty;self.cash+=pnl;p['realized']+=pnl;p['legs'].append(dict(at=float(self.market.times[k]),price=leg['price'],quantity=qty,pnl=pnl,reason=leg['reason']));p['quantity']-=qty;p['risk']=p['initial_risk']*p['quantity']/p['original_quantity'];p['margin']=p['initial_margin']*p['quantity']/p['original_quantity']
        if leg['terminal']:
            assert abs(p['quantity'])<1e-8;del self.positions[pid];t=float(self.market.times[k]);self.guards[p['lane']].exited(p['realized'],t);self.history.append((t,p['realized']));self.fills.append(dict(id=pid,strategy=p['lane'],symbol=p['symbol'],entry_at=p['at'],exit_at=t,side=p['side'],quantity=p['original_quantity'],entry=p['entry'],exit=sum(x['price']*x['quantity'] for x in p['legs'])/p['original_quantity'],stop=p['stop'],target=p['target'],pnl=p['realized'],reason=leg['reason'],planned_risk=p['initial_risk'],entry_margin=p['initial_margin'],exit_style=p['style'],legs=p['legs'],net_R=p['realized']/p['initial_risk'],maximum_observed_quote_gap_seconds=p['path_gap']))

    def run_to(self,end):
        cutoff=datetime.fromisoformat(end).replace(tzinfo=NY).timestamp();limit=int(np.searchsorted(self.market.times,cutoff));
        while self.heap and self.heap[0][0]<limit:
            k=self.heap[0][0];self.advance(k-1);eq=self.equity(k);self.new_day(k,eq);self.flag(eq)
            while self.heap and self.heap[0][0]==k:
                _,_,_,_,kind,data=heapq.heappop(self.heap)
                if kind=='entry':self.enter(k,*data)
                else:self.close_leg(k,*data)
            self.point(k);self.cursor=k
        if limit:self.advance(limit-1)
        assert abs(self.cash-5000.-sum(f['pnl'] for f in self.fills)-sum(p['realized'] for p in self.positions.values()))<1e-6

    def result(self):
        values=[f['pnl'] for f in self.fills];return dict(initial_equity=5000.,ending_balance=self.cash,net_pnl=self.cash-5000.,trades=len(values),win_rate=100*sum(x>0 for x in values)/len(values) if values else None,quote_drawdown_pct=self.dd*100,max_open_risk=self.max_risk,max_reserved_margin=self.max_margin,max_positions=self.max_positions,open_positions=len(self.positions),incomplete_paths=self.unknown_paths,partial_fallbacks=self.partial_fallbacks,rejections=dict(Counter(reason for row in self.decisions if row['status']!='EXECUTED' for reason in row.get('reasons',[]))),paper_only=True,independent_validation=False)
