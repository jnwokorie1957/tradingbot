"""Third bounded discovery batch: pre-known session levels and time-of-day noise.

This adds source files only. Existing registered evaluators/results stay frozen.
"""
from collections import deque
from datetime import datetime,timezone,timedelta
from . import run as batch
from . import extension as execution_sensitivity
from .data import NY
from .signals import HOLIDAYS,EARLY_CLOSE

FAMILIES=('prior_session_reclaim','time_of_day_breakout')


class LevelNoiseSignals:
    def __init__(self,minutes,tick):
        self.minutes=minutes;self.tick=tick;self.day=None;self.session={};self.prior=None;self.sessions=deque(maxlen=14);self.history=deque(maxlen=3);self.last=None;self.previous_bounds=None

    def close_previous_session(self):
        if not self.day or self.day in HOLIDAYS or datetime.fromisoformat(self.day).weekday()>=5:return
        close=EARLY_CLOSE.get(self.day,960);expected=set(range(570,close,self.minutes))
        # Quality of the PREVIOUS session is known before this day's decisions.
        if set(self.session)!=expected:
            self.prior=None;self.sessions.clear();return
        bars=[self.session[k] for k in sorted(self.session)];opening=bars[0]['open']
        self.prior=dict(low=min(b['low'] for b in bars),high=max(b['high'] for b in bars),close=bars[-1]['close'],day=self.day)
        self.sessions.append(dict(day=self.day,opening=opening,moves={k:abs(b['close']/opening-1) for k,b in self.session.items()}))

    def generate(self,bars):
        out={f:[] for f in FAMILIES}
        for raw in bars:
            b={k:float(raw[k]) for k in ['t','open','high','low','close']};end=b['t']+self.minutes*60
            at=datetime.fromtimestamp(end,timezone.utc).astimezone(NY);start=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY);day=start.date().isoformat();clock=at.hour*60+at.minute;slot=start.hour*60+start.minute
            if day!=self.day:
                self.close_previous_session()
                if self.day:
                    missing=datetime.fromisoformat(self.day)+timedelta(days=1)
                    while missing.date().isoformat()<day:
                        if missing.weekday()<5 and missing.date().isoformat() not in HOLIDAYS:self.prior=None;self.sessions.clear()
                        missing+=timedelta(days=1)
                self.day=day;self.session={};self.previous_bounds=None;self.history.clear()
            if self.last is not None and b['t']!=self.last+self.minutes*60:self.history.clear();self.previous_bounds=None
            self.last=b['t'];close=EARLY_CLOSE.get(day,960)
            eligible=start.weekday()<5 and day not in HOLIDAYS and 585<=clock<=min(930,close-30)
            deadline=at.replace(hour=(close-5)//60,minute=(close-5)%60,second=0,microsecond=0).timestamp()
            if 570<=slot<close:self.session[slot]=b
            def emit(family,side,stop,room=None):
                if eligible:out[family].append(dict(decision=end,entry_at=end+1,side=side,stop=stop,room=room,reference=b['close'],deadline=deadline,hold_seconds=min(3600,20*self.minutes*60),family=family,minutes=self.minutes))
            prev=self.history[-1] if self.history else None
            if prev is not None and self.prior:
                low,high=self.prior['low'],self.prior['high'];mid=(low+high)/2
                if prev['close']<low and low<b['close']<mid and b['close']>b['open']:
                    emit('prior_session_reclaim',1,min(prev['low'],b['low'])-self.tick,mid)
                elif prev['close']>high and mid<b['close']<high and b['close']<b['open']:
                    emit('prior_session_reclaim',-1,max(prev['high'],b['high'])+self.tick,mid)
            if self.prior and len(self.sessions)==14 and 570 in self.session and all(slot in s['moves'] for s in self.sessions):
                opening=self.session[570]['open'];sigma=sum(s['moves'][slot] for s in self.sessions)/14
                upper=max(opening,self.prior['close'])*(1+sigma);lower=min(opening,self.prior['close'])*(1-sigma)
                # Typical-price session mean is explicitly NOT exchange-volume VWAP.
                mean=sum((x['high']+x['low']+x['close'])/3 for x in self.session.values())/len(self.session)
                if prev is not None and self.previous_bounds and len(self.history)>=2:
                    recent=list(self.history)[-2:]+[b]
                    if prev['close']<=self.previous_bounds[1] and b['close']>upper and b['close']>mean and b['close']>b['open']:
                        emit('time_of_day_breakout',1,min(x['low'] for x in recent)-self.tick)
                    elif prev['close']>=self.previous_bounds[0] and b['close']<lower and b['close']<mean and b['close']<b['open']:
                        emit('time_of_day_breakout',-1,max(x['high'] for x in recent)+self.tick)
                self.previous_bounds=(lower,upper)
            else:self.previous_bounds=None
            self.history.append(b)
        return out


ORIGINAL_WRITE=batch.write


def registered_write(path,value):
    if path.name=='protocol.json':
        value.update(replacement_reason='New fixed session-level and time-of-day hypotheses following 96 completed development cost cases; no prior rule or benchmark changed.',execution_delay_seconds=1,latency_sensitivity_seconds=5,hypotheses={
            'prior_session_reclaim':'Require the previous complete known RTH session. Prior candle closes outside that high/low, current directional candle closes back inside and before prior midpoint. Natural two-candle extreme stop, known prior midpoint target-room guard. No gap fill from missing prior bars.',
            'time_of_day_breakout':'Fourteen prior fully observed RTH sessions, same native time slot average absolute open-to-close move. Bounds max(today open,prior close)*(1+sigma), min(today open,prior close)*(1-sigma). Closed-candle crossing plus directional body and typical-price session-mean confirmation. Natural three-candle extreme stop. This is an adaptation, not original paper replication or VWAP.'},session_history='Only fully observed previous RTH sessions supply levels and noise history; half-day calendar fixed. Any missing trading session or incomplete prior session resets levels/history; weekends and exchange holidays do not. Missing prior slots are not interpolated. Current-day future coverage never vetoes an earlier decision.',latency_gate='Selected candidates also replayed with five-second delayed entry at BOTH costs; require >=100 trades,>=60% wins,positive net,PF>=1.2,DD<10 for promotion.',prior_comparisons='96 completed development cost cases, eight further market/timeframe/RR configurations per family (32 new cost cases). Configurations share prices and are not independent samples. All dates previously exposed. Later diagnostics are not untouched OOS.')
    ORIGINAL_WRITE(path,value)


def main():
    batch.VERSION='short_horizon_mt5_v4';batch.FAMILIES=FAMILIES;batch.Signals=LevelNoiseSignals;batch.write=registered_write
    # Reuse the frozen execution-sensitivity helper without editing its file.
    execution_sensitivity.ExtensionSignals=LevelNoiseSignals;batch.report=execution_sensitivity.extension_report
    batch.SOURCES=[dict(title='Concretum: intraday momentum',url='https://concretumgroup.substack.com/p/beat-the-market-with-intraday-momentum',role='Original SPY time-of-day noise-area research; our contracts, stops, targets, sessions and mean-confirmation differ.'),dict(title='New York Fed: support/resistance mechanism',url='https://www.newyorkfed.org/research/staff_reports/sr125.html',role='FX order-clustering mechanism motivates a falsifiable equity-index session-level hypothesis. Transfer and profitability are unproven.'),dict(title='NYSE calendar',url='https://www.nyse.com/trade/hours-calendars',role='Pre-known holidays and early closes.')]
    batch.main()


if __name__=='__main__':main()
