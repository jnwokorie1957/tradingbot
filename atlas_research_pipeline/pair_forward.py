"""Finite, frozen two-lane prospective receipt-clock PAPER replay.

Reads the existing collector's archive. No MT5 import, connection, order routing,
authentication, worker restart, or modification of the active paper books.
"""
import argparse
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from atlas_exit_research.data import NY, sha, stamp, write
from research_monitor.atlas_capture_inputs import load, build_lane
from research_monitor.atlas_metrics import metrics
from research_monitor.atlas_nas15_prospective import groups, read_only, received_minutes, cutoff_now
from research_monitor.atlas_opportunity_study import COSTS
from research_monitor.atlas_portfolio_controller import APPROVED
from research_monitor.native_data import aggregate
from .forward_core import PairedPaperBook, LedgerAudit, windows, availability_prefix, signal_available

FOLDER='atlas_pair_prospective_v1'
PROFILES={'control_60':60,'nas_90':90}
COST_NAMES=('standard','higher','severe')
SYMBOLS=('SPX500','NAS100')
POLICY=dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True,direction_guard=True)


def identity(pid):
    """Actual Windows process creation identity; status PID alone is insufficient."""
    command=f"Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' | Select-Object ProcessId,ParentProcessId,@{{Name='creation_utc';Expression={{$_.CreationDate.ToUniversalTime().ToString('o')}}}},ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    r=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)if r.stdout.strip()else None


def collector_health(state):
    s=json.loads((state/'status.json').read_text());actual=identity(s['worker_pid']);age=(datetime.now(timezone.utc)-datetime.fromisoformat(s['last_poll_utc'])).total_seconds()
    matches=bool(actual and 'research_monitor.atlas_forward_service'in actual['CommandLine']and 'atlas-forward-v2'in actual['CommandLine']and '--port 8878'in actual['CommandLine'])
    return dict(at_utc=stamp(),actual_process=actual,poll_age_seconds=age,identity_matches_expected_command=matches,fresh_status=0<=age<=90,status=s['status'],paper_only=s['paper_only'],broker_execution_calls=s['broker_execution_calls'],liveness_does_not_certify_coverage=True),s


def next_weekday(now):
    day=now.astimezone(NY).date()+timedelta(days=1)
    while day.weekday()>=5:day+=timedelta(days=1)
    return datetime.combine(day,datetime.min.time(),tzinfo=NY)


