"""Three independent, preregistered closed-candle hypotheses."""
import math
from collections import deque,Counter
from datetime import datetime,timezone
from .data import NY

FAMILIES=('band_reentry','opening_range_failure','inside_bar_trap')
# Published US cash-equity calendar, fixed before the replacement batch.
HOLIDAYS={'2025-12-25','2026-01-01','2026-01-19','2026-02-16','2026-04-03','2026-05-25','2026-06-19','2026-07-03','2026-09-07'}
EARLY_CLOSE={'2025-12-24':780}


class Signals:
    def __init__(self,minutes,tick):
        self.minutes=minutes;self.tick=tick;self.history=deque(maxlen=21);self.band=None;self.day=None;self.or_bars=[];self.or_level=None;self.trap=None;self.index=0;self.last=None

    def generate(self,bars):
        out={n:[] for n in FAMILIES}
        for raw in bars:
            b={k:float(raw[k]) for k in ['t','open','high','low','close']};end=b['t']+self.minutes*60
            at=datetime.fromtimestamp(end,timezone.utc).astimezone(NY);day=at.date().isoformat();clock=at.hour*60+at.minute
            if day!=self.day:self.day=day;self.or_bars=[];self.or_level=None;self.trap=None
            if self.last is not None and b['t']!=self.last+self.minutes*60:self.history.clear();self.band=None;self.trap=None
            self.last=b['t'];self.index+=1
            start=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY);start_clock=start.hour*60+start.minute
            if 570<=start_clock<585:self.or_bars.append(b)
            if clock>=585 and self.or_level is None and len(self.or_bars)==15//self.minutes:
                first=self.or_bars[0];last=self.or_bars[-1]
                if datetime.fromtimestamp(first['t'],timezone.utc).astimezone(NY).hour*60+datetime.fromtimestamp(first['t'],timezone.utc).astimezone(NY).minute==570 and last['t']+self.minutes*60-first['t']==900:
                    self.or_level=(min(x['low'] for x in self.or_bars),max(x['high'] for x in self.or_bars))
            close=EARLY_CLOSE.get(day,960)
            eligible=at.weekday()<5 and day not in HOLIDAYS and 585<=clock<=min(930,close-30)
            deadline=at.replace(hour=(close-5)//60,minute=(close-5)%60,second=0,microsecond=0).timestamp()
            def emit(family,side,stop,room=None):
                if not eligible:return
                out[family].append(dict(decision=end,entry_at=end+60,side=side,stop=stop,reference=b['close'],room=room,deadline=deadline,hold_seconds=min(3600,20*self.minutes*60),family=family,minutes=self.minutes))
            prev=self.history[-1] if self.history else None
            if len(self.history)>=19:
                values=[x['close'] for x in list(self.history)[-19:]]+[b['close']];mean=sum(values)/20;sd=math.sqrt(sum((v-mean)**2 for v in values)/20);current=(mean-2*sd,mean,mean+2*sd)
                if prev is not None and self.band is not None and sd>0:
                    if prev['close']<self.band[0] and current[0]<b['close']<mean and b['close']>b['open']:
                        emit('band_reentry',1,min(prev['low'],b['low'])-self.tick,mean)
                    elif prev['close']>self.band[2] and mean<b['close']<current[2] and b['close']<b['open']:
                        emit('band_reentry',-1,max(prev['high'],b['high'])+self.tick,mean)
                self.band=current
            if prev is not None and self.or_level is not None and clock<=690:
                low,high=self.or_level
                if prev['close']<low and low<b['close']<high:
                    emit('opening_range_failure',1,min(prev['low'],b['low'])-self.tick,high)
                elif prev['close']>high and low<b['close']<high:
                    emit('opening_range_failure',-1,max(prev['high'],b['high'])+self.tick,low)
            if self.trap:
                tr=self.trap
                if self.index-tr['index']>3:self.trap=None
                else:
                    tr['low']=min(tr['low'],b['low']);tr['high']=max(tr['high'],b['high'])
                    if tr['side']*(b['close']-tr['level'])>0:
                        emit('inside_bar_trap',tr['side'],tr['low']-self.tick if tr['side']==1 else tr['high']+self.tick)
                        self.trap=None
            if len(self.history)>=2:
                mother,inside=self.history[-2],self.history[-1]
                if inside['high']<mother['high'] and inside['low']>mother['low']:
                    if b['high']<inside['high'] and b['low']<inside['low']:
                        self.trap=dict(index=self.index,side=1,level=inside['high'],low=min(inside['low'],b['low']),high=max(inside['high'],b['high']))
                    elif b['high']>inside['high'] and b['low']>inside['low']:
                        self.trap=dict(index=self.index,side=-1,level=inside['low'],low=min(inside['low'],b['low']),high=max(inside['high'],b['high']))
            self.history.append(b)
        return out
