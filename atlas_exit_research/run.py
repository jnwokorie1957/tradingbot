"""Finite, registered exit comparison. Offline only; originals are read-only.

One chronological development selection per lane precedes its later replay.
Every date is already exposed: later replay is descriptive, never untouched OOS.
"""
import argparse,copy,gc,json,os,shutil
from pathlib import Path
from itertools import combinations
import numpy as np
from .data import Market,sha,stamp,write
from .engine import Account,EXITS
from .control_check import inputs
from .baseline import detailed
from research_monitor.atlas_metrics import metrics,local_day,weekdays
from research_monitor.atlas_opportunity_study import COSTS
from research_monitor.atlas_portfolio_controller import APPROVED

FIRST='2025-12-15';SPLIT='2026-06-01';END='2026-10-31'


def entry_identity(lanes):
    import hashlib
    return {n:hashlib.sha256(json.dumps({k:v for k,v in l.items() if k!='native'},sort_keys=True).encode()).hexdigest() for n,l in lanes.items()}


def describe(book,first=FIRST,end=END,starting=5000.,fills=None):
    fills=book.fills if fills is None else fills
    m=metrics(fills,initial=starting,first=first,end=end);wins=[f for f in fills if f['pnl']>0];losses=[f for f in fills if f['pnl']<0]
    m.update(realized_payoff_ratio=m['average_win']/-m['average_loss'] if wins and losses else None,average_winning_planned_R=float(np.mean([f['pnl']/f['planned_risk'] for f in wins])) if wins else None,average_losing_planned_R=float(np.mean([f['pnl']/f['planned_risk'] for f in losses])) if losses else None,worst_trade=min((f['pnl'] for f in fills),default=None),losses_above_planned=sum(-f['pnl']>f['planned_risk']+1e-8 for f in fills),largest_loss_over_planned=max([0.]+[-f['pnl']-f['planned_risk'] for f in fills]),trades_per_week=len(fills)/((__import__('datetime').date.fromisoformat(end)-__import__('datetime').date.fromisoformat(first)).days/7),trades_per_month=len(fills)/((__import__('datetime').date.fromisoformat(end)-__import__('datetime').date.fromisoformat(first)).days/30.436875))
    # A fixed block bootstrap preserves within-week clustering, includes zero weeks,
    # and is a development uncertainty diagnostic, not a multiple-search correction.
    days=m['daily_dates'];buckets={}
    for day in days:
        dt=__import__('datetime').date.fromisoformat(day);iso=dt.isocalendar();buckets.setdefault((iso.year,iso.week),[0.,0])
    for f in fills:
        dt=__import__('datetime').date.fromisoformat(local_day(f['exit_at']));iso=dt.isocalendar();b=buckets[(iso.year,iso.week)];b[0]+=f['pnl']/f['planned_risk'];b[1]+=1
    values=np.array(list(buckets.values()));rng=np.random.default_rng(20261102);pick=rng.integers(0,len(values),size=(2000,len(values)));sums=values[pick].sum(axis=1);ratios=sums[sums[:,1]>0,0]/sums[sums[:,1]>0,1]
    m['weekly_block_bootstrap_net_R_95pct']=np.quantile(ratios,[.025,.975]).tolist() if len(ratios) else None
    m['commission_dollars']=sum(f['quantity']*book.cost['fee'] for f in fills)
    m['modeled_roundtrip_slippage_dollars']=sum(2*book.meta[f['symbol']]['trade_tick_value_loss']*book.cost['slip_ticks']*f['quantity'] for f in fills)
    m['quote_gaps_over_60s']=sum(f['maximum_observed_quote_gap_seconds']>60 for f in fills)
    m['max_observed_gap_seconds']=max((f['maximum_observed_quote_gap_seconds'] for f in fills),default=0.)
    m['cash_curve']=[dict(day=d,balance=b) for d,b in zip(m['daily_dates'],m['daily_balance'])]
    return {k:v for k,v in m.items() if not k.startswith('daily_')}


