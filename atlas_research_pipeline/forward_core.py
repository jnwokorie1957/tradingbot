"""Fixed receipt-clock paper execution and independent ledger equity audit.

No network/MT5/order transport. Source-time paths inform conservative exits only
after their first collector receipt. Entry/expiry clocks are receipt timestamps.
"""
import math
from datetime import datetime,timezone,timedelta
from research_monitor.atlas_live_core import PaperBook
from atlas_exit_research.data import NY

HOLIDAYS={'2026-11-26','2026-12-25','2027-01-01','2027-01-18','2027-02-15','2027-03-26','2027-05-31','2027-06-18','2027-07-05','2027-09-06','2027-11-25','2027-12-24'}
EARLY={'2026-11-27':780,'2026-12-24':780,'2027-11-26':780}


def windows(start,through,minutes):
    """Frozen NYSE reference clock windows; not a CFD venue-hours certificate."""
    day=datetime.fromtimestamp(start,timezone.utc).astimezone(NY).date();last=datetime.fromtimestamp(through,timezone.utc).astimezone(NY).date();rows=[]
    if last.year>2027:raise ValueError('Frozen reference calendar horizon exceeded')
    while day<=last:
        key=day.isoformat();local=datetime.combine(day,datetime.min.time(),tzinfo=NY);close=EARLY.get(key,960);end=local.replace(hour=16,minute=15).timestamp()
        if day.weekday()<5 and key not in HOLIDAYS and end<=through:
            a=int(local.replace(hour=9,minute=30).timestamp());b=int(local.replace(hour=close//60,minute=close%60).timestamp());expected=set(range(a,b,60));counts={s:len(expected&set(bars)) for s,bars in minutes.items()};required=math.ceil(.99*len(expected));rows.append(dict(date=key,expected=len(expected),required=required,observed=counts,covered=all(v>=required for v in counts.values())))
        day+=timedelta(days=1)
    return dict(sessions=rows,covered_sessions=[r['date']for r in rows if r['covered']],uncovered_sessions=[r['date']for r in rows if not r['covered']])


def availability_prefix(minutes,available,freeze):
    """All earlier feature inputs must have arrived; conservative dependency bound."""
    times=sorted(minutes);out=[];last=freeze
    for t in times:last=max(last,available[t]);out.append(last)
    return times,out


def signal_available(decision,times,prefix,available,freeze):
    import bisect
    if any(m not in available for m in range(int(decision)-900,int(decision),60)):return None
    i=bisect.bisect_left(times,decision)-1
    return prefix[i] if i>=0 else freeze


class PairedPaperBook(PaperBook):
    def __init__(self,*a,nas_minutes=60,**kw):super().__init__(*a,**kw);self.nas_minutes=nas_minutes
    def _record(self,row):
        if row.get('status')=='EXECUTED':
            p=self.positions[row['id']];duration=self.nas_minutes if p['lane']=='NAS15' else 60;cutoff=datetime.fromtimestamp(p['at'],timezone.utc).astimezone(NY).replace(hour=16,minute=0,second=0,microsecond=0).timestamp();p['expiry']=min(p['at']+duration*60,cutoff);p['_last_source']=p['at'];p['_max_source_gap']=0.
        super()._record(row)
    def _close(self,pid,price,t,why):
        p=self.positions[pid];gap=p.get('_max_source_gap',0.);super()._close(pid,price,t,why);self.fills[-1].update(maximum_observed_source_gap_seconds=gap,execution_clock='first_collector_receipt',actual_broker_fill=False)
    def quote(self,symbol,t,bid,ask,fresh=True,source_time=None):
        if not fresh:raise ValueError('Stale quotes cannot advance this receipt-clock book')
        super().quote(symbol,t,bid,ask,fresh=True,source_time=source_time)
        for p in self.positions.values():
            if p['symbol']!=symbol or not p['pending_exit'] or '_pending_worst'in p:continue
            price=bid if p['side']==1 else bid+(ask-bid)*self.cost['spread']
            if 'target'in p['pending_exit'][1]:price=min(price,p['target'])if p['side']==1 else max(price,p['target'])
            p['_pending_worst']=price
    def observed_path(self,symbol,receipt,bid,ask,path):
        """Stops/targets seen inside a batch fill only now, at adverse observed price.

        Severe one-second exit delay is honored. Target profits are capped at the
        target; gaps/losses are never clipped. The final book.quote handles time
        exits triggered by receipt clock rather than source clock.
        """
        scaled=[(t,b,b+(a-b)*self.cost['spread'])for t,b,a in path];current_ask=bid+(ask-bid)*self.cost['spread']
        for pid in [k for k,p in self.positions.items()if p['symbol']==symbol]:
            p=self.positions[pid];side=p['side'];current=bid if side==1 else current_ask;future=[x for x in scaled if x[0]>=p['at']];last=p.get('_last_source',p['at'])
            for t,_,_ in future:
                if t>last:p['_max_source_gap']=max(p.get('_max_source_gap',0.),t-last);last=t
            p['_last_source']=last
            if p['pending_exit']:
                values=[b if side==1 else a for _,b,a in future]+[current,p.get('_pending_worst',current)];worst=min(values)if side==1 else max(values);p['_pending_worst']=worst
                if receipt>=p['pending_exit'][0]:self._close(pid,worst,receipt,p['pending_exit'][1]+'_adverse_delayed')
                continue
            for i,(_,b,a) in enumerate(future):
                price=b if side==1 else a;why=None
                if price<=p['stop']if side==1 else price>=p['stop']:why='received_stop'
                elif p['target']is not None and(price>=p['target']if side==1 else price<=p['target']):why='received_target'
                if why:
                    values=[x[1]if side==1 else x[2]for x in future[i:]]+[current];worst=min(values)if side==1 else max(values)
                    if why=='received_target':worst=min(worst,p['target'])if side==1 else max(worst,p['target'])
                    if self.cost.get('exit_delay',0):p['pending_exit']=(receipt+self.cost['exit_delay'],why);p['_pending_worst']=worst
                    else:self._close(pid,worst,receipt,why+'_adverse')
                    break


class LedgerAudit:
    """Reconstruct from entry decisions, closed fills and raw received prices.

    Path bound deliberately combines favorable/adverse quotes conservatively;
    it is an upper bound on observed intrabatch drawdown, not an exact synchronous
    source-tick equity curve and never a bound on unseen or broker-realized loss.
    """
    def __init__(self,meta,cost):self.meta=meta;self.cost=cost;self.cash=self.peak=self.bound_peak=5000.;self.dd=self.bound_dd=0.;self.positions={};self.latest={};self.decisions_seen=self.fills_seen=0;self.max_difference=0.
    def floating(self,p,bid,ask):
        m=self.meta[p['symbol']];side=p['side'];price=bid if side==1 else bid+(ask-bid)*self.cost['spread'];slip=m['trade_tick_size']*self.cost['slip_ticks'];mult=m['trade_tick_value_loss']/m['trade_tick_size'];return ((price-side*slip-p['entry'])*side*mult-self.cost['fee'])*p['quantity']
    def path_bound(self,paths,receipt):
        low=high=self.cash
        for p in self.positions.values():
            values=[self.floating(p,b,a)for t,b,a in paths.get(p['symbol'],[])if p['at']<=t<=receipt+1]
            if not values:values=[self.floating(p,*self.latest[p['symbol']])]
            low+=min(values);high+=max(values)
        self.bound_peak=max(self.bound_peak,high);self.bound_dd=max(self.bound_dd,(self.bound_peak-low)/self.bound_peak)
    def point(self,book,symbol,bid,ask):
        self.latest[symbol]=(bid,ask)
        for row in book.decisions[self.decisions_seen:]:
            if row.get('status')=='EXECUTED':
                assert row['id']not in self.positions;assert row['planned_risk']<=row['lane_budget']+1e-7 and row['planned_risk']+row['used_risk']<=row['total_budget']+1e-7;name=row['lane'];self.positions[row['id']]=dict(symbol=book.lanes[name]['symbol'],side=row['side'],entry=row['entry_quote'],quantity=row['quantity'],at=row['observed_at'])
        self.decisions_seen=len(book.decisions)
        for f in book.fills[self.fills_seen:]:
            p=self.positions.pop(f['id']);m=self.meta[p['symbol']];value=((f['exit']-p['entry'])*p['side']*m['trade_tick_value_loss']/m['trade_tick_size']-self.cost['fee'])*p['quantity'];assert abs(value-f['pnl'])<1e-7;self.cash+=value
        self.fills_seen=len(book.fills);eq=self.cash+sum(self.floating(p,*self.latest[p['symbol']])for p in self.positions.values());self.max_difference=max(self.max_difference,abs(eq-book.equity()));assert self.max_difference<1e-6 and abs(self.cash-book.cash)<1e-6;self.peak=max(self.peak,eq);self.dd=max(self.dd,(self.peak-eq)/self.peak);self.bound_peak=max(self.bound_peak,eq);self.bound_dd=max(self.bound_dd,(self.bound_peak-eq)/self.bound_peak)
    def result(self):return dict(cash=self.cash,receipt_marked_drawdown_pct=100*self.dd,conservative_observed_path_drawdown_bound_pct=100*max(self.dd,self.bound_dd),maximum_equity_difference=self.max_difference,open_positions=len(self.positions),method='Independent entry/closed-fill cash and receipt marks;conservative intrabatch observed-path range bound,not exact synchronized tickDD or brokerloss guarantee')
