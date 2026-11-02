"""Paper-only intent ledger and shared portfolio admission. No broker dependencies."""
import hashlib,math
from datetime import datetime,timezone
from .audited_run import NY,up,down
from .risk_review import RiskReview
from .entry_quality_v2 import reject
from .hourly_entry_quality import reject_quality
from .confirmation_quality import reject_confirmation
from .portfolio_discipline_rules import reject_state
from .atlas_capture_core import allocation as shared_allocation
from .atlas_portfolio_controller import allocate as approved_allocation


def intent_id(lane,s):
    return hashlib.sha256(f'{lane}|{s["decision"]}|{s["side"]}'.encode()).hexdigest()[:24]


def allocation(meta,entry,distance,slip,fee,cash,equity,positions,symbol,side,guard,policy):
    mult=meta['trade_tick_value_loss']/meta['trade_tick_size'];perlot=(distance+slip)*mult+fee;minimum=perlot*meta['volume_min'];used=sum(p['risk'] for p in positions.values());margin=sum(p['margin'] for p in positions.values())
    budget=guard.cap(cash);total=25.;margin_limit=min(cash,equity)
    if policy.get('governed'):
        safe=max(0.,min(cash,equity));pct=min(policy['risk_pct'],.005) if guard.loss_streak>=2 else policy['risk_pct'];budget=min(budget,safe*pct);total=min(25.,safe*.02);margin_limit=safe*.5
    margin_perlot=entry*meta.get('trade_contract_size',100.)*meta.get('assumed_margin_rate',.005)*policy.get('margin_multiplier',1.)
    free_margin=max(0.,margin_limit-margin);available=max(0.,min(budget,total-used,cash));quantity=down(min(available/perlot,free_margin/margin_perlot,meta.get('volume_max',1000.)),meta['volume_step']);reasons=[]
    if (policy.get('governed') or policy.get('direction_guard')) and any(p['symbol']==symbol and p['side']!=side for p in positions.values()):reasons.append('conflicting_same_symbol_exposure')
    if minimum>budget+1e-8:reasons.append('minimum_lot_above_trade_risk')
    if minimum>total-used+1e-8:reasons.append('shared_gross_risk_budget')
    if margin_perlot*meta['volume_min']>free_margin+1e-8:reasons.append('shared_margin_budget')
    if cash<minimum:reasons.append('insufficient_cash')
    return dict(quantity=max(0.,quantity),perlot=perlot,margin_perlot=margin_perlot,minimum_legal_risk=minimum,lane_budget=budget,total_budget=total,used_risk=used,free_margin=free_margin,reasons=reasons)