def freeze(root,folder):
    if folder.exists():raise ValueError('Prospective folder already exists; never refreeze or replace a cohort')
    state=root/'work/tradingbot/local-results/atlas-forward-v2';health,status=collector_health(state)
    assert health['identity_matches_expected_command']and health['fresh_status']and health['paper_only']and health['broker_execution_calls']==0
    assert health['status']=='observing_paper_forward'
    original=json.loads((state/'freeze.json').read_text());repo=root/'work/tradingbot'
    for name,h in original['source_hashes'].items():assert sha(repo/('trading_pipeline'if name=='engine_v4.py'else'research_monitor')/name)==h,name
    offsets={s:c['offset_hours']for s,c in status['clock'].items()}
    assert set(offsets)==set(SYMBOLS)and all(v is not None for v in offsets.values())
    # Verify synthetic execution/causality/arithmetic checks before freezing.
    checked=subprocess.run([os.sys.executable,'-m','atlas_research_pipeline.checks_forward'],cwd=repo,capture_output=True,text=True)
    if checked.returncode:raise ValueError(checked.stdout+checked.stderr)
    folder.mkdir(parents=True,exist_ok=False);known=datetime.now(timezone.utc).timestamp();warmup={s:[]for s in SYMBOLS};db=read_only(state/'observations.sqlite')
    for symbol,t,payload in db.execute('SELECT symbol,t,payload FROM minutes WHERE t+65<=? ORDER BY t',(known,)):
        if symbol in warmup:warmup[symbol].append(json.loads(payload))
    db.close();write(folder/'warmup_receipts.json',warmup)
    sources=list((repo/'research_monitor').glob('*.py'))+list((repo/'atlas_exit_research').glob('*.py'))+[repo/'trading_pipeline/engine_v4.py']
    sources += [repo/'atlas_research_pipeline'/n for n in ['__init__.py','forward_core.py','pair_forward.py','checks_forward.py']]
    source_hashes={str(p.relative_to(root)):sha(p)for p in sorted(set(sources))}
    historical=[]
    for rel in ['nas100_quote_data_v1','spx15_canonical_quote_data_v1','spx15_direction_later_v1/data']:
        d=root/'outputs'/rel;historical+=list(d.glob('*.csv'));historical += [p for p in [d/'manifest.json',d/'metadata.json']if p.exists()]
    historical+=[root/'work/mt5_symbol_metadata.json']
    evidence=root/'outputs/atlas_pair_holding_v1';preserved=[evidence/n for n in ['protocol.json','selection.json','results.json','completed.json','independent_audit.json']if(evidence/n).exists()]
    now=datetime.now(timezone.utc);start=next_weekday(now)
    protocol=dict(frozen_utc=now.isoformat(),freeze_epoch=now.timestamp(),financial_start_utc=start.astimezone(timezone.utc).isoformat(),financial_start_epoch=start.timestamp(),profiles=PROFILES,costs={c:COSTS[c]for c in COST_NAMES},risk=APPROVED,policy=POLICY,
        strategy_identity={'SPX15':'Original confirmed long breakout15m,1.5R,60minute expiry','NAS15':'Original selective long breakout15m/recoveryefficiency,2R,60 versus90minute expiry'},
        holding='Actual receipt entry plus60/90minutes,capped16:00NY. Original entries,natural stops,recovery filters,60second entrydelay and5second eligibility window unchanged.',
        offset_hours=offsets,metadata=status['symbol_metadata'],collector_database=str((state/'observations.sqlite').relative_to(root)),collector_freeze_sha256=sha(state/'freeze.json'),collector_creation_identity=health['actual_process'],
        source_sha256=source_hashes,historical_warmup_input_sha256={str(p.relative_to(root)):sha(p)for p in historical},warmup_sha256=sha(folder/'warmup_receipts.json'),development_evidence_sha256={str(p.relative_to(root)):sha(p)for p in preserved},
        information_clock='FIRST COLLECTOR RECEIPT,not evaluator walltime or source-time hypothetical availability. Every prior postfreeze indicator input must have arrived. Minutes finalize65seconds after source start and never revise. Historical/prefreeze prices and all observations before financialstart are warmup only.',
        execution='One last fresh sourcequote per symbol/receipt admits intents. Received sourceordered postentry paths manage stops/targets only at receipt,using adverse observed crossing-to-receipt price;profits cappedtarget. Severe1second exitdelay honored. Stale batches cannot fill;pending paths waitfor freshquote. Losses never clipped to plannedstop.',
        data_gate='At least5NEW complete NYSE-reference weekday windows;both symbols>=99percent expected RTHminutes. Expected missing sessions remain visible and disqualify cohort. Calendar is reference,not CFD venue certification. Maximum observed sourcegap>60seconds whileposition open or incomplete liquidation disqualifies.',
        comparison_gate='At least20covered sessions,50portfolio and30NAS closedtrades EACHcost;positive candidate net afterallcosts,portfolio andNAS net>=control,receiptDD andconservative observedpathDDbound<=control and<10percent,>=75percent control tradecapture. No WRtarget,no refit/reselection. Not a deployment instruction.',
        drawdown='Receiptmarked equity independently reconstructed;observed intrabatch pathrange gives conservative drawdown upperbound,not exact synchronized fulltickDD. Missing/unreceived paths and brokerliquidity cannot be bounded.',
        cadence='Score only after5NEW sufficientlycovered complete sessions. Cumulative expanding cohort,not independent repeated validations. No rerun unchanged batches;failed records preserved;never restart/refit or reset cohort automatically.',
        known_uncertainty=['CFD commission proxy,not verified account fees','Historical serverclock/DST and venuehours unverified;current clock frozen','Marginproxy,liquidity,orderacceptance and adversefills unverified','No actual orders or brokerfills;new receiptclock paper replay only','Stop and entrypause thresholds do not guarantee realized loss or drawdown'],
        calendar_reference='https://www.nyse.com/trade/hours-calendars',paper_only=True,active_paper_changed=False,deployment=False)
    write(folder/'protocol.json',protocol);write(folder/'protocol_identity.json',dict(sha256=sha(folder/'protocol.json')));write(folder/'preflight.json',dict(checked_utc=stamp(),exit_code=0,output=checked.stdout+checked.stderr,financial_observations_scored=0));write(folder/'collector_health_at_freeze.json',health);write(folder/'progress.json',dict(status='frozen_waiting_new_sessions',last_scored_sessions=[],last_batch=None,financial_observations_scored=0));print(json.dumps(dict(status='frozen_waiting_new_sessions',frozen_utc=protocol['frozen_utc'],financial_start_utc=protocol['financial_start_utc'],protocol_sha256=sha(folder/'protocol.json'),active_paper_changed=False)))