def choose(rows,name):
    original={r['cost']:r for r in rows if r['style']=='original'};rank=[]
    for style in EXITS:
        costs={r['cost']:r for r in rows if r['style']==style};why=[]
        for cost,r in costs.items():
            m=r['metrics'];ref=original[cost]
            if m['trades']<30:why.append(cost+': fewer than30 development trades')
            if m['net_pnl']<=0:why.append(cost+': nonpositive net')
            if r['account']['quote_drawdown_pct']>=10:why.append(cost+': drawdown>=10percent')
            if r['account']['open_positions'] or r['account']['incomplete_paths']:why.append(cost+': incomplete position path')
            if cost in ('standard','higher') and (m['net_pnl']<ref['metrics']['net_pnl']-1e-7 or (m['expectancy_planned_R'] or -999)<(ref['metrics']['expectancy_planned_R'] or -999)-1e-9):why.append(cost+': net or expectancy below original')
            ci=m['weekly_block_bootstrap_net_R_95pct']
            if not ci or ci[0]<=0:why.append(cost+': uncertainty includes nonpositive expectancy')
        score=min((r['metrics']['expectancy_planned_R'] or -999) for r in costs.values());rank.append(dict(style=style,development_gate=not why,reasons=why,worst_cost_expectancy_R=score))
    eligible=[r for r in rank if r['development_gate']];selected=max(eligible,key=lambda r:r['worst_cost_expectancy_R'])['style'] if eligible else 'original'
    lead=max(rank,key=lambda r:r['worst_cost_expectancy_R'])['style']
    return dict(lane=name,selected_reference=selected,diagnostic_lead=lead,eligible_development_candidates=len(eligible),ranked=sorted(rank,key=lambda r:r['worst_cost_expectancy_R'],reverse=True),independently_validated=False,promotion_allowed=False,decision='Retain original reference unless all predefined development gates pass; no financial deployment. Diagnostic lead is not a validated winner.')


