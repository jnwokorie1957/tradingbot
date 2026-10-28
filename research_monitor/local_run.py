"""Finite causal CFD variation study with private, observed progress snapshots."""
import argparse, csv, hashlib, json, math, time
from collections import deque, Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .telemetry import Reporter
from trading_pipeline.engine_v4 import Engine,Hypothesis,Policy

NY=ZoneInfo('America/New_York')
def iso(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def up(v,tick):return math.ceil(v/tick-1e-8)*tick
def down(v,tick):return math.floor(v/tick+1e-8)*tick

def read_bars(path,offset):
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        rows=[]
        for row in csv.DictReader(f):
            rows.append(dict(t=int(row['time_epoch_mt5'])-offset*3600,open=float(row['open']),high=float(row['high']),low=float(row['low']),close=float(row['close']),spread=float(row['spread']),volume=int(row['tick_volume'])))
    if any(b['t']<=a['t'] for a,b in zip(rows,rows[1:])):raise ValueError('Price rows must be chronological and unique')
    return rows

def signals(native,symbol,minutes,lookback,filter_,end_clock=720):
    engine=object.__new__(Engine);engine.state={'bars':{},'pending':{},'positions':{}}
    engine.hypothesis=Hypothesis(family='pullback' if symbol=='NAS100' else 'breakout',lookback=lookback)
    engine.policy=Policy();out={};ema=None;history=deque(maxlen=6);previous=None;atr=None;true_ranges=[]
    for b in native:
        end=b['t']+minutes*60;at=datetime.fromtimestamp(end,timezone.utc);local=at.astimezone(NY)
        ema=b['close'] if ema is None else ema+(2/51)*(b['close']-ema);history.append(ema)
        tr=max(b['high']-b['low'],abs(b['high']-previous),abs(b['low']-previous)) if previous is not None else b['high']-b['low']
        previous=b['close'];true_ranges.append(tr)
        if len(true_ranges)==14:atr=sum(true_ranges)/14
        elif len(true_ranges)>14:atr=(13*atr+tr)/14
        e=dict(contract=symbol,start=iso(b['t']),end=iso(end),available_at=iso(end),**{k:b[k] for k in ('open','high','low','close','volume')})
        result=Engine._bar(engine,e,at,{})
        side=result['side'];clock=local.hour*60+local.minute
        trend=(side==1 and b['close']>ema and len(history)==6 and ema>history[0]) or (side==-1 and b['close']<ema and len(history)==6 and ema<history[0])
        width=b['high']-b['low'];location=(b['close']-b['low'])/width if width else .5
        strong=(side==1 and location>=.65) or (side==-1 and location<=.35)
        passes={'none':True,'ema50':trend,'close65':strong,'long_only':side==1,'close65_long':strong and side==1,
            'short_only':side==-1,'max_stop_atr':True,'short_range':side==-1}.get(filter_)
        if passes is None:raise ValueError('Unknown preregistered entry filter')
        if side and 600<=clock<=end_clock and passes:
            out[end]=dict(side=side,stop=b['low'] if side==1 else b['high'],reference=b['close'],decision=end,entry_at=end+60,atr14=atr)
    return out

def run_case(source,symbol,minutes,metadata,variant,phase,days,reporter,pace,queue_index,queue_total,stress=False):
    end_clock=variant.get('end_clock',720)
    one=source[(symbol,1)];native=source[(symbol,minutes)];sig=signals(native,symbol,minutes,variant['lookback'],variant['filter'],end_clock)
    chosen=set(days);rows=[]
    for b in one:
        local=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY);clock=local.hour*60+local.minute
        if str(local.date()) in chosen and 570<=clock<960:rows.append(b)
    tick=metadata['trade_tick_size'];mult=metadata['trade_tick_value_loss']/tick;slip=tick*(2 if stress else 1)
    spread_factor=1.5 if stress else 1;cash=500.;position=None;pending=None;busy=-1;fills=[];skips=Counter();peak=500.;dd=0.;risk=25.
    rid=f'{symbol}-{phase}-L{variant["lookback"]}-{variant["rr"]}-{variant["filter"]}-'+('wide' if stress else 'base')
    reporter.begin(rid,symbol,f'{minutes}m',('Pullback' if symbol=='NAS100' else 'Breakout')+(' · Morning session' if end_clock==720 else ' · Day session'),500,
        evidence='Historical simulation',phase=phase,queue_index=queue_index,queue_total=queue_total,assumptions='Isolated dollar ceiling; portfolio and daily halts not applied. Before commissions; margin unverified.')
    reporter.state.update(risk_cap=risk,rr=f'1:{variant["rr"]:g}',timeframe_minutes=minutes,
        variant=f'L{variant["lookback"]} · '+('EMA50' if variant['filter']!='none' else 'Unfiltered'),queue_index=queue_index,queue_total=queue_total)
    reporter.state['variant']='L'+str(variant['lookback'])+' · '+variant['filter'].replace('_',' ').title()
    def close(price,at,reason):
        nonlocal cash,position,busy
        p=position;fill=price-p['side']*slip;pnl=(fill-p['entry'])*p['side']*p['quantity']*mult
        cash+=pnl;R=(fill-p['entry'])*p['side']/p['distance'];fills.append(dict(entry_at=iso(p['at']),exit_at=iso(at),pnl=pnl,R=R,reason=reason,side=p['side'],entry_price=p['entry'],exit_price=fill,stop=p['stop'],target=p['target'],quantity=p['quantity'],initial_risk_points=p['distance']))
        reporter.state.update(balance=cash,equity=cash,plan=None)
        reporter.event('exit',time=iso(at),price=fill,side=p['side'],pnl=pnl,quantity=p['quantity'],reason=reason)
        position=None;busy=at
    for index,b in enumerate(rows):
        t=b['t'];now=t+60;spread=up(b['spread']*metadata['point']*spread_factor,tick)
        if pending and t>=pending['entry_at']:
            if t!=pending['entry_at']:skips['missing_entry']+=1
            elif not 600<=datetime.fromtimestamp(t,timezone.utc).astimezone(NY).hour*60+datetime.fromtimestamp(t,timezone.utc).astimezone(NY).minute<=end_clock:skips['entry_outside_window']+=1
            elif not position and pending['decision']>busy:
                side=pending['side'];entry=b['open']+(spread if side==1 else 0)+side*slip
                stop=down(pending['stop'],tick) if side==1 else up(pending['stop'],tick);distance=side*(entry-stop)
                perlot=(distance+slip)*mult;quantity=down(min(risk,max(cash,0))/perlot,metadata['volume_step']) if perlot>0 else 0
                if distance<tick-1e-8:skips['invalid_stop']+=1
                elif variant['filter'] in ('max_stop_atr','short_range') and (not pending.get('atr14') or distance/pending['atr14']>1.5):skips['oversized_stop_relative_to_volatility']+=1
                elif quantity<metadata['volume_min']-1e-8:skips['minimum_lot_above_cap']+=1
                else:
                    reward=down(variant['rr']*distance,tick)
                    local=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
                    flatten=int(local.replace(hour=15,minute=55,second=0,microsecond=0).timestamp())
                    position=dict(side=side,entry=entry,stop=stop,target=entry+side*reward,distance=distance,quantity=quantity,at=t,expiry=min(t+3600,flatten))
                    reporter.state['plan']=dict(side=side,entry=entry,stop=stop,target=position['target'],time=iso(t))
                    reporter.event('entry',time=iso(t),price=entry,side=side,quantity=quantity,stop=stop,target=position['target'])
            pending=None
            if position is None:reporter.state['plan']=None
        # Only the current M1 observation can trigger a fill; no future-bar lookup.
        if position:
            p=position;q=spread if p['side']==-1 else 0;op=b['open']+q;hi=b['high']+q;lo=b['low']+q;side=p['side']
            if (op<=p['stop'] if side==1 else op>=p['stop']):close(op,t,'stop_gap')
            elif t>=p['expiry']:close(op,t,'time_exit')
            elif (op>=p['target'] if side==1 else op<=p['target']):close(p['target'],t,'target')
            elif (lo<=p['stop'] if side==1 else hi>=p['stop']):close(p['stop'],now,'stop')
            elif (hi>=p['target'] if side==1 else lo<=p['target']):close(p['target'],now,'target')
        bucket=t//(minutes*60)*(minutes*60)
        candles=reporter.state['candles']
        if candles and candles[-1]['time']==bucket:
            c=candles[-1];reporter.candle(bucket,c['open'],max(c['high'],b['high']),min(c['low'],b['low']),b['close'])
        else:reporter.candle(bucket,b['open'],b['high'],b['low'],b['close'])
        if now in sig and not position and now>busy:
            pending=dict(sig[now]);reporter.state['plan']=dict(side=pending['side'],entry=None,stop=pending['stop'],target=None,time=iso(now))
            reporter.event('plan',time=iso(now),side=pending['side'],price=pending['reference'],stop=pending['stop'])
        equity=cash
        if position:
            executable=b['close']+(spread if position['side']==-1 else 0)-position['side']*slip
            equity+=(executable-position['entry'])*position['side']*position['quantity']*mult
        peak=max(peak,equity);dd=max(dd,(peak-equity)/peak)
        reporter.update(balance=cash,equity=equity,progress=(index+1)/max(len(rows),1),processed=index+1,total=len(rows),cursor_time=iso(now),closed_positions=len(fills))
        if pace:time.sleep(pace)
    status='completed' if position is None else 'incomplete'
    wins=sum(f['R']>0 for f in fills);sumR=sum(f['R'] for f in fills)
    result=dict(id=rid,symbol=symbol,variant=variant,phase=phase,stress=stress,status=status,
        outcomes=len(fills),win_rate=100*wins/len(fills) if fills else None,sum_R=sumR,mean_R=sumR/len(fills) if fills else None,
        ending_balance_before_fees=cash,drawdown_pct=dd*100,skips=dict(skips),qualified=False,broker_execution_enabled=False)
    reporter.finish(status,balance=cash,equity=cash,progress=1,summary=result)
    return result

