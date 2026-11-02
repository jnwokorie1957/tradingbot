"""Reconcile preserved versions before any exit experiment is financially run."""
import argparse,json
from pathlib import Path
from .data import sha,stamp,write,prepare,Market,reconstruct
from research_monitor.portfolio_inputs import load_lanes
from research_monitor.atlas_metrics import metrics,contribution_metrics
from research_monitor.atlas_opportunity_study import COSTS


def detailed(fills,initial):
    x=metrics(fills,initial=initial);wins=[f for f in fills if f['pnl']>0];losses=[f for f in fills if f['pnl']<0]
    x.update(realized_payoff_ratio=x['average_win']/-x['average_loss'] if wins and losses else None,average_winning_planned_R=sum(f['pnl']/f['planned_risk'] for f in wins)/len(wins) if wins else None,average_losing_planned_R=sum(f['pnl']/f['planned_risk'] for f in losses)/len(losses) if losses else None,worst_trade=min((f['pnl'] for f in fills),default=None),largest_loss_over_planned=max((-f['pnl']-f['planned_risk'] for f in fills),default=0.))
    return {k:v for k,v in x.items() if not k.startswith('daily_')}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();out=root/'outputs/atlas_exit_management_v1';out.mkdir(exist_ok=True)
    if (out/'baseline.json').exists():raise SystemExit('Baseline already reconciled; preserve existing record')
    refs=['outputs/three_strategy_shared_account_v1/results.json','outputs/portfolio_25_discipline_v1/results.json','outputs/atlas_opportunity_v1/approved5000/results.json','outputs/atlas_two_strategy_5000_v1/results.json','work/tradingbot/local-results/atlas-forward-v2/freeze.json','outputs/atlas_nas15_prospective_v1/protocol.json'];identity={s:sha(root/s) for s in refs};write(out/'preserved_identity.json',identity)
    write(out/'baseline_protocol.json',dict(registered_utc=stamp(),method='Independent ledger arithmetic and event-ordered quote equity; no fitting, source files or benchmark results changed.',reference_sha256=identity,source_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},primary_baseline='Existing recovery-filter $500 composition: SPX15 long confirmed breakout, NAS15 long selective breakout plus loss-dependent efficiency, NAS5 short RSI2. Earliest both-direction NAS5 composition remains a separate reference.',all_prices_reused=True))
    prepare(root,out);_,meta,_=load_lanes(root);market=Market(root,out);records=[]
    scenarios=[]
    originals=json.loads((root/'outputs/three_strategy_shared_account_v1/results.json').read_text())
    for row in originals:
        if row['open_risk_cap']==25. and row['composition']=='original_both_direction_RSI':scenarios.append(('earliest_both_direction',500.,'three_strategy_shared_account_v1',row['ledger'],row))
    for row in json.loads((root/'outputs/portfolio_25_discipline_v1/results.json').read_text()):
        if row['stage']=='full' and row['variant']=='nas15_eff_after2':scenarios.append(('recovery_filter',500.,'portfolio_25_discipline_v1',row['ledger'],row))
    for row in json.loads((root/'outputs/atlas_opportunity_v1/approved5000/results.json').read_text()):scenarios.append(('approved5000_original_exits',5000.,'atlas_opportunity_v1/approved5000',row['ledger'],row))
    for label,initial,folder,key,reported in scenarios:
        cost=reported.get('cost','higher' if reported.get('stress') else 'standard');file=root/'outputs'/folder/f'{"fills" if initial==5000 else "private_fills"}_{key}.json';fills=json.loads(file.read_text());write(out/'progress.json',dict(status='running',phase='baseline_quote_reconciliation',version=label,cost=cost,completed=len(records),total=len(scenarios)))
        assert abs(sum(f['pnl'] for f in fills)-reported['net_pnl'])<1e-7;assert len(fills)==reported.get('outcomes',reported.get('trades'));win=100*sum(f['pnl']>0 for f in fills)/len(fills);assert abs(win-reported['win_rate'])<1e-9
        quote,contributions=reconstruct(market,fills,meta,COSTS[cost],initial);old_dd=reported.get('quote_marked_drawdown_pct',reported.get('quote_drawdown_pct'));assert abs(quote['quote_drawdown_pct']-old_dd)<1e-7,(label,cost,quote['quote_drawdown_pct'],old_dd)
        lanes={n:dict(detailed([f for f in fills if f['strategy']==n],initial),**contributions.get(n,{}),drawdown_scope=f'Shared-account executed contribution marked against ${initial:g}, not a standalone strategy replay') for n in ['SPX15','NAS15','NAS5']}
        row=dict(version=label,cost=cost,initial_equity=initial,period=['2025-12-15','2026-10-30'],portfolio=dict(detailed(fills,initial),**quote),strategies=lanes,ledger_file=str(file.relative_to(root)),ledger_sha256=sha(file),arithmetic_reconciled=True,quote_drawdown_reconciled=True,independent_validation=False,correlations=contribution_metrics(fills)['pairs'])
        records.append(row);print(json.dumps(dict(version=label,cost=cost,trades=len(fills),net=reported['net_pnl'],win_rate=win,quote_drawdown=old_dd)),flush=True)
    assert all(sha(root/f)==v for f,v in identity.items());write(out/'baseline.json',dict(completed_utc=stamp(),records=records,legacy_risk_sensitivities=[{k:v for k,v in x.items() if not isinstance(v,(list,dict))} for x in originals if x['open_risk_cap']!=25.],baseline_reconciled=True,all_previous_files_preserved=True))
    write(out/'progress.json',dict(status='baseline_complete',phase='baseline_complete',completed=len(records),total=len(records)))


if __name__=='__main__':main()
