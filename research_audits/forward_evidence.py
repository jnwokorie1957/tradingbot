"""Snapshot and audit the existing Atlas observer; no terminal/order interface.

Observational evidence only. This neither changes strategy rules nor creates a
second collector. It never treats an unfinished session as a validation fold.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
import hashlib,json,sqlite3,subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

NY=ZoneInfo('America/New_York')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def utc(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')


def complete_hours(times):
    buckets=defaultdict(list)
    for t in times:buckets[t//3600*3600].append(t)
    return [hour+3600 for hour,rows in sorted(buckets.items()) if rows==list(range(hour,hour+3600,60))]


def clock_windows(times,through):
    counts=Counter()
    for t in times:
        at=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
        if at.weekday()<5 and 570<=at.hour*60+at.minute<960:counts[at.date().isoformat()]+=1
    rows=[]
    for day,count in sorted(counts.items()):
        end=datetime.fromisoformat(day).replace(hour=16,minute=15,tzinfo=NY).timestamp();closed=end<=through
        rows.append(dict(date=day,observed_minutes=count,clock_window_complete=closed,sufficient_minutes=count>=351,eligible_completed_clock_window=closed and count>=351))
    return rows


def reconcile(book,initial,metadata,fee):
    fills=book['fills'];pnl=0.;ids=set();spx=[]
    for f in fills:
        assert f['id'] not in ids,'Duplicate closed financial intent';ids.add(f['id'])
        m=metadata[f['symbol']];mult=m['trade_tick_value_loss']/m['trade_tick_size'];step=m['volume_step'];q=f['quantity']
        assert q>=m['volume_min'] and abs(q/step-round(q/step))<1e-7,'Illegal current lot increment'
        value=((f['exit']-f['entry'])*f['side']*mult-fee)*q;assert abs(value-f['pnl'])<1e-6,'PnL/commission mismatch';pnl+=value
        assert f['planned_risk']<=25.+1e-7,'Planned per-trade dollar ceiling exceeded'
        if f['strategy']=='SPX15':
            distance=f['side']*(f['entry']-f['stop']);reward=f['side']*(f['target']-f['entry'])
            assert distance>0 and 0<=1.5*distance-reward<m['trade_tick_size']+1e-7,'SPX 1.5R identity mismatch';spx.append(f)
    assert abs(initial+pnl-book['cash'])<1e-6,'Ledger does not reconcile to cash'
    return dict(initial_equity=initial,closed_trades=len(fills),closed_spx_trades=len(spx),closed_spx_net=sum(f['pnl'] for f in spx),spx_win_rate=100*sum(f['pnl']>0 for f in spx)/len(spx) if spx else None,ending_balance=book['cash'],open_positions=len(book['positions']),quote_drawdown_pct=book['dd']*100,arithmetic='PASS',broker_fills=False)


def processes():
    command="Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -match '-m research_monitor\\.atlas_forward_service' } | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json -Depth 3"
    p=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],check=True,capture_output=True,text=True)
    result=json.loads(p.stdout) if p.stdout.strip() else [];return [result] if isinstance(result,dict) else result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args();root=args.root.resolve();out=args.out.resolve()
    assert out.is_relative_to(root/'outputs'),'Audit output must stay inside workspace outputs';out.mkdir(exist_ok=False)
    state=root/'work/tradingbot/local-results/atlas-forward-v2';at=datetime.now(timezone.utc);stamp=at.timestamp();status=json.loads((state/'status.json').read_text());checkpoint_raw=(state/'checkpoint.json').read_bytes();checkpoint=json.loads(checkpoint_raw);freeze=json.loads((state/'freeze.json').read_text());ps=processes();worker=status['worker_pid'];by_pid={p['ProcessId']:p for p in ps}
    protocol=dict(created_utc=at.isoformat(),kind='Retrospective observer-health and receipt-evidence audit; no new financial hypothesis or strategy selection',freeze_sha256=digest(state/'freeze.json'),observer_freeze_utc=freeze['frozen_utc'],auditor_source_sha256=digest(Path(__file__)),rules='Read-only SQLite snapshot. Verify actual PID/ancestry, freshness, source identities and paper-only guards. Reconcile checkpoint financial records; calculate actual minute coverage and quote/receipt clock evidence. An unfinished day never counts as a completed session. Missing pre-open observations remain missing.',prior_goal_turn='Progress on the separately requested 1m/5m study; original SPX goal was a verified wait on the confirmed existing collector. This audit adds current SPX observation evidence without refitting.')
    write(out/'protocol.json',protocol);write(out/'process_identity.json',ps);write(out/'status_at_review.json',status)
    # Preserve the checkpoint bytes, including its documented internal Infinity
    # sentinels, without rewriting them or leaking nonfinite values into metrics.
    (out/'checkpoint_at_review.raw.json').write_bytes(checkpoint_raw)
    assert worker in by_pid,'Reported worker is not alive';parent=by_pid[worker]['ParentProcessId'];assert set(by_pid).issubset({worker,parent}),'More than one effective collector process tree'
    assert '--cohort atlas-forward-v2' in by_pid[worker]['CommandLine'] and '--candidate approved5000' in by_pid[worker]['CommandLine'],'Wrong process identity'
    freshness=stamp-datetime.fromisoformat(status['last_poll_utc']).timestamp();assert 0<=freshness<60,'Stale observer status'
    assert status['paper_only'] and status['broker_execution_calls']==0 and not freeze['live_execution_available'],'Paper-only invariant failed'
    source_rows=[]
    for name,wanted in freeze['source_hashes'].items():
        live=root/'work/tradingbot'/('trading_pipeline' if name=='engine_v4.py' else 'research_monitor')/name;archive=state/'source'/name
        assert digest(live)==wanted and digest(archive)==wanted,'Frozen source identity mismatch: '+name;source_rows.append(dict(name=name,sha256=wanted))
    source=sqlite3.connect(f'file:{(state/"observations.sqlite").as_posix()}?mode=ro',uri=True);source.execute('PRAGMA query_only=ON');destination=sqlite3.connect(out/'observations_snapshot.sqlite');source.backup(destination);destination.close();source.close()
    db=sqlite3.connect(f'file:{(out/"observations_snapshot.sqlite").as_posix()}?mode=ro',uri=True);db.execute('PRAGMA query_only=ON');assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    events=[dict(book=b,kind=k,receipt_ms=t,payload=json.loads(v)) for b,k,t,v in db.execute('SELECT book,kind,receipt_ms,payload FROM events ORDER BY seq')];through=db.execute('SELECT MAX(receipt_ms) FROM quotes').fetchone()[0]/1000;coverage={};clock={}
    for symbol in ['NAS100','SPX500']:
        rows=db.execute('SELECT raw_ms,bid,ask,receipt_ms FROM quotes WHERE symbol=? ORDER BY receipt_ms,rowid',(symbol,)).fetchall();offset=status['clock'][symbol]['offset_hours'];assert offset in [0,2,3]
        ages=[receipt/1000-(raw/1000-offset*3600) for raw,bid,ask,receipt in rows];assert all(bid>0 and ask>=bid for raw,bid,ask,receipt in rows),'Invalid archived quote';assert min(ages)>=-1,'Current offset implies future-dated source quote'
        times=[t for t, in db.execute('SELECT t FROM minutes WHERE symbol=? ORDER BY t',(symbol,))];hours=complete_hours(times);last=max((t for t in hours if t+5<=through),default=None)
        coverage[symbol]=dict(completed_minutes_total=len(times),rth_clock_windows=clock_windows(times,through),latest_complete_incoming_hour_end_utc=utc(last) if last else None,fresh_incoming_hour_available=last is not None and through-last<=3600,latest_complete_hour_age_seconds=through-last if last else None,qualification='Incoming archive coverage only. Historical warmup does not count as new financial observations.')
        ages.sort();clock[symbol]=dict(current_observed_offset_hours=offset,quote_rows=len(rows),minimum_receipt_minus_source_seconds=ages[0],median_receipt_minus_source_seconds=ages[len(ages)//2],maximum_receipt_minus_source_seconds=ages[-1],historical_policy_verified=False,scope='Current source-versus-first-receipt evidence, including delayed/backfilled quotes. These are not all executable fresh quotes.')
    db.close();books={};mismatch=[]
    for name,b in checkpoint['books'].items():
        initial=5000. if name.startswith('candidate_') else 500.;fee=12. if name.endswith('_higher') else 6.;books[name]=reconcile(b,initial,status['symbol_metadata'],fee)
        db_fills=[e['payload'] for e in events if e['book']==name and e['kind']=='fill'];consistent={f['id'] for f in db_fills}=={f['id'] for f in b['fills']}
        if not consistent:mismatch.append(name)
        books[name]['checkpoint_and_database_closed_ids_match']=consistent
        if consistent:assert all(next(x for x in b['fills'] if x['id']==f['id'])==f for f in db_fills)
    gaps=[e for e in events if e['kind']=='data_gap'];reasons=Counter((e['book'],e['payload'].get('lane'),e['payload'].get('reason')) for e in events if e['kind']=='decision');summary_reasons=[dict(book=b,lane=l,reason=r,count=n) for (b,l,r),n in sorted(reasons.items())]
    assert digest(state/'freeze.json')==protocol['freeze_sha256'],'Cohort identity changed during audit'
    result=dict(audited_utc=datetime.now(timezone.utc).isoformat(),through_first_receipt_utc=utc(through),worker_pid=worker,worker_parent_pid=parent,effective_collectors=1,status_age_seconds_at_start=freshness,source_hashes_verified=source_rows,paper_only=True,broker_execution_calls=0,books=books,clock=clock,coverage=coverage,data_gap_events=gaps,decision_reasons=summary_reasons,snapshot_sha256=digest(out/'observations_snapshot.sqlite'),snapshot_checkpoint_sync_warnings=mismatch,completed_covered_sessions=sorted(set.intersection(*[{r['date'] for r in c['rth_clock_windows'] if r['eligible_completed_clock_window']} for c in coverage.values()])),independent_profitability_established=False,goal_achieved=False,limitations=['A live collector and clean arithmetic do not establish profitability.','Current UTC+3 clock observations do not certify historic DST policy.','SPX fees remain the unverified $6/$12 full-lot round-trip proxy.','Current contract and margin snapshots do not certify historic applicability or fill liquidity.','Existing pre-open collection gaps can make hourly confirmation unavailable; do not fill missing prices or relax a frozen gate.','This cohort is a receipt-time hypothetical paper book, not broker execution.'])
    write(out/'results.json',result);write(out/'artifact_identity.json',dict(protocol_sha256=digest(out/'protocol.json'),results_sha256=digest(out/'results.json'),snapshot_sha256=result['snapshot_sha256']))
    print(json.dumps({k:result[k] for k in ['audited_utc','through_first_receipt_utc','worker_pid','effective_collectors','books','clock','coverage','completed_covered_sessions','goal_achieved']},indent=2))


if __name__=='__main__':main()
