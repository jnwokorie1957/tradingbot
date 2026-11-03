"""Append-only hash-chained experiment inventory and monthly report package."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from atlas_exit_research.data import sha,write,stamp
from atlas_exit_research.baseline import detailed
from .monthly import calculate


def inventory(root,out):
    p=subprocess.run(['rg','--files','outputs','-g','protocol.json'],cwd=root,capture_output=True,text=True,check=True);old=[];file=out/'research_ledger.jsonl'
    if file.exists():old=[json.loads(s) for s in file.read_text(encoding='utf-8').splitlines() if s]
    seen={(r['record']['identity'],r['record']['status']) for r in old};previous=old[-1]['sha256'] if old else '0'*64;records=[]
    for rel in sorted(p.stdout.splitlines()):
        path=root/rel;folder=path.parent
        if any(x in folder.parts for x in ['source','source_snapshot','recovery_source','data']):continue
        files=[f for f in folder.iterdir() if f.is_file() and f.name in ['protocol.json','results.json','development.json','selection.json','decisions.json','completed.json','failure.json','progress.json','worker.json','audit.json','independent_audit.json']];identity=hashlib.sha256(''.join(f.name+sha(f) for f in sorted(files)).encode()).hexdigest();status='results_recorded_unvalidated' if(folder/'results.json').exists()else 'registered_no_outcomes';phase={}
        for n in ['progress.json','worker.json']:
            if(folder/n).exists():
                v=json.loads((folder/n).read_text(encoding='utf-8'));phase=v if isinstance(v,dict)else {}
        if(folder/'completed.json').exists()or phase.get('status')=='completed'or phase.get('phase') in ['complete','completed']:status='completed_unvalidated'
        elif(folder/'failure.json').exists()or phase.get('status')=='failed':status='failed_preserved'
        elif(folder/'results.json').exists():
            result=json.loads((folder/'results.json').read_text(encoding='utf-8'))
            if isinstance(result,list)and any(isinstance(r,dict)and isinstance(r.get('checks'),dict)and not all(r['checks'].values())for r in result):status='failed_verification_preserved'
        record=dict(experiment=str(folder.relative_to(root)).replace('\\','/'),status=status,identity=identity,files={f.name:sha(f) for f in files},has_results=(folder/'results.json').exists(),independent_validation='Not inferred from completion; requires separate unseen evidence',all_artifacts_preserved=True);records.append(record)
        if (identity,status) not in seen:
            event=dict(recorded_utc=stamp(),previous_sha256=previous,record=record);digest=hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest();event['sha256']=digest
            with file.open('a',encoding='utf-8')as stream:stream.write(json.dumps(event)+'\n')
            previous=digest;seen.add((identity,status))
    # Verify every prior link before publishing an updated view.
    prev='0'*64
    for line in file.read_text(encoding='utf-8').splitlines():
        e=json.loads(line);digest=e.pop('sha256');assert e['previous_sha256']==prev and hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest()==digest;prev=digest
    write(out/'experiment_registry.json',dict(updated_utc=stamp(),experiments=records,chain_tip=prev,append_only=True));return records


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve();out=root/'outputs/atlas_research_pipeline_v1';out.mkdir(exist_ok=True);records=inventory(root,out);baseline=json.loads((root/'outputs/atlas_exit_management_v1/baseline.json').read_text());books=[]
    for r in baseline['records']:
        file=root/r['ledger_file'];books.append((r['version'],r['cost'],r['initial_equity'],file,r['portfolio']['quote_drawdown_pct']))
    for folder,label in [('atlas_two_strategy_exits_v1','two_strategy_1_5R_2R'),('atlas_pair_holding_v1','two_strategy_NAS90min')]:
        for r in json.loads((root/'outputs'/folder/'results.json').read_text()):
            cost=r['cost'];file=root/'outputs'/folder/(f'private_fills_requested_{cost}.json'if folder=='atlas_two_strategy_exits_v1'else f'private_fills_{cost}.json');books.append((label,cost,5000.,file,r.get('quote_drawdown_pct',r.get('account',{}).get('quote_drawdown_pct'))))
    for r in json.loads((root/'outputs/atlas_exit_management_v1/comparison/portfolio.json').read_text()):books.append(('three_strategy_NAS2R',r['cost'],5000.,root/f'outputs/atlas_exit_management_v1/comparison/portfolio_fills_{r["cost"]}.json',r['account']['quote_drawdown_pct']))
    results=[]
    for name,cost,capital,file,dd in books:
        fills=json.loads(file.read_text());m=calculate(fills,capital);results.append(dict(book=name,cost=cost,initial_equity=capital,monthly=m,metrics=detailed(fills,capital),quote_drawdown_pct=dd,ledger_sha256=sha(file),reused_observations=True,independent_validation=False))
    write(out/'monthly_results.json',dict(created_utc=stamp(),period=['2025-12-15','2026-10-30'],books=results,independently_evaluated_months=0,independent_monthly_threshold_frequency='NOT_AVAILABLE,not zero percent',capital_comparability='500USD benchmarks used different percentage risk and cannot establish5000USD performance'))
    cycle=out/'cycles/001';new=json.loads((cycle/'results.json').read_text())if(cycle/'results.json').exists()else[];decisions=json.loads((cycle/'decisions.json').read_text())if(cycle/'decisions.json').exists()else[];package=dict(created_utc=stamp(),objective='Investigate15/20/25percent monthly net as stretchhypotheses;positiveindependentexpectancy first;DDtargetbelow10;no riskincreases',monthly=results,original_benchmarks={k:v for k,v in baseline.items()if k!='records'},original_strategy_metrics=[{k:v for k,v in r.items()if k not in ['portfolio','strategies']}|{'strategies':{n:{k:v for k,v in m.items()if k!='curve'}for n,m in r['strategies'].items()}}for r in baseline['records']],experiments=records,new_cycle=[{k:v for k,v in r.items()if k!='audit'}for r in new],new_decisions=decisions,independent_validation=dict(months=0,thresholds={str(t):None for t in [15,20,25]},walk_forward='NOT_AVAILABLE:no untouched historical cohort',prospective='Requires complete evaluator and profile freeze before financial observations; no deployment'),priorities=['Obtain longer genuinely unusedIBKRcontract histories via confirmedothercomputerroute;quarantine and seal before outcome review','Complete a frozen receipt-clock prospective evaluator; existing MT5observer unchanged','Read-only coverage/clock/contract audit and confirmedfees','Bounded evidence-based new cycles; retain all losses and failures;no after-outcome parameter tuning'],active_paper_changed=False)
    def trim(v):
        if isinstance(v,dict):return {k:trim(x)for k,x in v.items()if k not in ['curve','cash_curve']}
        if isinstance(v,list):return [trim(x)for x in v]
        return v
    delay=root/'outputs/atlas_pair_execution_delay_v1';future=root/'outputs/atlas_pair_prospective_v1'
    package['execution_delay']=dict(completed=json.loads((delay/'completed.json').read_text()),decision=json.loads((delay/'development_decision.json').read_text()),records=[dict(profile=r['profile'],cost=r['cost'],trades=r['metrics']['trades'],win_rate=r['metrics']['win_rate'],net=r['metrics']['net_pnl'],quote_drawdown_pct=r['account']['quote_drawdown_pct'])for r in json.loads((delay/'development.json').read_text())],period=['2025-12-15','2026-05-31'],reused=True)if(delay/'completed.json').exists()else None
    if(future/'protocol.json').exists():
        p0=json.loads((future/'protocol.json').read_text());a0=json.loads((future/'availability.json').read_text())if(future/'availability.json').exists()else{};phase=json.loads((future/'progress.json').read_text());package['pair_prospective']=dict(frozen_utc=p0['frozen_utc'],financial_start_utc=p0['financial_start_utc'],profiles=p0['profiles'],protocol_sha256=sha(future/'protocol.json'),phase=phase['status'],financial_observations_scored=phase['financial_observations_scored'],covered_sessions=a0.get('coverage',{}).get('covered_sessions',[]),minimum_new_sessions=5,active_paper_changed=False,evaluation='Frozen receiptclock hypothetical replay;no newcollector or actual orders',drawdown=p0['drawdown']);package['independent_validation']['prospective']='Two-lane60/90minute fixed comparison frozen before new financial observations;awaiting complete sessions';package['priorities'][1]='Evaluate the frozen receipt-clock paired holding comparison after5new covered sessions;no refit or automatic deployment'
    if package.get('pair_prospective')and phase.get('last_batch'):
        batch=root/phase['last_batch'];package['pair_prospective']['records']=json.loads((batch/'results.json').read_text());package['pair_prospective']['comparison']=json.loads((batch/'comparison.json').read_text())
    second=out/'cycles/002';audit=root/'outputs/atlas_pair_bottleneck_audit_v1/results.json'
    if audit.exists():package['bottleneck_audit']={k:v for k,v in json.loads(audit.read_text()).items()if k!='source_sha256'}
    if(second/'completed.json').exists():package['cycle002']=dict(completed=json.loads((second/'completed.json').read_text()),decisions=json.loads((second/'decisions.json').read_text()),records=[dict(profile=r['profile'],cost=r['cost'],trades=r['metrics']['trades'],win_rate=r['metrics']['win_rate'],net=r['metrics']['net_pnl'],quoteDD=r['account']['quote_drawdown_pct'])for r in json.loads((second/'results.json').read_text())],period=['2025-12-15','2026-05-31'],reused_observations=True,independent_validation=False)
    third=out/'cycles/003'
    if(third/'completed.json').exists():
        package['cycle003']=dict(completed=json.loads((third/'completed.json').read_text()),decisions=json.loads((third/'decisions.json').read_text()),post_run_audit=json.loads((third/'post_run_audit.json').read_text()),records=[dict(profile=r['profile'],cost=r['cost'],trades=r['metrics']['trades'],win_rate=r['metrics']['win_rate'],net=r['metrics']['net_pnl'],quoteDD=r['account']['quote_drawdown_pct'],exposure=r['exposure'])for r in json.loads((third/'results.json').read_text())],period=['2025-12-15','2026-05-31'],reused_observations=True,independent_validation=False)
    spread=out/'feasibility/spread_wait_v1';precision=out/'feasibility/quote_precision_v1'
    if(spread/'failure.json').exists():
        package['spread_feasibility']=dict(status='FAILED_DATA_COMPATIBILITY_PRESERVED',failure=json.loads((spread/'failure.json').read_text()),protocol_sha256=sha(spread/'protocol.json'),financial_cases_started=0,financial_result=None,interpretation='The backward-spread waiting idea was not financially scored. Its real-data precision guard failed; eight synthetic causal checks passing did not establish compatibility with historical SPX quotes. No rounding repair, threshold refit or rerun.')
    if(precision/'completed.json').exists():
        package['quote_precision']=json.loads((precision/'results.json').read_text())
        package['priorities'].insert(0,'Reconcile SPX historical quote precision with the saved tick size/value and contract timeline before new execution-sensitive SPX scoring. Preserve old modeled results and the failed feasibility probe; do not infer replacement specifications.')
    provenance=out/'feasibility/contract_provenance_v1'
    if(provenance/'completed.json').exists():
        package['contract_provenance']=json.loads((provenance/'public_summary.json').read_text())
        package['priorities'].insert(0,'Keep historical contract applicability unresolved: agreeing saved snapshots have no effective-date evidence in the bounded corpus. Require documentary reconciliation before a newly registered execution model; no substitution, rounding repair, or replay.')
    decision=root/'outputs/atlas_observer_incident_2026_11_02T2229_v1/user_decision.json'
    if decision.exists():
        package['observation']=dict(state='stopped_by_user',collection_running=False,prospective_observations_accruing=False,required_action=None,notice='Observation stopped by user. Offline research continues; no new prospective observations are being collected. No restart or replacement is authorized.')
        package['independent_validation']['prospective']='Stopped by user; old frozen cohort cannot adopt a replacement process. No new observations accrue.'
        package['priorities'][1]='Keep observation stopped as requested. Any future collection or new cohort requires explicit reactivation and a separate pre-observation freeze.'
    write(out/'dashboard_data.json',trim(package));print(json.dumps(dict(experiments=len(records),books=len(results),independent_months=0,latest=[dict(cost=r['cost'],statistics=r['monthly']['statistics'])for r in results if r['book']=='two_strategy_NAS90min']),allow_nan=False))


if __name__=='__main__':main()