def verify(root,folder):
    p=json.loads((folder/'protocol.json').read_text());assert sha(folder/'protocol.json')==json.loads((folder/'protocol_identity.json').read_text())['sha256'];assert sha(folder/'warmup_receipts.json')==p['warmup_sha256'];assert p['risk']==APPROVED and p['policy']==POLICY and p['profiles']==PROFILES and p['paper_only']and not p['deployment']
    for mapping in ['source_sha256','historical_warmup_input_sha256','development_evidence_sha256']:
        for path,h in p[mapping].items():assert sha(root/path)==h,path
    state=(root/p['collector_database']).parent;assert sha(state/'freeze.json')==p['collector_freeze_sha256'];status=json.loads((state/'status.json').read_text())
    assert {s:v['offset_hours']for s,v in status['clock'].items()}==p['offset_hours'],'Frozen receipt/sourceclock changed;preserve cohort and seek review'
    for symbol,meta in p['metadata'].items():
        for field in ['trade_tick_size','trade_tick_value_loss','trade_contract_size','volume_min','volume_step']:assert abs(status['symbol_metadata'][symbol][field]-meta[field])<1e-8,'Contract metadata changed'
    return p


def availability(root,folder,p,through):
    source=read_only(root/p['collector_database']);observed={s:{}for s in SYMBOLS};start=int(p['financial_start_epoch']*1000);end=int(through*1000)
    if end>=start:
        for symbol,rawminute in source.execute('SELECT symbol,raw_ms/60000 FROM quotes WHERE receipt_ms>=? AND receipt_ms<=? GROUP BY symbol,raw_ms/60000',(start,end)):
            t=int(rawminute)*60-p['offset_hours'][symbol]*3600
            if t>=p['financial_start_epoch']:observed[symbol][t]=None
    source.close();covered=windows(p['financial_start_epoch'],through,observed);progress=json.loads((folder/'progress.json').read_text());new=[d for d in covered['covered_sessions']if d not in progress['last_scored_sessions']];health,_=collector_health((root/p['collector_database']).parent)
    expected=p['collector_creation_identity'];health['matches_frozen_creation']=bool(health['actual_process']and health['actual_process']['ProcessId']==expected['ProcessId']and health['actual_process']['creation_utc']==expected['creation_utc'])
    value=dict(status='waiting_new_completed_sessions',at_utc=stamp(),through_utc=datetime.fromtimestamp(through,timezone.utc).isoformat(),financial_start_utc=p['financial_start_utc'],coverage=covered,new_complete_sessions=len(new),minimum_new_sessions=5,last_scored_sessions=progress['last_scored_sessions'],collector_health=health,financial_observations_scored=progress.get('financial_observations_scored',0),new_source='Genuinely new firstreceipts afterfreeze;not MT5history backfill',active_paper_changed=False)
    write(folder/'availability.json',value);return value


def snapshot(root,p,through,batch):
    source=read_only(root/p['collector_database']);dest=sqlite3.connect(batch/'received_quotes.sqlite');dest.execute('CREATE TABLE quotes(seq INTEGER PRIMARY KEY,symbol TEXT,raw_ms INTEGER,bid REAL,ask REAL,occurrence INTEGER,receipt_ms INTEGER)');cursor=source.execute('SELECT rowid,symbol,raw_ms,bid,ask,occurrence,receipt_ms FROM quotes WHERE receipt_ms>=? AND receipt_ms<=? ORDER BY rowid',(int(p['freeze_epoch']*1000),int(through*1000)));count=0
    while True:
        rows=cursor.fetchmany(10000)
        if not rows:break
        dest.executemany('INSERT INTO quotes VALUES(?,?,?,?,?,?,?)',rows);count+=len(rows)
    source.close();dest.commit();dest.close();return batch/'received_quotes.sqlite',count


