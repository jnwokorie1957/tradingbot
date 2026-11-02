"""Frozen benchmark frequency ledger and bounded causal opportunity/risk proposals."""
import argparse,copy,gc,hashlib,heapq,json,os,shutil
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from .atlas_capture_core import PaperBook
from .atlas_capture_inputs import load,build_lane
from .portfolio_inputs import load_quotes
from .atlas_capture_quotes import feasible_envelopes
from .atlas_metrics import metrics,weekdays,local_day
from .native_data import aggregate
from .audited_run import NY

CASES=[('frozen',{},500.,c) for c in ['standard','higher']]+[('queue_at_entry',dict(defer_busy_gate=True),500.,c) for c in ['standard','higher']]+[('capture_same_direction',dict(defer_busy_gate=True,allow_multiple=True,direction_guard=True),500.,c) for c in ['standard','higher']]+[(name,dict(governed=True,risk_pct=pct,defer_busy_gate=True,allow_multiple=True),capital,c) for name,pct,capital in [('governed_1pct',.01,500.),('governed_halfpct',.005,500.),('capital_2500_1pct',.01,2500.)] for c in ['standard','higher','severe']]
COSTS={'standard':dict(spread=1.,fee=6.,slip_ticks=1,exit_delay=0.,margin_multiplier=1.),'higher':dict(spread=1.5,fee=12.,slip_ticks=2,exit_delay=0.,margin_multiplier=1.),'severe':dict(spread=2.,fee=18.,slip_ticks=4,exit_delay=1.,margin_multiplier=2.)}


