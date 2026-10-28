"""Re-run the two prior dollar-cap leaders without selecting new parameters."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from .local_run import read_bars,run_case,NY
from .telemetry import Reporter

def main():
    p=argparse.ArgumentParser(description='Finite priority comparison')
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True);p.add_argument('--pace',type=float,default=.001)
    args=p.parse_args();args.state_dir.mkdir(parents=True,exist_ok=True)
    variants={'NAS100':dict(lookback=20,rr=1.,filter='none',end_clock=720),'SPX500':dict(lookback=20,rr=2.,filter='none',end_clock=900)}
    protocol=dict(created_utc=datetime.now(timezone.utc).isoformat(),variants=variants,
        purpose='Direct causal re-run of prior NAS morning1R and SPX original2R dollar-cap leaders; no parameter tuning.',
        sample='Same consumed30day sample. No independent validation claim. Isolated25dollar ceiling, before unknown commissions; margin/clock unverified.')
    record=args.state_dir/'priority-results.json';record.write_text(json.dumps(dict(protocol=protocol,status='running',results=[]),indent=2))
    meta=json.loads(args.metadata.read_text());source={}
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for tf in [1,minutes]:source[(symbol,tf)]=read_bars(args.data_dir/f'{symbol}_M{tf}_30days.csv',3)
    days=sorted({str(datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).date()) for b in source[('NAS100',1)] if 570<=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).hour*60+datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).minute<960})
    reporter=Reporter(args.state_dir);results=[];index=0
    for symbol,minutes in [('NAS100',5),('SPX500',15)]:
        for stress in [False,True]:
            index+=1;r=run_case(source,symbol,minutes,meta[symbol],variants[symbol],'Priority comparison',days,reporter,args.pace,index,4,stress)
            results.append(r);record.write_text(json.dumps(dict(protocol=protocol,status='running',results=results),indent=2));print(json.dumps(r),flush=True)
    record.write_text(json.dumps(dict(protocol=protocol,status='completed',results=results),indent=2));reporter.finish('completed',batch_complete=True)
    print('Priority comparison complete.',flush=True)

if __name__=='__main__':main()