def correlations(fills):
    result=[];names=sorted({f['strategy'] for f in fills});days=weekdays();daily={n:{d:0. for d in days} for n in names}
    for f in fills:daily[f['strategy']][local_day(f['exit_at'])]+=f['pnl']
    for a,b in combinations(names,2):
        x=np.array(list(daily[a].values()));y=np.array(list(daily[b].values()));pairs=[(u,v) for u in fills if u['strategy']==a for v in fills if v['strategy']==b and min(u['exit_at'],v['exit_at'])>max(u['entry_at'],v['entry_at'])]
        result.append(dict(a=a,b=b,daily_net_correlation=float(np.corrcoef(x,y)[0,1]) if x.std() and y.std() else None,both_losing_days=int(((x<0)&(y<0)).sum()),overlapping_pairs=len(pairs),overlapping_both_losing_pairs=sum(u['pnl']<0 and v['pnl']<0 for u,v in pairs)))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();out=root/'outputs/atlas_exit_management_v1';run=out/'comparison';run.mkdir(exist_ok=False)
    assert json.loads((out/'control_parity_v3/completed.json').read_text())['exact_financial_parity']
    frozen=json.loads((out/'preserved_identity.json').read_text());assert all(sha(root/k)==v for k,v in frozen.items());lanes,meta=inputs(root);entry_hash=entry_identity(lanes)
    protocol=dict(registered_utc=stamp(),pid=os.getpid(),objective='20-30percentannualizednet;portfolio quote drawdown<10percent;positive robust expectancy;larger winners where feasible;no mandatory winrate target',original_entries_sha256=entry_hash,approved_risk=APPROVED,costs=COSTS,dates=[FIRST,'2026-10-30'],development=[FIRST,'2026-05-31'],later_reused=[SPLIT,'2026-10-30'],all_prices_previously_exposed=True,untouched_historical_OOS_available=False,exit_styles=list(EXITS),exit_definitions=dict(original='Unchanged1.5R SPX/NAS15; NAS5 original RSI2 exit',fixed='1.5/2/3/4 gross price-distance R; legal tick rounding; original stop and original expiry retained',trailing='After1.5R favorable excursion, lagged prior-quote highwater minus1R; only ratchets tighter; adverse gaps filled at observed market',partial_trailing='Legal half rounded down at1.5R then remaining trails1R. Min-lot prevents partial: full-position trail with fallback counted. No invented fractional contracts',structure='After1.5R excursion, preceding two completed strategy candles extreme plus1tick; ratchets only; bar levels eligible at completed-bar end+1sec',expiry='All variants retain original holding deadlines; this pass does not extend overnight risk'),selection='Fixed before outcomes: >=30 development trades EACHcost; positive net;quoteDD<10; flat paths; bootstrap lower95bound netR>0 eachcost; standard/higher net and expectancy>=original. Rank worstcost expectancyR. If no candidate qualifies, original remainsreference. Diagnostic worstcost lead may be shown but not promoted.',validation='Later dates are reused descriptive continuation, NOT untouchedOOS. No true walkforward results available. Freeze prospective rules before new data;20completed-session future folds without tuning. No selection or promotion on prospective outcomes.',sources={f.name:sha(f) for f in Path(__file__).parent.glob('*.py')},preserved_references=frozen,limitations=['Fee6/12/18USD per full CFD lot roundtrip are proxies,not verified account commissions','Observed bid/ask archive; scaled spreads and deterministic tick slippage; no verified queue/liquidity model','Historical clock inferred +2/+3 not broker-certified','Current contract/legal lot data and0.5percent margin proxy not historically verified; severe margin doubled','No futures equivalence: NAS100/SPX500 CFDs,not MNQ/MES','No guaranteed realized loss or drawdown bound; entry pauses do not liquidate positions','Calendar/holiday closures and quote gaps remain in results; funding/tax/data-platform fees not included'])
    write(run/'protocol.json',protocol);(run/'source').mkdir()
    for f in Path(__file__).parent.glob('*.py'):shutil.copy2(f,run/'source'/f.name)
    rows=[];selections={};completed=0
    def progress(**v):write(out/'progress.json',dict(status='running',completed=completed,total_unique=66,**v))
    def save(book,name,style,cost,scope):
        key=f'{name}_{style}_{cost}_{scope}';r=dict(id=key,lane=name,style=style,cost=cost,scope=scope,account=book.result(),metrics=describe(book,end=SPLIT if scope=='development' else END),independent_validation=False)
        if scope=='full':
            later=[f for f in book.fills if local_day(f['exit_at'])>=SPLIT];starting=5000.+sum(f['pnl'] for f in book.fills if local_day(f['exit_at'])<SPLIT);r['later_reused_metrics']=describe(book,first=SPLIT,starting=starting,fills=later)
            write(run/'ledgers'/f'{key}.json',book.fills);write(run/'decisions'/f'{key}.json',book.decisions)
        rows.append(r);write(run/'results.json',rows);return r
    for symbol,names in [('SPX500',['SPX15']),('NAS100',['NAS15','NAS5'])]:
        progress(phase='market_load',symbol=symbol);market=Market(root,out,(symbol,))
        for name in names:
            books={};dev=[]
            for style in EXITS:
                if style=='fixed_1_5' and name!='NAS5':continue
                for cost in COSTS:
                    progress(phase='individual_development',lane=name,style=style,cost=cost);book=Account(market,{name:lanes[name]},meta,COSTS[cost],{name:style});book.run_to(SPLIT);books[(style,cost)]=book;dev.append(save(book,name,style,cost,'development'))
            if name!='NAS5':
                for cost in COSTS:
                    r=copy.deepcopy(next(r for r in dev if r['style']=='original' and r['cost']==cost));r.update(id=f'{name}_fixed_1_5_{cost}_development',style='fixed_1_5',equivalent_to='original');dev.append(r);rows.append(r)
            selections[name]=choose(dev,name);write(run/'selection.json',dict(frozen_utc=stamp(),selections=selections,later_outcomes_not_consulted_for_lane_selection=True));write(run/'results.json',rows)
            for (style,cost),book in books.items():
                progress(phase='individual_full',lane=name,style=style,cost=cost);book.run_to(END);save(book,name,style,cost,'full');completed+=1
            if name!='NAS5':
                for cost in COSTS:
                    r=copy.deepcopy(next(r for r in rows if r['lane']==name and r['style']=='original' and r['cost']==cost and r['scope']=='full'));r.update(id=f'{name}_fixed_1_5_{cost}_full',style='fixed_1_5',equivalent_to='original');rows.append(r)
            del books;gc.collect()
        del market;gc.collect()
    write(run/'results.json',rows)
    styles={n:selections[n]['diagnostic_lead'] for n in lanes};write(run/'portfolio_protocol.json',dict(frozen_utc=stamp(),styles=styles,selected_by='Each lane development-only maximum worstcost expectancy,regardless of qualification; diagnostic only',independently_validated=False,promotion_allowed=False,approved_risk=APPROVED))
    market=Market(root,out);portfolio=[]
    for cost in COSTS:
        progress(phase='combined_diagnostic',cost=cost);book=Account(market,lanes,meta,COSTS[cost],styles);book.run_to(END);r=dict(cost=cost,styles=styles,account=book.result(),metrics=describe(book),strategies={n:dict(detailed([f for f in book.fills if f['strategy']==n],5000.)) for n in lanes},correlations=correlations(book.fills),independently_validated=False,promotion_allowed=False);portfolio.append(r);write(run/f'portfolio_fills_{cost}.json',book.fills);write(run/f'portfolio_decisions_{cost}.json',book.decisions);write(run/'portfolio.json',portfolio)
    assert entry_identity(lanes)==entry_hash;assert all(sha(root/k)==v for k,v in frozen.items())
    prospective=dict(frozen_utc=stamp(),no_new_financial_observations_used=True,styles=styles,source_sha256=protocol['sources'],entry_identity=entry_hash,risk=APPROVED,status='NOT_ACTIVATED: independent validation pending; existing paper collector unchanged',source='Existing observer first-collector-receipt archive only; no second terminal connection; never backdate hypothetical fills',data_after='This protocol freeze,with price/indicator warmup tagged separately',coverage='Require each scored NY09:00-16:00 session>=99percent completed1m bars; reject positions with missing path; current incomplete sessions remain disqualified',evaluation='Minimum3consecutive20completed-session folds and30 closed trades per lane at eachcost; no tuning/reselection; evaluateoriginal and frozen candidate chronologically with same riskcontroller and observed quotes. Annualtarget is extrapolation until full year.',promotion='None automatic. Positive net at standard/higher/severe;quoteDD<10 atallcosts; improving portfolio netexpectancy and not deteriorating stressedDD vs contemporaneousoriginal; meaningful count, uncertainty and opportunitycapture. If fails,new hypothesis needs another future block.',true_walkforward_results='Unavailable: no untouched market block has elapsed after freeze')
    write(run/'prospective_protocol.json',prospective);write(run/'completed.json',dict(completed_utc=stamp(),unique_individual_comparisons=completed,reported_full_rows=72,portfolio_diagnostics=3,original_benchmarks_preserved=True,entries_unchanged=True,paper_account_unchanged=True,independent_validation=False,validation_pass=False));write(out/'progress.json',dict(status='completed',phase='finite_exit_comparison_complete',completed=completed,total_unique=66,independent_validation=False));print(json.dumps(dict(completed=completed,styles=styles,portfolio=[dict(cost=r['cost'],net=r['account']['net_pnl'],drawdown=r['account']['quote_drawdown_pct']) for r in portfolio])),flush=True)


if __name__=='__main__':main()