def frequencies(book):
    daily={d:{n:Counter() for n in book.lanes} for d in weekdays()};reasons={n:Counter() for n in book.lanes};qualified=Counter()
    for row in book.decisions:
        d=local_day(row['decision']);name=row['lane']
        if d not in daily:continue
        daily[d][name]['raw_setups']+=1;daily[d][name][row['status']]+=1;reasons[name][row['reason']]+=1
        if row.get('signal_qualified'):daily[d][name]['signal_qualified']+=1;qualified[name]+=1
    buckets={'weekly':{},'monthly':{}}
    for day,lanes in daily.items():
        dt=datetime.fromisoformat(day);iso=dt.isocalendar()
        for kind,key in [('weekly',f'{iso.year}-W{iso.week:02d}'),('monthly',day[:7])]:
            bucket=buckets[kind].setdefault(key,{n:Counter() for n in book.lanes})
            for n,count in lanes.items():bucket[n].update(count)
    totals={n:dict(sum((v[n] for v in daily.values()),Counter())) for n in book.lanes}
    return dict(daily=daily,**buckets,totals=totals,reasons=reasons,definitions='Raw=causal family signal before window/direction filters. Qualified=all noncapital entry rules passed on first entry quote. EXECUTED=paper entry,REJECTED=policy/feature, BLOCKED=occupancy/risk/margin/conflict/duplicate, MISSED=quotes/execution unavailable. Counts reconcile;unobserved candle slots imply unknown setups,not zero.',weekdays=len(daily),ISO_weeks=len(buckets['weekly']),calendar_months=len(buckets['monthly']))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root;out=root/'outputs/atlas_opportunity_v1';out.mkdir(exist_ok=False)
    source=Path(__file__).parent;protocol=dict(registered_utc=datetime.now(timezone.utc).isoformat(),objective='25-40percentannualizednet,portfolioDDbelow10;maximizevalidatedpositiveexpectancyopportunitycapture,not winrateortradecountalone',benchmark='Frozen recovery portfolio:SPX15confirmedlong1.5R,NAS15selectivelong1.5R/recoveryefficiency,NAS5shortRSI2nativeexits. No parameter edits.',dates=['2025-12-15','2026-10-30'],development=['2025-12-15','2026-05-31'],later='June-Oct already exposed;descriptive stability only,not untouchedvalidation',cases=[dict(name=n,policy=pol,initial=c,cost=cost) for n,pol,c,cost in CASES],costs=COSTS,
        counterfactuals='Queue intent until entry quote rather than drop at decision while busy. Allow unique same-direction entries if shared grossbudget permits;do not add opposite same-symbol exposure. No after-outcome cherry-picking or summing individuallyprofitablemisses. Replay entire account chronology and keep losses/skips.',
        governed='0.5/1percentplannedrisk variants;recoverymin(0.5percent,existing10USD),hard25USDtotal plus2percent-equitygrossindexbudget;no diversification/nettingcredit,50percentequitymarginbudget,8percentDDnewentryreview,legalminlot/step. No trade-countquota,loss-countdailyhalt or arbitrary cooldown. Sameassetopposite/duplicatesveto;sam_directionallowedsubjectrisk.',
        capital='500USDprimary.2500USDpaper-onlycapitalillustration preserves25dollarceiling at1percent-pertrade;not same-capital performance or a deposit request.',
        complement='NAS3 RSI2 range-regime abs(prior20 directional efficiency)<.30,short-only;fixedthreshold from existing context,not fit. Shadow standalone500,governed1percent,developmentonly,standard/higher;never replace currentthree or deploy from these results.',
        acceptance='All proposalsUNVALIDATED until unseenforwardevidence. MechanicalPASS requires exactfrozen56/46financialledgers,legalquantities,sharedrisk/margin,duplicate/directiontests. PerformancePASSrequires higher netexpectancy,opportunitycapture not below same-capital benchmark,unchangedbreakout1.5R,no tail/drawdown deterioration,DDbelow10standardandsevere,and genuinelyindependent evidence.75percentWRstretch only;smallhighWRsamplesfailqualification.',
        OOS='No eligibleunusedhistoricalperiod fromprioraudit;do not rebrandreusedprices. Startreceipt-timestampedreadonlyMT5paperforward aftercode/configfreeze,nohistoryreplayfills,no liveorders.',code_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in source.glob('*.py')},benchmark_sha256=hashlib.sha256((root/'outputs/portfolio_25_discipline_v1/results.json').read_bytes()).hexdigest())
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2));(out/'source').mkdir()
    for n in protocol['code_hashes']:shutil.copy2(source/n,out/'source'/n)
    state=dict(pid=os.getpid(),status='running',phase='load',completed=0,total=len(CASES)+2)
    def checkpoint():(out/'worker.json').write_text(json.dumps(state,indent=2))
    checkpoint();lanes,meta,folders,warmup,coverage=load(root);(out/'coverage.json').write_text(json.dumps(coverage,indent=2));sessions=load_quotes(folders);cache={};rows=[];refs=json.loads((root/'outputs/portfolio_25_discipline_v1/results.json').read_text())
    def quotes(active,delay):
        key=('shadow' if 'NAS3'in active else 'main',delay)
        if key in cache:return cache[key]
        result={}
        for symbol in {l['symbol'] for l in active.values()}:
            union={}
            for name,l in active.items():
                if l['symbol']!=symbol:continue
                for t,s in l['signals'].items():
                    local=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
                    if l['start']<=local.hour*60+local.minute<=l['end']:union[(t,name)]=s
            result[symbol],_=feasible_envelopes(sessions[symbol],union,meta[symbol],False,540,900,exit_delay=delay)
        cache[key]=result;return result
    def run(name,policy,capital,cost,active,scope='full'):
        state.update(phase='quote_replay',variant=name,cost=cost,scope=scope);checkpoint();book=PaperBook(active,meta,policy,COSTS[cost],capital);streams=[]
        def stream(symbol,data):
            for day,q,offset in data:
                if scope=='development' and day>='2026-06-01':continue
                for x in q:yield(float(x['time_msc'])/1000-offset*3600,0 if symbol=='SPX500' else 1,symbol,float(x['bid']),float(x['ask']))
        for symbol,q in quotes(active,COSTS[cost]['exit_delay']).items():streams.append(stream(symbol,q))
        for t,_,symbol,bid,ask in heapq.merge(*streams,key=lambda x:(x[0],x[1])):book.quote(symbol,t,bid,ask)
        if scope=='development':
            for lane in book.lanes:
                book.events[lane]=[e for e in book.events[lane] if local_day(e[0])<'2026-06-01']
        book.finish();r=book.result();assert not book.positions
        if name=='frozen':
            ref=next(x for x in refs if x['stage']=='full' and x['variant']=='nas15_eff_after2' and x['stress']==(cost=='higher'));expected=json.loads((root/f'outputs/portfolio_25_discipline_v1/private_fills_{ref["ledger"]}.json').read_text());assert len(expected)==len(book.fills) and all({k:f[k] for k in e}==e for f,e in zip(book.fills,expected)),('benchmarkfinancialparity',cost,len(book.fills),len(expected));assert abs(r['quote_drawdown_pct']-ref['quote_marked_drawdown_pct'])<1e-7;r['archived_parity']=True
        first,end=('2025-12-15','2026-06-01') if scope=='development' else ('2025-12-15','2026-10-31');r.update(name=name,policy=policy,cost=cost,scope=scope,metrics=metrics(book.fills,initial=capital,first=first,end=end),frequency=frequencies(book),per_strategy={n:metrics([f for f in book.fills if f['strategy']==n],initial=capital,first=first,end=end) for n in active},independent_validation=False)
        key=f'{len(rows)+1:02d}';r['ledger']=key;(out/f'fills_{key}.json').write_text(json.dumps(book.fills,indent=2));(out/f'rejections_{key}.json').write_text(json.dumps(book.decisions,indent=2));rows.append(r);(out/'results.json').write_text(json.dumps(rows,indent=2));state['completed']=len(rows);checkpoint();print(json.dumps({k:r[k] for k in ['name','cost','net_pnl','trades','win_rate','quote_drawdown_pct']}),flush=True);gc.collect()
    for name,policy,capital,cost in CASES:run(name,policy,capital,cost,lanes)
    template=dict(lanes['NAS5']);template['start']=600;template['end']=900;native=aggregate(warmup['NAS100'],3);shadow=build_lane('NAS100',3,warmup['NAS100'],native,template,False);shadow['signals']={t:s for t,s in shadow['signals'].items() if local_day(t)<'2026-06-01' and abs(s.get('features',{}).get('directional_efficiency',2.))<.30}
    for cost in ['standard','higher']:run('shadow_NAS3_range',dict(governed=True,risk_pct=.01,defer_busy_gate=True,allow_multiple=True),500.,cost,{'NAS3':shadow},'development')
    (out/'completed.json').write_text(json.dumps(dict(cases=len(rows),benchmark_preserved=True,independent_validation=False,performance_pass=False,reason='Unseen evidence required;no variant promoted on reused history.',objective='25-40percentannualnet;below10DD'),indent=2));state.update(status='completed',phase='complete');checkpoint()


if __name__=='__main__':main()
