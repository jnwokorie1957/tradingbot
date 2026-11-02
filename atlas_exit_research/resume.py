"""Recover the finite comparison after a Windows atomic-write sharing lock.

No parameters change. Completed SPX/NAS15 financial cases are reused. NAS5
development recomputation solely restores lost in-memory account state and must
match the already recorded result; then it continues chronologically.
"""
import argparse,json,os,shutil
from pathlib import Path
from .data import Market,write,sha,stamp
from .engine import Account,EXITS
from .control_check import inputs
from .run import describe,choose,correlations,entry_identity,FIRST,SPLIT,END
from research_monitor.atlas_opportunity_study import COSTS
from research_monitor.atlas_portfolio_controller import APPROVED
from research_monitor.atlas_metrics import local_day
from .baseline import detailed


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve();out=root/'outputs/atlas_exit_management_v1';run=out/'comparison';assert not(run/'completed.json').exists();assert not(run/'recovery_protocol.json').exists();protocol=json.loads((run/'protocol.json').read_text());rows=json.loads((run/'results.json').read_text());selections=json.loads((run/'selection.json').read_text())['selections'];lanes,meta=inputs(root);assert entry_identity(lanes)==protocol['original_entries_sha256'];assert sha(Path(__file__).parent/'engine.py')==protocol['sources']['engine.py'];assert all(sha(root/k)==v for k,v in protocol['preserved_references'].items())
    write(run/'failure.json',dict(reason='Windows WinError5 replacing progress.json; interrupted after SPX15/NAS15 completed and most NAS5 development rows. Financial sources/rules intact.',completed_full_rows=sum(r['scope']=='full' for r in rows),prior_results_sha256=sha(run/'results.json'),prior_progress_sha256=sha(out/'progress.json'),recorded_utc=stamp()))
    write(run/'recovery_protocol.json',dict(registered_utc=stamp(),pid=os.getpid(),change='Bounded retry on Windows atomic-file sharing violation only. No financial parameter/source change. Reuse all completed financial rows; reconstruct NAS5 development state,assert stored results before continuation.',source_sha256={f.name:sha(f) for f in Path(__file__).parent.glob('*.py')},original_protocol_sha256=sha(run/'protocol.json')));snap=run/'recovery_source';snap.mkdir()
    for f in Path(__file__).parent.glob('*.py'):shutil.copy2(f,snap/f.name)
    market=Market(root,out,('NAS100',));name='NAS5';books={};dev=[r for r in rows if r['lane']==name and r['scope']=='development']
    for style in EXITS:
        for cost in COSTS:
            write(out/'progress.json',dict(status='running',phase='recover_NAS5_development_state',style=style,cost=cost,completed=42,total_unique=66));book=Account(market,{name:lanes[name]},meta,COSTS[cost],{name:style});book.run_to(SPLIT);actual=book.result();stored=next((r for r in dev if r['style']==style and r['cost']==cost),None)
            if stored:
                for k in ['net_pnl','quote_drawdown_pct','trades','win_rate']:assert actual[k]==stored['account'][k],(style,cost,k)
            else:
                r=dict(id=f'{name}_{style}_{cost}_development',lane=name,style=style,cost=cost,scope='development',account=actual,metrics=describe(book,end=SPLIT),independent_validation=False);dev.append(r);rows.append(r);write(run/'results.json',rows)
            books[(style,cost)]=book
    selections[name]=choose(dev,name);write(run/'selection.json',dict(frozen_utc=stamp(),selections=selections,later_outcomes_not_consulted_for_lane_selection=True));completed=42
    for (style,cost),book in books.items():
        write(out/'progress.json',dict(status='running',phase='individual_full',lane=name,style=style,cost=cost,completed=completed,total_unique=66));book.run_to(END);key=f'{name}_{style}_{cost}_full';later=[f for f in book.fills if local_day(f['exit_at'])>=SPLIT];starting=5000.+sum(f['pnl'] for f in book.fills if local_day(f['exit_at'])<SPLIT);r=dict(id=key,lane=name,style=style,cost=cost,scope='full',account=book.result(),metrics=describe(book),later_reused_metrics=describe(book,first=SPLIT,starting=starting,fills=later),independent_validation=False);rows.append(r);write(run/'ledgers'/f'{key}.json',book.fills);write(run/'decisions'/f'{key}.json',book.decisions);write(run/'results.json',rows);completed+=1
    del books,market
    styles={n:selections[n]['diagnostic_lead'] for n in lanes};write(run/'portfolio_protocol.json',dict(frozen_utc=stamp(),styles=styles,selected_by='Lane development-only maximum worstcost expectancy;diagnostic only,not qualification or deployment',independently_validated=False,promotion_allowed=False,approved_risk=APPROVED));market=Market(root,out);portfolio=[]
    for cost in COSTS:
        write(out/'progress.json',dict(status='running',phase='combined_diagnostic',cost=cost,completed=completed,total_unique=66));book=Account(market,lanes,meta,COSTS[cost],styles);book.run_to(END);r=dict(cost=cost,styles=styles,account=book.result(),metrics=describe(book),strategies={n:detailed([f for f in book.fills if f['strategy']==n],5000.) for n in lanes},correlations=correlations(book.fills),independently_validated=False,promotion_allowed=False);portfolio.append(r);write(run/f'portfolio_fills_{cost}.json',book.fills);write(run/f'portfolio_decisions_{cost}.json',book.decisions);write(run/'portfolio.json',portfolio)
    assert entry_identity(lanes)==protocol['original_entries_sha256'];assert all(sha(root/k)==v for k,v in protocol['preserved_references'].items())
    write(run/'prospective_protocol.json',dict(frozen_utc=stamp(),styles=styles,no_new_financial_observations_used=True,source_sha256=json.loads((run/'recovery_protocol.json').read_text())['source_sha256'],entry_identity=protocol['original_entries_sha256'],risk=APPROVED,status='NOT_ACTIVATED: independent validation pending; existing paper collector unchanged',source='Existing observer first-collector-receipt archive only;no second terminal connection;never backdate hypothetical fills',data_after='Protocol freeze with price/indicator warmup tagged separately',coverage='>=99percent completed NY09:00-16:00 minute bars each scored session;missing position paths disqualify',evaluation='Three consecutive20covered-session folds and30closed trades per lane per cost; frozen original and candidate; no tuning/reselection. Future financial evaluator must be frozen before it consumes that cohort.',promotion='No automatic promotion;positive net and quoteDD<10 atallcosts;net expectancy and stressedDD improvements vs contemporaneousoriginal;meaningful capture and uncertainty',true_walkforward_results='Unavailable: no untouched market block has elapsed after freeze'))
    write(run/'completed.json',dict(completed_utc=stamp(),unique_individual_comparisons=completed,reported_full_rows=72,portfolio_diagnostics=3,original_benchmarks_preserved=True,entries_unchanged=True,paper_account_unchanged=True,independent_validation=False,validation_pass=False));write(out/'progress.json',dict(status='completed',phase='finite_exit_comparison_complete',completed=completed,total_unique=66,independent_validation=False));print(json.dumps(dict(completed=completed,styles=styles,portfolio=[dict(cost=r['cost'],net=r['account']['net_pnl'],drawdown=r['account']['quote_drawdown_pct']) for r in portfolio])))


if __name__=='__main__':main()
