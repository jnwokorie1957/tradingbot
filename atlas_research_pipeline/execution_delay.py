"""Bounded execution-timing comparison on existing MT5 strategies.

No new signal family, risk allocation, stop geometry, live transport or target.
10s is the predefined primary hypothesis;5s is development sensitivity only.
"""
import argparse,copy,hashlib,json,os,shutil,traceback
from pathlib import Path
from datetime import datetime,timezone
from atlas_exit_research.data import Market,write,sha,stamp,NY
from atlas_exit_research.holding_pair import HoldingBook
from atlas_exit_research.control_check import inputs
from atlas_exit_research.run import describe,entry_identity,SPLIT,END
from atlas_exit_research.baseline import detailed
from atlas_exit_research.audit import reconcile
from research_monitor.atlas_portfolio_controller import APPROVED
from research_monitor.atlas_opportunity_study import COSTS
from .monthly import calculate

PROFILES={'control60':60,'primary10':10,'sensitivity5':5}


def setup_identity(lanes):
    selected={n:{k:v for k,v in lane.items()if k not in ['signals','native']}|{'signals':{t:{k:v for k,v in s.items()if k!='entry_at'}for t,s in lane['signals'].items()}}for n,lane in lanes.items()}
    return hashlib.sha256(json.dumps(selected,sort_keys=True).encode()).hexdigest()


def delayed(lanes,seconds):
    if seconds not in PROFILES.values():raise ValueError('Only preregistered5/10/60second delays are permitted')
    changed={n:dict(lane,signals={t:dict(s,entry_at=s['decision']+seconds)for t,s in lane['signals'].items()})for n,lane in lanes.items()};assert setup_identity(changed)==setup_identity(lanes);return changed


def checks_for_development(rows):
    controls={r['cost']:r for r in rows if r['profile']=='control60'};reasons=[]
    for r in [r for r in rows if r['profile']=='primary10']:
        cost=r['cost'];a=r['account'];m=r['metrics'];reference=controls[cost]
        if m['trades']<30:reasons.append(cost+': fewer than30closedportfolio trades')
        if m['net_pnl']<=0:reasons.append(cost+': nonpositive net')
        if(m['profit_factor']or 0)<1.1:reasons.append(cost+': PF below1.1')
        if m['net_pnl']<reference['metrics']['net_pnl']-1e-7:reasons.append(cost+': net below60second control')
        if a['quote_drawdown_pct']>=10:reasons.append(cost+': DD>=10percent')
        if a['open_positions']or a['incomplete_paths']:reasons.append(cost+': incomplete financial path')
    return reasons


