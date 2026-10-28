"""Atomic, local-only observation snapshots. No brokerage transport."""
import json, os, time, uuid
from datetime import datetime, timezone
from pathlib import Path


class Reporter:
    def __init__(self, directory, interval=.15):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.interval=interval;self.last_write=0.;self.state={}

    def begin(self, run_id, symbol, timeframe, strategy, starting_balance=500, **metadata):
        self.state=dict(id=str(run_id),symbol=symbol,timeframe=timeframe,strategy=strategy,
            mode='observed',status='running',started_at=datetime.now(timezone.utc).isoformat(),
            starting_balance=starting_balance,balance=starting_balance,equity=starting_balance,
            progress=0,candles=[],events=[],plan=None,metadata=metadata)
        self.flush(True)

    def candle(self, time_, open_, high, low, close, **extra):
        item=dict(time=time_,open=open_,high=high,low=low,close=close,**extra)
        candles=self.state.setdefault('candles',[])
        if candles and candles[-1]['time']==time_:candles[-1]=item
        else:
            candles.append(item)
            self.state['candle_count']=self.state.get('candle_count',0)+1
        del candles[:-300]

    def event(self, kind, **fields):
        self.state.setdefault('events',[]).append(dict(kind=kind,**fields))
        self.state['events']=self.state['events'][-100:]
        self.flush(True)

    def update(self, **values):
        self.state.update(values);self.flush()

    def finish(self, status='completed', **values):
        self.state.update(status=status,**values);self.flush(True)

    def flush(self, force=False):
        now=time.monotonic()
        if not force and now-self.last_write<self.interval:return
        snapshot=dict(self.state,updated_at=datetime.now(timezone.utc).isoformat())
        encoded=json.dumps(snapshot,allow_nan=False)
        target=self.directory/'state.json';temporary=self.directory/(uuid.uuid4().hex+'.tmp')
        try:
            temporary.write_text(encoded,encoding='utf-8');os.replace(temporary,target)
        finally:
            if temporary.exists():temporary.unlink()
        self.last_write=now


class EngineObserver:
    """Adapter for the admitted, causal pipeline. Only observed events are emitted."""
    def __init__(self, directory):self.reporter=Reporter(directory);self.count=0;self.total=0
    def begin_trial(self, run_id, metadata, total):
        self.count=0;self.total=total
        h=metadata['hypothesis']
        self.reporter.begin(run_id,'Awaiting instrument','—',h['family'].title(),
            phase=metadata['phase'],scenario=metadata['scenario']['id'],
            evidence='Synthetic simulation' if metadata.get('synthetic') else 'Historical simulation')
    def on_event(self, engine, event, outcome):
        self.count+=1;r=self.reporter;key=event['contract'];s=engine.state
        r.state['symbol']=key
        if event['kind']=='bar':
            minutes=round((datetime.fromisoformat(event['end'].replace('Z','+00:00'))-datetime.fromisoformat(event['start'].replace('Z','+00:00'))).total_seconds()/60)
            r.state['timeframe']=str(minutes)+'m'
            r.candle(event['start'],event['open'],event['high'],event['low'],event['close'])
        pending=s.get('pending',{}).get(key);position=s.get('positions',{}).get(key)
        if pending and outcome.get('status')=='signal':
            plan=dict(side=pending['side'],stop=pending['stop'],target=None,entry=None,time=event['available_at'])
            r.state['plan']=plan;r.event('plan',**plan)
        if position:r.state['plan']=dict(side=position['side'],entry=position['entry'],stop=position['stop'],target=position['target'],time=position['at'])
        if outcome.get('status') in ('entry','exit'):
            r.event(outcome['status'],time=event['available_at'],price=outcome['fill'],side=position['side'] if position else 0,
                quantity=outcome.get('quantity',1),pnl=outcome.get('net_pnl'),reason=outcome.get('reason',''))
            if outcome['status']=='exit':r.state['plan']=None
        r.update(balance=s['cash'],equity=s['equity'],progress=self.count/max(self.total,1),processed=self.count,total=self.total)
    def finish_trial(self, result):
        self.reporter.finish('completed' if result['status']!='failed' else 'failed',progress=1,summary=result.get('metrics',{}))
    def finish_experiment(self, result):
        if not self.reporter.state:return
        self.reporter.finish('failed' if result['status']=='blocked_or_failed' else 'completed',progress=1)

