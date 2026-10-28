"""Four checkpointed local workers with a deadline and no repeated data loops."""
import argparse,hashlib,itertools,json,multiprocessing as mp,os,time
from datetime import datetime,timezone
from pathlib import Path
from .local_run import read_bars,run_case,NY
from .telemetry import Reporter

LANES=[dict(id='nas-pullback',symbol='NAS100',minutes=5,family='pullback'),
       dict(id='nas-breakout',symbol='NAS100',minutes=15,family='breakout'),
       dict(id='spx-breakout',symbol='SPX500',minutes=15,family='breakout'),
       dict(id='spx-pullback',symbol='SPX500',minutes=5,family='pullback')]

def atomic(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2,allow_nan=False))
    for attempt in range(30):
        try:os.replace(temp,path);return
        except PermissionError:
            if attempt==29:raise
            time.sleep(.01)

def load_source(data_dir,lane):
    symbol=lane['symbol'];source={(symbol,n):read_bars(data_dir/f'{symbol}_M{n}_30days.csv',3) for n in [1,lane['minutes']]}
    days=[];closing=[]
    for b in source[(symbol,1)]:
        t=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY)
        if t.hour==15 and t.minute==59:closing.append(str(t.date()))
    complete_through=max(closing) if closing else ''
    days=sorted({str(datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).date()) for b in source[(symbol,1)]
        if 570<=datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).hour*60+datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).minute<960
        and str(datetime.fromtimestamp(b['t'],timezone.utc).astimezone(NY).date())<=complete_through})
    return source,days,complete_through

def worker(lane,data_dir,metadata,state_dir,deadline,stop,pace):
    folder=state_dir/'lanes'/lane['id'];folder.mkdir(parents=True,exist_ok=True);reporter=Reporter(folder)
    seen=None
    try:
        while not stop.is_set() and time.time()<deadline:
            source,days,version=load_source(data_dir,lane)
            if not version or len(days)<17:raise ValueError('At least17 dated sessions required')
            if version==seen:
                reporter.update(status='waiting',message='Awaiting a fresh completed market session');stop.wait(20);continue
            seen=version;record=folder/('batch-'+version+'.json')
            if record.exists():
                saved=json.loads(record.read_text());results=saved.get('results',[])
                if saved.get('status')=='completed':
                    reporter.begin(lane['id']+'-waiting',lane['symbol'],str(lane['minutes'])+'m',lane['family'].title(),500)
                    reporter.finish('waiting',message='Completed session already evaluated');continue
            else:
                results=[];saved=dict(protocol=dict(lane=lane,registered_utc=datetime.now(timezone.utc).isoformat(),
                    deadline_utc=datetime.fromtimestamp(deadline,timezone.utc).isoformat(),through_session=version,
                    lookbacks=[10,20,30],RR=[1.,1.5,2.],filters=['none','ema50','close65'],entry_cutoffs=[720,900],
                    selection='Development meanR among>=10 outcomes; otherwise most outcomes; not qualification.',
                    scope='Each lane separately starts at500. Isolated25dollar ceiling; unknown fees/margins/clock; no orders. Rolling sessions overlap and are never independent validation.',
                    development_days=days[:15],later_days=days[15:],
                    source_hashes={str(n):hashlib.sha256((data_dir/f'{lane["symbol"]}_M{n}_30days.csv').read_bytes()).hexdigest() for n in [1,lane['minutes']]}),results=results,status='running')
                atomic(record,saved)
            grid=[dict(lookback=n,rr=rr,filter=f,end_clock=end,family=lane['family']) for n,rr,f,end in itertools.product([10,20,30],[1.,1.5,2.],['none','ema50','close65'],[720,900])]
            total=len(grid)+2
            for index,variant in enumerate(grid,1):
                if stop.is_set() or time.time()>=deadline:stop.set();break
                if any(r['phase']=='Development' and r['variant']==variant and r['status']=='completed' for r in results):continue
                r=run_case(source,lane['symbol'],lane['minutes'],metadata[lane['symbol']],variant,'Development',days[:15],reporter,pace,index,total,stop_event=stop)
                results.append(r);saved.update(results=results);atomic(record,saved)
            if stop.is_set():break
            choices=[r for r in results if r['phase']=='Development' and r['outcomes']>=10 and r['status']=='completed']
            if not choices:choices=[r for r in results if r['phase']=='Development' and r['status']=='completed']
            best=max(choices,key=lambda r:(r['mean_R'] if r['mean_R'] is not None else -1e99,r['outcomes']))
            saved['selection_frozen']=best['variant'];atomic(record,saved)
            for number,stress in enumerate([False,True],len(grid)+1):
                if stop.is_set():break
                if any(r['phase']=='Later period' and r['stress']==stress and r['status']=='completed' for r in results):continue
                r=run_case(source,lane['symbol'],lane['minutes'],metadata[lane['symbol']],best['variant'],'Later period',days[15:],reporter,pace,number,total,stress,stop)
                results.append(r);saved['results']=results;atomic(record,saved)
            saved['status']='interrupted' if stop.is_set() else 'completed';atomic(record,saved)
            reporter.finish('waiting' if not stop.is_set() else 'paused',message='Awaiting fresh completed prices' if not stop.is_set() else 'Reset deadline reached')
    except Exception as error:
        reporter.finish('failed',message=type(error).__name__+': '+str(error));raise
    finally:
        if reporter.state and stop.is_set():reporter.finish('paused',message='Research deadline reached; checkpoint retained')

def main():
    p=argparse.ArgumentParser(description='Four local research lanes')
    p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True);p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--stop-at',required=True);p.add_argument('--pace',type=float,default=.001)
    args=p.parse_args();deadline=datetime.fromisoformat(args.stop_at.replace('Z','+00:00')).timestamp()
    if deadline<=time.time():raise ValueError('Deadline already reached')
    args.state_dir.mkdir(parents=True,exist_ok=True);pidfile=args.state_dir/'parallel-supervisor.json'
    if pidfile.exists():
        old=json.loads(pidfile.read_text())
        if old.get('status')=='running':raise RuntimeError('Supervisor checkpoint is marked active; inspect its process before recovery')
    metadata=json.loads(args.metadata.read_text());ctx=mp.get_context('spawn');stop=ctx.Event();processes=[]
    for lane in LANES:
        proc=ctx.Process(target=worker,args=(lane,args.data_dir,metadata,args.state_dir,deadline,stop,args.pace),name=lane['id']);proc.start();processes.append(proc)
    atomic(pidfile,dict(pid=os.getpid(),workers={lane['id']:proc.pid for lane,proc in zip(LANES,processes)},status='running',stop_at=args.stop_at))
    print(json.dumps(dict(supervisor=os.getpid(),workers={p.name:p.pid for p in processes},stop_at=args.stop_at)),flush=True)
    try:
        while time.time()<deadline and not (args.state_dir/'stop.request').exists():
            if any(p.exitcode is not None for p in processes):
                print('A lane exited; checkpoint available for health review.',flush=True)
                break
            time.sleep(2)
    except KeyboardInterrupt:pass
    finally:
        stop.set()
        for proc in processes:proc.join(10)
        for proc in processes:
            if proc.is_alive():proc.terminate();proc.join()
        atomic(pidfile,dict(pid=os.getpid(),workers={p.name:p.pid for p in processes},status='stopped',stop_at=args.stop_at))

if __name__=='__main__':main()