def admission_check(book,delay):
    counts={};executed=0
    for n in book.lanes:
        rows=[r for r in book.decisions if r['lane']==n];done=[r for r in rows if r['status']=='EXECUTED'];capital={'minimum_lot_above_trade_risk','shared_gross_risk_budget','broker_margin_plus_loss_reserve','conflicting_same_symbol_exposure','duplicate_economic_intent','daily_2pct_loss_pause','portfolio_10pct_drawdown_pause','quantity_rounding_or_cash'}
        counts[n]=dict(candidate_decisions=len(rows),executed=len(done),outside_session=sum('entry_outside_session'in r.get('reasons',[])for r in rows),capital_only_veto=sum(r['status']!='EXECUTED'and bool(r.get('reasons'))and set(r['reasons'])<=capital for r in rows))
        for r in done:
            assert r['planned_risk']<=min(25.,r['lane_budget'])+1e-7 and r['planned_risk']+r['used_risk']<=r['total_budget']+1e-7
            assert r['entry_at']==r['decision']+delay and r['entry_at']<=r['observed_at']<=r['entry_at']+5
            m=book.meta[book.lanes[n]['symbol']];assert r['quantity']>=m['volume_min']-1e-8 and abs(r['quantity']/m['volume_step']-round(r['quantity']/m['volume_step']))<1e-7;executed+=1
    return dict(executed_admissions_verified=executed,all_planned_entry_delays_match=True,all_risk_and_legal_quantities_pass=True,by_lane=counts)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--status',action='store_true');a=p.parse_args();root=a.root.resolve();out=root/'outputs/atlas_pair_execution_delay_v1';baseline=root/'outputs/atlas_pair_holding_v1';archive=root/'outputs/atlas_exit_management_v1';state=root/'work/tradingbot/local-results/atlas-research-pipeline';state.mkdir(parents=True,exist_ok=True)
    if a.status:print((out/'progress.json').read_text()if(out/'progress.json').exists()else json.dumps(dict(status='not_started')));return
    out.mkdir(exist_ok=False);lock=state/'execution_delay.lock.json';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,json.dumps(dict(pid=os.getpid(),started_utc=stamp(),out=str(out))).encode());os.close(fd)
    try:
        refs=[baseline/'results.json',baseline/'protocol.json',root/'outputs/atlas_two_strategy_exits_v1/results.json',root/'outputs/atlas_exit_management_v1/comparison/portfolio.json',root/'work/tradingbot/local-results/atlas-forward-v2/freeze.json',root/'work/tradingbot/atlas_exit_research/engine.py',root/'work/tradingbot/atlas_exit_research/holding_pair.py',root/'work/tradingbot/research_monitor/atlas_portfolio_controller.py'];preserved={str(f.relative_to(root)):sha(f)for f in refs};frozen=json.loads((root/'work/tradingbot/local-results/atlas-forward-v2/freeze.json').read_text());source_checks={n:sha(root/'work/tradingbot'/('trading_pipeline'if n=='engine_v4.py'else'research_monitor')/n)==v for n,v in frozen['source_hashes'].items()};assert all(source_checks.values())
        sources=[Path(__file__),Path(__file__).with_name('checks_delay.py')];protocol=dict(registered_utc=stamp(),hypothesis='A hardcoded60second post-completion wait may discard valid terminal-window setups and change stop/no-chase/minlot feasibility. Investigate shorter causal execution delay rather than changing entry filters or risk. Historical actual barreceipt/computation latency is notverified.',profiles=PROFILES,primary='primary10 fixed before outcomes;do not choose5s after10s failure',risk=APPROVED,strategies={'SPX15':'original1.5R60minutehold','NAS15':'fixed2R90minuteholdcapped16:00NY'},only_change='Signal entry_at=decision+10seconds,or+5s sensitivity. Every other signal feature, natural stop, entry filter, RR, legal increment, fee and portfolio riskcontroller remains unchanged. Quote must arrive within5s of plannedentry.',development=['2025-12-15','2026-05-31'],later_reused=['2026-06-01','2026-10-30'],all_history_previously_exposed=True,cases='9development records includingcontrols. Full9-month continuation of10s only if fixeddevelopmentgates pass;3costs.5s never gets later selection in thiscycle.',development_gate='Primary>=30closedportfolio trades at EACHcost;positive net,PF>=1.1,net>=matched60scontrol,quoteDD<10,flatcompletepaths atall3costs. If any fails,archive andstop:do not try another delay orrefit.',later_gate='Descriptive reused continuation,not independentOOS. Report regressions as well as improvements;never promote from these prices.',costs=COSTS,official_docs={'completed_bars':'https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py','last_tick':'https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py'},preserved_sha256=preserved,sources={p.name:sha(p)for p in sources},limitations=['10s/5s signal-delivery and computation delays are hypotheses,not measured historical receipts','Quotes use market-time archives with unverified inferred historicalUTC+2/+3 clock','Commissions and historical contract/margin applicability remain proxies','5s processing result is not chosen by profit and not automaticallytradeable','No deployment or new MT5 connection;actual paperbook and all18frozen sources unchanged'])
        write(out/'protocol.json',protocol);write(out/'original_source_audit.json',source_checks);(out/'source').mkdir()
        for f in sources:shutil.copy2(f,out/'source'/f.name)
        write(out/'progress.json',dict(status='running',pid=os.getpid(),phase='verify_quote_caches',completed=0,total=9));data_identity=json.loads((archive/'data_identity.json').read_text());cache_checks={symbol:sha(root/record['cache'])==record['sha256']for symbol,record in data_identity.items()};assert all(cache_checks.values());write(out/'data_identity_audit.json',dict(original_quote_cache_hashes_match=cache_checks,input_csv_sha256={str(f.relative_to(root)):sha(f)for f in [root/'outputs/nas100_quote_data_v1/NAS100_M1.csv',root/'outputs/spx15_canonical_quote_data_v1/SPX500_M1.csv',root/'outputs/spx15_direction_later_v1/data/SPX500_M1.csv']}))
        write(out/'progress.json',dict(status='running',pid=os.getpid(),phase='load_original_inputs',completed=0,total=9));all_lanes,meta=inputs(root);lanes={n:l for n,l in all_lanes.items()if n in ['NAS15','SPX15']};original_identity=entry_identity(lanes);setup=setup_identity(lanes);write(out/'setup_identity.json',dict(setup_sha256=setup,original_entries_sha256=original_identity));market=Market(root,archive);rows=[];books={};audits={};styles={'SPX15':'original','NAS15':'fixed_2'}
        for profile,delay in PROFILES.items():
            active=lanes if profile=='control60'else delayed(lanes,delay)
            for cost in COSTS:
                write(out/'progress.json',dict(status='running',pid=os.getpid(),phase='development',profile=profile,cost=cost,completed=len(rows),total=9));book=HoldingBook(market,active,meta,COSTS[cost],styles,durations={'NAS15':90});book.run_to(SPLIT);account=book.result();audit=reconcile(market,book.fills,meta,COSTS[cost],account);key=profile+'_'+cost;audits[key]=audit;row=dict(profile=profile,cost=cost,delay_seconds=delay,account=account,metrics=describe(book,end=SPLIT),admission_audit=admission_check(book,delay),independent_validation=False);rows.append(row);books[(profile,cost)]=book;write(out/'development'/f'private_fills_{key}.json',book.fills);write(out/'development'/f'private_decisions_{key}.json',book.decisions);write(out/'development.json',rows)
                if profile=='control60':
                    old=json.loads((baseline/f'private_fills_{cost}.json').read_text());prefix=[f for f in old if datetime.fromtimestamp(f['exit_at'],timezone.utc).astimezone(NY).date().isoformat()<SPLIT];assert book.fills==prefix,'Control money/executed ledger diverged from preservedprefix';ref=next(r for r in json.loads((baseline/'development.json').read_text())if r['profile']=='nas90'and r['cost']==cost);assert abs(account['quote_drawdown_pct']-ref['account']['quote_drawdown_pct'])<1e-7
        reasons=checks_for_development(rows);write(out/'development_decision.json',dict(frozen_utc=stamp(),primary='primary10',passed=not reasons,reasons=reasons,sensitivity_not_selected=True,promotion=False,later_outcomes_not_consulted=True));full=[]
        if not reasons:
            refs=json.loads((baseline/'results.json').read_text())
            for cost in COSTS:
                write(out/'progress.json',dict(status='running',pid=os.getpid(),phase='later_reused_continuation',profile='primary10',cost=cost));book=books[('primary10',cost)];book.run_to(END);account=book.result();assert not account['open_positions']and not account['incomplete_paths'];audit=reconcile(market,book.fills,meta,COSTS[cost],account);audits['full_'+cost]=audit;m=describe(book);old=next(r for r in refs if r['cost']==cost);row=dict(profile='primary10',cost=cost,delay_seconds=10,account=account,metrics=m,monthly=calculate(book.fills,5000.),strategies={n:detailed([f for f in book.fills if f['strategy']==n],5000.)for n in lanes},comparison=dict(old_net=old['account']['net_pnl'],new_net=account['net_pnl'],net_delta=account['net_pnl']-old['account']['net_pnl'],old_drawdown=old['account']['quote_drawdown_pct'],new_drawdown=account['quote_drawdown_pct'],old_trades=old['account']['trades'],new_trades=account['trades']),admission_audit=admission_check(book,10),independent_validation=False,promotion=False);full.append(row);write(out/f'private_fills_{cost}.json',book.fills);write(out/f'private_decisions_{cost}.json',book.decisions);write(out/'results.json',full);print(json.dumps(dict(cost=cost,**row['comparison'],WR=m['win_rate'],annualized=m['annualized_extrapolation_pct'])),flush=True)
        assert entry_identity(lanes)==original_identity and setup_identity(lanes)==setup and all(sha(root/k)==v for k,v in preserved.items());write(out/'independent_audit.json',dict(all_pass=True,records=audits));write(out/'completed.json',dict(completed_utc=stamp(),development_cases=9,later_cases=len(full),primary_development_pass=not reasons,all_originals_preserved=True,signal_rules_stops_RR_risk_unchanged=True,active_paper_configuration_unchanged=True,independent_validation=False,promotion=False));write(out/'progress.json',dict(status='completed',development_cases=9,later_cases=len(full)));print(json.dumps(dict(completed=True,later_cases=len(full),development_failures=reasons)),flush=True)
    except BaseException:
        write(out/'failure.json',dict(failed_utc=stamp(),traceback=traceback.format_exc(),rules_changed=False));write(out/'progress.json',dict(status='failed',pid=os.getpid()));raise
    finally:lock.unlink(missing_ok=True)


if __name__=='__main__':main()
