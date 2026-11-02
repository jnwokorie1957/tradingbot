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
    write(out/'dashboard_data.json',trim(package));print(json.dumps(dict(experiments=len(records),books=len(results),independent_months=0,latest=[dict(cost=r['cost'],statistics=r['monthly']['statistics'])for r in results if r['book']=='two_strategy_NAS90min']),allow_nan=False))


if __name__=='__main__':main()