def main():
    p=argparse.ArgumentParser(description='Finite local CFD variation study')
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,default=Path(__file__).resolve().parents[1]/'local-results/research-monitor')
    p.add_argument('--pace',type=float,default=.002);args=p.parse_args()
    metadata=json.loads(args.metadata.read_text());source={}
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for tf in [1,minutes]:source[(symbol,tf)]=read_bars(args.data_dir/f'{symbol}_M{tf}_30days.csv',3)
    days=sorted({str(datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).date()) for b in source[('NAS100',1)] if 570<=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).hour*60+datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).minute<960})
    variants=[dict(lookback=n,rr=rr,filter=f) for n in [10,30] for rr in [1.,1.5] for f in ['none','ema50']]
    args.state_dir.mkdir(parents=True,exist_ok=True)
    protocol=dict(created_utc=datetime.now(timezone.utc).isoformat(),variants=variants,development_days=days[:15],later_days=days[15:],
        selection='Highest development meanR among >=10 outcomes; otherwise most outcomes. Exploratory selection only, not qualification.',
        data_exposure='All prices previously inspected; later block is reused and not an untouched holdout.',cap=25,starting_balance=500,
        execution='Isolated cap-only simulation. Natural stops, current lot increments, assumed UTC+3, before unknown fees and margin. Current M1 events only. Entry60seconds after completed native signal; stop first for ambiguous bars.',
        source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.data_dir.glob('*.csv')})
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');record=args.state_dir/('batch-'+stamp+'.json')
    record.write_text(json.dumps(dict(protocol=protocol,results=[]),indent=2))
    reporter=Reporter(args.state_dir);results=[];selected={};total=20;current=0
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for variant in variants:
            current+=1;result=run_case(source,symbol,minutes,metadata[symbol],variant,'Development',days[:15],reporter,args.pace,current,total)
            results.append(result);record.write_text(json.dumps(dict(protocol=protocol,results=results),indent=2));print(json.dumps(result),flush=True)
        choices=[r for r in results if r['symbol']==symbol and r['outcomes']>=10]
        if choices:best=max(choices,key=lambda r:(r['mean_R'],r['outcomes']))
        else:best=max([r for r in results if r['symbol']==symbol],key=lambda r:r['outcomes'])
        selected[symbol]=best['variant']
    # Freeze both variants before the reused later-period checks.
    protocol['selection_frozen']=selected;record.write_text(json.dumps(dict(protocol=protocol,results=results),indent=2))
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for stress in [False,True]:
            current+=1;result=run_case(source,symbol,minutes,metadata[symbol],selected[symbol],'Later period',days[15:],reporter,args.pace,current,total,stress)
            results.append(result);record.write_text(json.dumps(dict(protocol=protocol,results=results),indent=2));print(json.dumps(result),flush=True)
    reporter.finish('completed',batch_complete=True,batch_results=[{k:r[k] for k in ('symbol','variant','phase','stress','outcomes','win_rate','ending_balance_before_fees','qualified')} for r in results])
    print('Finite batch complete. '+str(record),flush=True)

if __name__=='__main__':main()
