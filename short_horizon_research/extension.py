"""Second bounded hypothesis batch; v1/v2 files and financial outputs stay frozen."""
from collections import deque
from datetime import datetime,timezone
import json
from . import run as batch
from .data import NY,candles,quotes,archives
from .engine import Account,COSTS
from .signals import HOLIDAYS,EARLY_CLOSE

FAMILIES=('trend_ma_reclaim','channel_retest','rsi2_trend_reclaim')


class ExtensionSignals:
    def __init__(self,minutes,tick):
        self.minutes=minutes;self.tick=tick;self.history=deque(maxlen=201);self.last=None;self.ema={20:None,50:None,200:None};self.ema20_history=deque(maxlen=6);self.up=self.down=0.;self.previous_rsi=None;self.arm=None;self.index=0;self.day=None

    def generate(self,bars):
        out={f:[] for f in FAMILIES}
        for raw in bars:
            b={k:float(raw[k]) for k in ['t','open','high','low','close']};end=b['t']+self.minutes*60;self.index+=1
            if self.last is not None and b['t']!=self.last+self.minutes*60:
                self.history.clear();self.ema={20:None,50:None,200:None};self.ema20_history.clear();self.up=self.down=0.;self.previous_rsi=None;self.arm=None
            self.last=b['t'];at=datetime.fromtimestamp(end,timezone.utc).astimezone(NY);day=at.date().isoformat();clock=at.hour*60+at.minute;close=EARLY_CLOSE.get(day,960)
            if day!=self.day:self.day=day;self.arm=None
            eligible=at.weekday()<5 and day not in HOLIDAYS and 585<=clock<=min(930,close-30)
            deadline=at.replace(hour=(close-5)//60,minute=(close-5)%60,second=0,microsecond=0).timestamp()
            prev=self.history[-1] if self.history else None;old20=self.ema[20]
            for period in self.ema:
                old=self.ema[period];self.ema[period]=b['close'] if old is None else old+(b['close']-old)*2/(period+1)
            if prev:
                delta=b['close']-prev['close'];self.up=.5*self.up+.5*max(0.,delta);self.down=.5*self.down+.5*max(0.,-delta)
            rsi=100*self.up/(self.up+self.down) if self.up+self.down else 50.
            def emit(f,side,stop):
                if eligible:out[f].append(dict(decision=end,entry_at=end+1,side=side,stop=stop,room=None,reference=b['close'],deadline=deadline,hold_seconds=min(3600,20*self.minutes*60),family=f,minutes=self.minutes))
            if len(self.history)>=50 and prev:
                recent=list(self.history)[-2:]+[b];low=min(x['low'] for x in recent)-self.tick;high=max(x['high'] for x in recent)+self.tick
                e20,e50,e200=[self.ema[k] for k in [20,50,200]]
                slope=self.ema20_history[0] if len(self.ema20_history)==6 else e20
                if e20>e50 and e20>slope and prev['close']<=old20 and b['close']>e20 and b['close']>b['open']:emit('trend_ma_reclaim',1,low)
                elif e20<e50 and e20<slope and prev['close']>=old20 and b['close']<e20 and b['close']<b['open']:emit('trend_ma_reclaim',-1,high)
                if len(self.history)>=200 and self.previous_rsi is not None:
                    if e50>e200 and b['close']>e200 and self.previous_rsi<10<=rsi and b['close']>b['open']:emit('rsi2_trend_reclaim',1,low)
                    elif e50<e200 and b['close']<e200 and self.previous_rsi>90>=rsi and b['close']<b['open']:emit('rsi2_trend_reclaim',-1,high)
            if self.arm:
                tr=self.arm
                if self.index-tr['index']>6:self.arm=None
                elif self.index>tr['index']:
                    side=tr['side'];touch=b['low']<=tr['level'] if side==1 else b['high']>=tr['level']
                    if touch and side*(b['close']-tr['level'])>self.tick and side*(b['close']-b['open'])>0:
                        recent=list(self.history)[-2:]+[b];stop=min(x['low'] for x in recent)-self.tick if side==1 else max(x['high'] for x in recent)+self.tick
                        emit('channel_retest',side,stop);self.arm=None
            if len(self.history)>=20 and self.arm is None:
                recent=list(self.history)[-20:];upper=max(x['high'] for x in recent);lower=min(x['low'] for x in recent);atr=sum(x['high']-x['low'] for x in recent[-14:])/14
                if abs(b['close']-b['open'])>=.5*atr:
                    if b['close']>upper:self.arm=dict(side=1,level=upper,index=self.index)
                    elif b['close']<lower:self.arm=dict(side=-1,level=lower,index=self.index)
            self.ema20_history.append(self.ema[20]);self.previous_rsi=rsi;self.history.append(b)
        return out


ORIGINAL_WRITE=batch.write
ORIGINAL_REPORT=batch.report


def registered_write(path,value):
    if path.name=='protocol.json':
        value.update(replacement_reason='Separate second bounded hypothesis batch, registered after all v2 configurations failed. No v2 or old Atlas benchmark is modified.',execution_delay_seconds=1,latency_sensitivity_seconds=5,hypotheses={
          'trend_ma_reclaim':'EMA20/50 direction and six-bar EMA20 slope; closed-candle reclaim of EMA20; stop beyond three-bar extreme.',
          'channel_retest':'Close beyond prior 20-bar channel with body >= half the prior 14-bar average range. Retest and directional close within six later bars. Stop beyond three-bar extreme.',
          'rsi2_trend_reclaim':'Intraday adaptation, not Connors replication: EMA50/200 direction, RSI2 Wilder rebound through 10/90, directional candle, stop beyond three-bar extreme. 200 complete-bar warmup.'},latency_gate='Selected candidates also replayed from beginning with five-second entry delay at BOTH costs. Require >=100 trades, >=60% win, positive net, PF>=1.2, DD<10. No reselection.',prior_comparisons='48 completed cost-adjusted development cases in v2, none qualified. All prices already exposed; not independent validation.')
    ORIGINAL_WRITE(path,value)


def extension_report(out,result):
    root=out.parents[1];meta=json.loads((out/'data/contract_snapshot.json').read_text());archive=archives(root);selection=json.loads((out/'selection.json').read_text())['selected'];latency=[]
    for symbol,rows in archive.items():
        selected=[s for s in selection if s['symbol']==symbol]
        if not selected:continue
        engines={m:ExtensionSignals(m,meta[symbol]['trade_tick_size']) for m in [1,5]};books={s['id']:{k:Account(meta[symbol],v,s['rr']) for k,v in COSTS.items()} for s in selected}
        for row in rows:
            date=row['date']
            if row.get('status')!='captured':continue
            t,bid,ask=quotes(root,out,symbol,row,'inferred_ny')
            if not len(t):continue
            plans={m:engines[m].generate(candles(t,bid,m)) for m in [1,5]}
            if date>='2025-12-15':
                for s in selected:
                    delayed=[dict(p,entry_at=p['decision']+5) for p in plans[s['minutes']][s['family']]]
                    for b in books[s['id']].values():b.run_day(date,t,bid,ask,delayed)
            ORIGINAL_WRITE(out/'progress.json',dict(updated_utc=batch.stamp(),phase='latency_sensitivity',symbol=symbol,date=date,paper_only=True))
        for s in selected:
            metrics={k:batch.metrics(v,'2025-12-15','2026-10-31') for k,v in books[s['id']].items()};latency.append(dict(s,metrics=metrics))
            for cost,b in books[s['id']].items():ORIGINAL_WRITE(out/'ledgers/latency5'/f'{s["id"]}_{cost}.json',dict(fills=b.fills,decisions=b.decisions,metrics=metrics[cost]))
    for row in result['challenge']:
        r=next(x for x in latency if x['id']==row['id'])
        if not batch.qualify(r['metrics'],100):row['decision']='FAIL: profitability / sample / win rate / drawdown / clock / latency gate'
    result['latency5']=latency;result['completed_utc']=batch.stamp();ORIGINAL_WRITE(out/'results.json',result);ORIGINAL_WRITE(out/'latency5.json',latency)
    ORIGINAL_REPORT(out,result)
    path=out/'report.html';page=path.read_text(encoding='utf-8').replace('60-second execution delay','one-second modeled execution delay, plus a five-second latency sensitivity')
    page=page.replace('<h2>Risk and evidence</h2>','<h2>Execution latency</h2><p>One-second entry delay is an estimate, not a measured historic receipt latency. <a href="latency5.json">Five-second sensitivity metrics</a> remain separate and must pass the same full-history target gates.</p><h2>Risk and evidence</h2>')
    path.write_text(page,encoding='utf-8')


def main():
    batch.VERSION='short_horizon_mt5_v3';batch.Signals=ExtensionSignals;batch.FAMILIES=FAMILIES;batch.write=registered_write;batch.report=extension_report
    batch.SOURCES=[dict(title='Cesar Alvarez: RSI2 research',url='https://alvarezquanttrading.com/blog/rsi2-strategy-double-returns-with-a-simple-rule-change/',role='Daily-stock source inspires only the trend-aligned pullback hypothesis. Our intraday EMA/RSI rules, stops and exits differ.'),dict(title='NYSE calendar',url='https://www.nyse.com/trade/hours-calendars',role='Pre-known holiday calendar; not a profitability filter.')]
    batch.main()


if __name__=='__main__':main()
