"""Finite winner/loss hypothesis follow-up, retaining the original entry rules."""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
from .local_run import read_bars,run_case,NY
from .telemetry import Reporter

def main():
    p=argparse.ArgumentParser(description='Finite entry-quality follow-up')
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True);p.add_argument('--after-file',type=Path);p.add_argument('--pace',type=float,default=.002)
    args=p.parse_args();args.state_dir.mkdir(parents=True,exist_ok=True)
    filters={'NAS100':['none','close65','long_only','close65_long'],'SPX500':['none','short_only','max_stop_atr','short_range']}
    protocol=dict(registered_utc=datetime.now(timezone.utc).isoformat(),filters=filters,lookback=20,rr=1.,cap=25,
        reasons={'NAS100':'Prior morning development entries closing in the directional outer35% of their candle won5of6, versus2of5 elsewhere. Longs won4of5, shorts3of6. Tiny, post-hoc samples; no qualification.',
                 'SPX500':'Prior morning development shorts won8of12 versus4of7 longs; losing entries had a larger median stop/ATR. Test a fixed1.5ATR maximum and direction separately; do not transfer the NAS candle filter.'},
        controls='Original1R morning comparator retained. Structural stops unchanged; dollar cap25; before commissions. Lookback20 frozen. No parameter search on the later block.',
        selection='Development only, highest meanR with >=8 outcomes; otherwise most outcomes. This is an exploratory comparison, not the separate300-trade qualification screen.',
        limitations='All observations previously inspected; tiny strata, multiple comparisons, costs/margins/clock unverified; no independent validation claim.')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');record=args.state_dir/('entry-review-'+stamp+'.json')
    record.write_text(json.dumps(dict(protocol=protocol,status='queued',results=[]),indent=2))
    if args.after_file:
        deadline=time.monotonic()+1800
        while True:
            try:prior=json.loads(args.after_file.read_text());done=prior.get('status')=='completed' or len(prior.get('results',[]))>=20
            except (OSError,ValueError):done=False
            if done:break
            if time.monotonic()>deadline:raise TimeoutError('Prior batch did not finish within30minutes')
            time.sleep(2)
    meta=json.loads(args.metadata.read_text());source={}
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for tf in [1,minutes]:source[(symbol,tf)]=read_bars(args.data_dir/f'{symbol}_M{tf}_30days.csv',3)
    days=sorted({str(datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).date()) for b in source[('NAS100',1)] if 570<=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).hour*60+datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).minute<960})
    protocol.update(development_days=days[:15],later_days=days[15:]);reporter=Reporter(args.state_dir);results=[];selected={};current=0;total=12
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for filter_ in filters[symbol]:
            current+=1;variant=dict(lookback=20,rr=1.,filter=filter_)
            result=run_case(source,symbol,minutes,meta[symbol],variant,'Entry review',days[:15],reporter,args.pace,current,total)
            results.append(result);record.write_text(json.dumps(dict(protocol=protocol,status='running',results=results),indent=2));print(json.dumps(result),flush=True)
        group=[r for r in results if r['symbol']==symbol];eligible=[r for r in group if r['outcomes']>=8]
        best=max(eligible,key=lambda r:r['mean_R']) if eligible else max(group,key=lambda r:r['outcomes'])
        selected[symbol]=best['variant']
    protocol['selection_frozen']=selected;record.write_text(json.dumps(dict(protocol=protocol,status='running',results=results),indent=2))
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for stress in [False,True]:
            current+=1;result=run_case(source,symbol,minutes,meta[symbol],selected[symbol],'Later review',days[15:],reporter,args.pace,current,total,stress)
            results.append(result);record.write_text(json.dumps(dict(protocol=protocol,status='running',results=results),indent=2));print(json.dumps(result),flush=True)
    record.write_text(json.dumps(dict(protocol=protocol,status='completed',results=results),indent=2));reporter.finish('completed',batch_complete=True)
    print('Entry-quality batch complete. '+str(record),flush=True)

if __name__=='__main__':main()