class PaperBook:
    def __init__(self,lanes,meta,policy=None,cost=None,initial=500.,sink=None):
        self.lanes=lanes;self.meta=meta;self.policy=policy or {};self.cost=cost or dict(spread=1.,fee=6.,slip_ticks=1,exit_delay=0.);self.initial=initial;self.cash=self.peak=initial;self.dd=0.;self.positions={};self.latest={};self.guards={n:RiskReview('recovery_trend') for n in lanes};self.busy={n:-1. for n in lanes};self.history=[];self.pending={n:[] for n in lanes};self.seen=set();self.fills=[];self.decisions=[];self.sink=sink;self.max_risk=self.max_margin=0.;self.max_positions=0;self.max_gross=0.;self.events={n:sorted(lane.get('signals',{}).items()) for n,lane in lanes.items()};self.indices={n:0 for n in lanes};self.exits={n:sorted(lane.get('exits',[])) for n,lane in lanes.items()};self.exit_indices={n:0 for n in lanes};self.last_exit={n:{1:float('-inf'),-1:float('-inf')} for n in lanes}
        self.risk_day=None;self.day_start=initial;self.daily_paused=False;self.drawdown_paused=False
    def economics(self,symbol):
        m=self.meta[symbol];return m['trade_tick_size'],m['trade_tick_value_loss']/m['trade_tick_size'],m['trade_tick_size']*self.cost['slip_ticks'],self.cost['fee']
    def received_path(self,symbol,receipt,bid,ask,path):
        """Existing orders only. Observe source-ordered crossings;fill at adverse receipt path."""
        converted=[(t,b,b+(a-b)*self.cost['spread']) for t,b,a in path];current_ask=bid+(ask-bid)*self.cost['spread']
        for pid in [key for key,p in self.positions.items() if p['symbol']==symbol]:
            p=self.positions[pid];side=p['side'];trigger=None;why=None
            for i,(t,b,a) in enumerate(converted):
                if t<p['at']:continue
                price=b if side==1 else a
                if price<=p['stop'] if side==1 else price>=p['stop']:trigger=i;why='received_stop_adverse';break
                if t>=p['expiry']:trigger=i;why='received_expiry_adverse';break
                if p['target'] is not None and (price>=p['target'] if side==1 else price<=p['target']):trigger=i;why='received_target_market_adverse';break
            if trigger is not None:
                values=[(b if side==1 else a) for _,b,a in converted[trigger:]]+[bid if side==1 else current_ask]
                price=min(values) if side==1 else max(values);self._close(pid,price,receipt,why)
    def equity(self):
        value=self.cash
        for p in self.positions.values():
            bid,ask,_=self.latest[p['symbol']];_,mult,slip,fee=self.economics(p['symbol']);value+=(((bid if p['side']==1 else ask)-p['side']*slip-p['entry'])*p['side']*mult-fee)*p['quantity']
        return value
    def _record(self,row):
        self.decisions.append(row)
        if self.sink:self.sink('decision',row)
    def enqueue(self,name,s):
        self.events[name].append((s['decision'],s))
    def _submit(self,name,s,t):
        sid=intent_id(name,s)
        if sid in self.seen:
            self._record(dict(id=sid,lane=name,decision=s['decision'],status='BLOCKED',reason='duplicate_intent',all_reasons=['duplicate_intent']));return
        self.seen.add(sid);lane=self.lanes[name];local=datetime.fromtimestamp(s['decision'],timezone.utc).astimezone(NY);clock=local.hour*60+local.minute
        row=dict(id=sid,lane=name,symbol=lane['symbol'],side=s['side'],decision=s['decision'],entry_at=s['entry_at'])
        if not lane['start']<=clock<=lane['end']:
            row.update(status='REJECTED',reason='outside_registered_signal_session',all_reasons=['outside_registered_signal_session']);self._record(row);return
        holding=any(p['lane']==name for p in self.positions.values())
        early=(holding or s['decision']<=self.busy[name]) and not self.policy.get('defer_busy_gate')
        self.pending[name].append(dict(signal=s,row=row,early_busy=early))
    def _close(self,pid,price,t,why):
        p=self.positions.pop(pid);_,mult,slip,fee=self.economics(p['symbol']);fill=price-p['side']*slip;pnl=((fill-p['entry'])*p['side']*mult-fee)*p['quantity'];self.cash+=pnl;self.guards[p['lane']].exited(pnl,t);self.busy[p['lane']]=t;self.history.append((t,pnl))
        f=dict(id=pid,strategy=p['lane'],symbol=p['symbol'],entry_at=p['at'],exit_at=t,side=p['side'],quantity=p['quantity'],entry=p['entry'],exit=fill,stop=p['stop'],target=p['target'],pnl=pnl,reason=why,planned_risk=p['risk'],entry_margin=p['margin']);self.fills.append(f)
        if self.sink:self.sink('fill',f)
    def quote(self,symbol,t,bid,ask,fresh=True,source_time=None):
        ask=bid+(ask-bid)*self.cost['spread'];self.latest[symbol]=(bid,ask,t);local=datetime.fromtimestamp(t,timezone.utc).astimezone(NY);day=str(local.date());clock=local.hour*60+local.minute
        if self.policy.get('atlas5000'):
            eq=self.equity()
            if day!=self.risk_day:self.risk_day=day;self.day_start=eq;self.daily_paused=False
            self.daily_paused=self.daily_paused or eq<=self.day_start*.98
            self.drawdown_paused=self.drawdown_paused or eq<=self.peak*.9
        for name,lane in self.lanes.items():
            if lane['symbol']!=symbol:continue
            guard=self.guards[name];guard.session_start(day)
            while self.indices[name]<len(self.events[name]) and self.events[name][self.indices[name]][0]<=t:
                _,s=self.events[name][self.indices[name]];self.indices[name]+=1;self._submit(name,s,t)
            while self.exit_indices[name]<len(self.exits[name]) and self.exits[name][self.exit_indices[name]][0]<=t:
                when,side=self.exits[name][self.exit_indices[name]];self.last_exit[name][side]=when;self.exit_indices[name]+=1
            remain=[]
            for item in self.pending[name]:
                s=item['signal'];row=item['row']
                if t<s['entry_at']:remain.append(item);continue
                if source_time is not None and source_time<s['entry_at'] and t-s['entry_at']<=5:remain.append(item);continue
                reasons=[];side=s['side'];tick,mult,slip,fee=self.economics(symbol);entry=(ask if side==1 else bid)+side*slip
                if self.policy.get('entry_halt_reason'):reasons.append(self.policy['entry_halt_reason'])
                if 'stop_distance'in s:distance=up(s['stop_distance'],tick);stop=entry-side*distance
                else:stop=down(s['stop'],tick) if side==1 else up(s['stop'],tick);distance=side*(entry-stop)
                if t-s['entry_at']>5:reasons.append('no_quote_within_5s')
                if not fresh:reasons.append('stale_received_quote')
                if not lane['start']<=clock<=lane['end']:reasons.append('entry_outside_session')
                executable=bid if side==1 else ask
                if distance<tick-1e-8 or (executable<=stop if side==1 else executable>=stop):reasons.append('invalid_or_breached_stop')
                for reason in [reject(lane['hypothesis'],s,entry,distance,lane['rr'] or 1.5),('short_entry_disabled' if lane['direction']=='long_only' and side!=1 else 'long_entry_disabled' if lane['direction']=='short_only' and side!=-1 else None),reject_quality(lane['quality'],s,entry),reject_confirmation(lane['confirmation'],s),reject_state(lane,s,guard,t,self.history),guard.entry_reason(s,ask-bid,slip,distance)]:
                    if reason:reasons.append(reason)
                row.update(observed_at=t,entry_quote=entry,stop=stop,distance=distance,signal_qualified=not reasons)
                if item['early_busy']:primary='open_position_at_decision'
                elif any(p['lane']==name for p in self.positions.values()) and not self.policy.get('allow_multiple'):primary='open_position_at_entry'
                else:primary=None
                if primary:reasons.insert(0,primary)
                if self.policy.get('governed') and self.equity()<self.peak*.92:reasons.append('portfolio_drawdown_entry_review')
                if distance>=tick-1e-8:
                    if self.policy.get('atlas5000'):
                        eq_now=self.equity();self.daily_paused=self.daily_paused or eq_now<=self.day_start*.98;self.drawdown_paused=self.drawdown_paused or eq_now<=self.peak*.9
                        alloc=approved_allocation(self.meta[symbol],entry,distance,slip,fee,self.cash,eq_now,self.positions,symbol,side,self.day_start,self.peak,self.daily_paused,self.drawdown_paused,self.cost.get('margin_multiplier',1.))
                    else:alloc=shared_allocation(self.meta[symbol],entry,distance,slip,fee,self.cash,self.equity(),self.positions,symbol,side,guard,{**self.policy,'margin_multiplier':self.cost.get('margin_multiplier',1.)})
                    row.update({k:v for k,v in alloc.items() if k!='reasons'});reasons.extend(alloc['reasons'])
                else:alloc=dict(quantity=0.)
                # An identical economic intent is never admitted twice under a different label.
                if (self.policy.get('governed') or self.policy.get('atlas5000')) and any(p['symbol']==symbol and p['side']==side and p['decision']==s['decision'] and abs(p['stop']-stop)<tick/2 for p in self.positions.values()):reasons.append('duplicate_economic_intent')
                row['all_reasons']=list(dict.fromkeys(reasons))
                if reasons:
                    reason=reasons[0];status='MISSED' if reason in ['no_quote_within_5s','stale_received_quote'] else 'BLOCKED' if reason.startswith(('open_position','shared_','minimum_lot','conflicting_','duplicate_','portfolio_','insufficient_')) else 'REJECTED';row.update(status=status,reason=reason)
                elif alloc['quantity']<self.meta[symbol]['volume_min']-1e-8:row.update(status='BLOCKED',reason='quantity_rounding_or_cash',all_reasons=['quantity_rounding_or_cash'])
                else:
                    quantity=alloc['quantity'];reward=down(lane['rr']*distance,tick) if lane['rr'] is not None else None;sid=row['id'];self.positions[sid]=dict(lane=name,symbol=symbol,side=side,entry=entry,stop=stop,target=entry+side*reward if reward is not None else None,quantity=quantity,at=t,expiry=min(s.get('expiry_at',t+3600),s.get('deadline',float('inf'))),risk=alloc['perlot']*quantity,margin=alloc['margin_perlot']*quantity,decision=s['decision'],pending_exit=None);guard.entered();row.update(status='EXECUTED',reason='paper_fill',planned_risk=self.positions[sid]['risk'],quantity=quantity);self.max_risk=max(self.max_risk,sum(p['risk'] for p in self.positions.values()));self.max_margin=max(self.max_margin,sum(p['margin'] for p in self.positions.values()));self.max_positions=max(self.max_positions,len(self.positions));assert sum(p['risk'] for p in self.positions.values())<=alloc['total_budget']+1e-7
                    if self.policy.get('governed'):assert sum(p['risk'] for p in self.positions.values())<=min(25.,max(0.,min(self.cash,self.equity()))*.02)+1e-7 or sum(p['risk'] for p in self.positions.values())<=alloc['total_budget']+1e-7
                self._record(row)
            self.pending[name]=remain
            for pid in [key for key,p in self.positions.items() if p['lane']==name]:
                p=self.positions.get(pid)
                if not p:continue
                side=p['side'];price=bid if side==1 else ask;why=None
                if p['pending_exit']:
                    if t>=p['pending_exit'][0]:self._close(pid,price,t,p['pending_exit'][1]+'_delayed')
                    continue
                if price<=p['stop'] if side==1 else price>=p['stop']:why='stop_quote'
                elif t>=p['expiry']:why='time_exit_quote'
                elif self.last_exit[name][side]>=p['at']:why='indicator_exit_quote'
                elif p['target'] is not None and (price>=p['target'] if side==1 else price<=p['target']):why='target_quote';price=p['target']
                if why:
                    if self.cost.get('exit_delay',0):p['pending_exit']=(t+self.cost['exit_delay'],why)
                    else:self._close(pid,price,t,why)
        eq=self.equity();self.peak=max(self.peak,eq);self.dd=max(self.dd,(self.peak-eq)/self.peak)
        if self.policy.get('atlas5000'):self.daily_paused=self.daily_paused or eq<=self.day_start*.98;self.drawdown_paused=self.drawdown_paused or eq<=self.peak*.9
        gross=sum((self.latest[p['symbol']][0]+self.latest[p['symbol']][1])*.5*self.meta[p['symbol']].get('trade_contract_size',100.)*p['quantity'] for p in self.positions.values());self.max_gross=max(self.max_gross,gross)
    def finish(self):
        for name in self.lanes:
            for _,s in self.events[name][self.indices[name]:]:self._submit(name,s,float('inf'))
            self.indices[name]=len(self.events[name])
            for item in self.pending[name]:self._record(dict(item['row'],status='MISSED',reason='no_quote_before_data_end',all_reasons=['no_quote_before_data_end']))
            self.pending[name]=[]
        assert abs(self.cash-self.initial-sum(f['pnl'] for f in self.fills))<1e-7
    def result(self):
        eq=self.equity();limits=dict(per_trade_all_in_ceiling=min(25.,max(0.,eq)*.005),combined_planned_open_risk=max(0.,eq)*.01,daily_loss_pause_dollars=self.day_start*.02,drawdown_pause_equity=self.peak*.9,daily_paused=self.daily_paused,drawdown_paused=self.drawdown_paused,daily_trade_count_limit=None) if self.policy.get('atlas5000') else dict(combined_planned_open_risk=25.,per_trade_maximum=25.,recovery_trade_maximum=10.,daily_trade_count_limit=None)
        return dict(initial_balance=self.initial,ending_balance=self.cash,current_equity=eq,net_pnl=self.cash-self.initial,trades=len(self.fills),win_rate=100*sum(f['pnl']>0 for f in self.fills)/len(self.fills) if self.fills else None,quote_drawdown_pct=self.dd*100,max_open_risk=self.max_risk,max_reserved_margin=self.max_margin,max_positions=self.max_positions,max_gross_notional=self.max_gross,open_positions=len(self.positions),active_limits=limits)