def replay(root,folder,p,through):
    batch=folder/'batches'/datetime.fromtimestamp(through,timezone.utc).strftime('%Y%m%dT%H%M%SZ');batch.mkdir(parents=True,exist_ok=False);write(batch/'started.json',dict(at_utc=stamp(),protocol_sha256=sha(folder/'protocol.json'),pid=os.getpid()))
    try:
        path,count=snapshot(root,p,through,batch);db=read_only(path);start_ms=int(p['freeze_epoch']*1000);end_ms=int(through*1000);points={s:m.get('point',m['trade_tick_size'])for s,m in p['metadata'].items()};minutes,available,late=received_minutes(groups(db,start_ms,end_ms),p['offset_hours'],p['freeze_epoch'],points);coverage=windows(p['financial_start_epoch'],through,minutes);progress=json.loads((folder/'progress.json').read_text());new=[d for d in coverage['covered_sessions']if d not in progress['last_scored_sessions']];write(batch/'coverage.json',coverage)
        if len(new)<5:raise ValueError('Finalized minute coverage failed the five-new-session gate;no financial scoring')
        all_lanes,meta,_,old_one,_=load(root);warmup=json.loads((folder/'warmup_receipts.json').read_text());lanes={}
        for name in ['SPX15','NAS15']:
            base=dict(all_lanes[name],rr=1.5 if name=='SPX15'else 2.);s=base['symbol'];combined={b['t']:b for b in old_one[s]};combined.update({b['t']:b for b in warmup[s]});combined.update(minutes[s]);one=[b for _,b in sorted(combined.items())];lanes[name]=build_lane(s,15,one,aggregate(one,15),base,True);meta[s].update(p['metadata'][s])
        plans=[];unavailable=[]
        for name,lane in lanes.items():
            symbol=lane['symbol'];times,prefix=availability_prefix(minutes[symbol],available[symbol],p['freeze_epoch'])
            for t,s in lane['signals'].items():
                if not p['financial_start_epoch']<=t<=through:continue
                seen=signal_available(t,times,prefix,available[symbol],p['freeze_epoch'])
                if seen is None:unavailable.append(dict(lane=name,decision=t,reason='missing_complete_signal_minutes'));continue
                plans.append((seen,t,name,s))
        plans.sort(key=lambda x:(x[0],x[1],0 if x[2]=='SPX15'else 1));write(batch/'unavailable_setups.json',unavailable)
        clean={n:dict(l,signals={},exits=[])for n,l in lanes.items()};books={(n,c):PairedPaperBook(clean,meta,POLICY,COSTS[c],5000.,nas_minutes=duration)for n,duration in PROFILES.items()for c in COST_NAMES};audits={key:LedgerAudit(meta,COSTS[key[1]])for key in books};nas_audits={key:LedgerAudit(meta,COSTS[key[1]])for key in books};cursor=0;buffer={s:[]for s in SYMBOLS};stale=0
        for receipt,rows in groups(db,start_ms,end_ms):
            while cursor<len(plans)and plans[cursor][0]<=receipt:
                _,_,name,s=plans[cursor];cursor+=1
                for b in books.values():b.enqueue(name,s)
            paths={s:sorted([(r[2]/1000-p['offset_hours'][s]*3600,r[3],r[4])for r in rows if r[1]==s])for s in SYMBOLS}
            if any(t>receipt+1 or bid<=0 or ask<bid for pp in paths.values()for t,bid,ask in pp):raise ValueError('Invalid quote or frozen sourceclock mismatch')
            for a in audits.values():a.path_bound(paths,receipt)
            for a in nas_audits.values():a.path_bound(paths,receipt)
            for symbol in SYMBOLS:
                buffer[symbol]+=paths[symbol]
                if not paths[symbol]:continue
                source_at,bid,ask=paths[symbol][-1]
                if not -1<=receipt-source_at<=5:stale+=1;continue
                retained=sorted(buffer[symbol]);buffer[symbol]=[]
                for key,b in books.items():
                    b.observed_path(symbol,receipt,bid,ask,retained);b.quote(symbol,receipt,bid,ask,source_time=source_at);audits[key].point(b,symbol,bid,ask)
                    # NAS contribution uses its own independent5000USD reference equity.
                    a=nas_audits[key];proxy=type('Contribution',(),{})();proxy.lanes=b.lanes;proxy.decisions=[r for r in b.decisions if r.get('lane')=='NAS15'];proxy.fills=[f for f in b.fills if f['strategy']=='NAS15'];proxy.cash=5000.+sum(f['pnl']for f in proxy.fills);proxy.equity=lambda b=b,proxy=proxy:proxy.cash+sum(a.floating(dict(symbol=p0['symbol'],entry=p0['entry'],side=p0['side'],quantity=p0['quantity']),b.latest[p0['symbol']][0],b.latest[p0['symbol']][0]+(b.latest[p0['symbol']][1]-b.latest[p0['symbol']][0])/b.cost['spread'])for p0 in b.positions.values()if p0['lane']=='NAS15');a.point(proxy,symbol,bid,ask)
        db.close();records=[];first=datetime.fromtimestamp(p['financial_start_epoch'],timezone.utc).astimezone(NY).date().isoformat();end=(datetime.fromtimestamp(through,timezone.utc).astimezone(NY).date()+timedelta(days=1)).isoformat()
        for (name,cost),b in books.items():
            b.finish();fills=sorted(b.fills,key=lambda f:f['exit_at']);r=dict(profile=name,cost=cost,account=b.result(),portfolio=metrics(fills,5000.,first,end),nas15=metrics([f for f in fills if f['strategy']=='NAS15'],5000.,first,end),spx15=metrics([f for f in fills if f['strategy']=='SPX15'],5000.,first,end),audit=audits[name,cost].result(),nas_audit=nas_audits[name,cost].result(),maximum_observed_position_source_gap_seconds=max([f['maximum_observed_source_gap_seconds']for f in fills]+[p0.get('_max_source_gap',0.)for p0 in b.positions.values()]+[0.]),actual_broker_fills=False,independent_new_observations=True)
            records.append(r);write(batch/f'private_fills_{name}_{cost}.json',fills);write(batch/f'private_decisions_{name}_{cost}.json',b.decisions);write(batch/f'private_open_positions_{name}_{cost}.json',b.positions)
        gate={};sample=len(coverage['covered_sessions'])>=20;complete=not coverage['uncovered_sessions']and all(r['account']['open_positions']==0 and r['maximum_observed_position_source_gap_seconds']<=60 for r in records)
        for cost in COST_NAMES:
            old=next(r for r in records if r['profile']=='control_60'and r['cost']==cost);newr=next(r for r in records if r['profile']=='nas_90'and r['cost']==cost);capture=newr['portfolio']['trades']/old['portfolio']['trades']if old['portfolio']['trades']else None;g=dict(complete_paths_and_sessions=complete,meaningful_sample=sample and newr['portfolio']['trades']>=50 and newr['nas15']['trades']>=30,positive_net=newr['portfolio']['net_pnl']>0,portfolio_net_no_lower=newr['portfolio']['net_pnl']>=old['portfolio']['net_pnl'],nas_net_no_lower=newr['nas15']['net_pnl']>=old['nas15']['net_pnl'],capture=capture is not None and capture>=.75)
            for key in ['receipt_marked_drawdown_pct','conservative_observed_path_drawdown_bound_pct']:
                for field in ['audit','nas_audit']:g[field+'_'+key]=newr[field][key]<=old[field][key]+1e-9 and newr[field][key]<10
            gate[cost]=dict(checks=g,passed=all(g.values()),trade_capture=capture)
        write(batch/'results.json',records);write(batch/'comparison.json',dict(costs=gate,all_costs_pass=all(g['passed']for g in gate.values()),scope='Cumulative genuinely postfreeze receiptclock replay,hypothetical fills;not actual executions or repeated independent cohorts',deployment=False));write(batch/'completed.json',dict(at_utc=stamp(),protocol_sha256=sha(folder/'protocol.json'),snapshot_sha256=sha(path),quotes=count,covered_sessions=coverage['covered_sessions'],uncovered_sessions=coverage['uncovered_sessions'],late_quotes_not_revising_bars=late,stale_batches_no_fills=stale,qualified_paths=complete,all_costs_pass=all(g['passed']for g in gate.values()),active_paper_changed=False));write(folder/'progress.json',dict(status='waiting_new_completed_sessions'if complete else 'evidence_failure_requires_review',last_scored_sessions=coverage['covered_sessions'],last_batch=str(batch.relative_to(root)),financial_observations_scored=count));print(json.dumps(dict(batch=str(batch),costs=gate,qualified_paths=complete)))
    except Exception as e:
        write(batch/'failure.json',dict(at_utc=stamp(),error=repr(e),preserve_all_artifacts=True,automatic_restart=False));prior=json.loads((folder/'progress.json').read_text());write(folder/'progress.json',dict(prior,status='evaluation_failed_requires_review',failed_batch=str(batch.relative_to(root))));raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--freeze',action='store_true');parser.add_argument('--status',action='store_true');args=parser.parse_args();root=args.root.resolve();folder=root/'outputs'/FOLDER
    if args.freeze:
        if args.status:parser.error('Choose freeze or status')
        freeze(root,folder);return
    p=verify(root,folder);through=cutoff_now();a=availability(root,folder,p,through)
    if args.status or a['new_complete_sessions']<5:print(json.dumps(a));return
    progress=json.loads((folder/'progress.json').read_text())
    if progress['status']in ['evidence_failure_requires_review','evaluation_failed_requires_review']:raise ValueError('Prior evidence failure requires review;cohort must not silently continue')
    if not a['collector_health']['matches_frozen_creation']:raise ValueError('Collector creation identity differs;preserve cohort and seek review')
    lock=folder/'evaluator.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps(dict(pid=os.getpid(),started_utc=stamp())).encode());os.close(fd)
    try:replay(root,folder,p,through)
    finally:lock.unlink(missing_ok=True)


if __name__=='__main__':main()
