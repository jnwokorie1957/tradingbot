"""Bounded two-lane holding-clock study. Entries, RR and risk are unchanged."""
import argparse,json,shutil
from pathlib import Path
from datetime import datetime,timezone
from .data import Market,write,sha,stamp,NY
from .engine import Account
from .control_check import inputs
from .run import describe,entry_identity,SPLIT,END
from .baseline import detailed
from .audit import reconcile
from research_monitor.atlas_opportunity_study import COSTS
from research_monitor.atlas_portfolio_controller import APPROVED

PROFILES={'nas90':{'NAS15':90},'nas120':{'NAS15':120},'spx90':{'SPX15':90},'spx120':{'SPX15':120},'both90':{'SPX15':90,'NAS15':90},'both120':{'SPX15':120,'NAS15':120}}


class HoldingBook(Account):
    def __init__(self,*args,durations,**kw):super().__init__(*args,**kw);self.durations=durations
    def enter(self,k,name,signal,i):
        if name in self.durations:
            # Actual observed entry time is known now. No future quote/feature is
            # used in the duration rule. Entries and natural stops are identical.
            at=float(self.market.t[self.lanes[name]['symbol']][i]);cutoff=datetime.fromtimestamp(at,timezone.utc).astimezone(NY).replace(hour=16,minute=0,second=0,microsecond=0).timestamp();signal=dict(signal,expiry_at=min(at+self.durations[name]*60,cutoff))
        return super().enter(k,name,signal,i)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve();out=root/'outputs/atlas_pair_holding_v1';out.mkdir(exist_ok=False);base=root/'outputs/atlas_two_strategy_exits_v1';archive=root/'outputs/atlas_exit_management_v1';frozen={str(f.relative_to(root)):sha(f) for f in [base/'results.json',base/'protocol.json',archive/'comparison/portfolio.json',root/'work/tradingbot/atlas_exit_research/engine.py',root/'work/tradingbot/research_monitor/atlas_portfolio_controller.py']};write(out/'protocol.json',dict(registered_utc=stamp(),hypothesis='24of86 standardcost exits expire at onehour. Longer intraday clocks may allow original1.5R/2R targets without changing entries/stops/risk; they may also increase reversals/occupancy and losses.',profiles=PROFILES,risk=APPROVED,styles={'SPX15':'original','NAS15':'fixed_2'},development=['2025-12-15','2026-05-31'],later=['2026-06-01','2026-10-30'],all_prices_previously_exposed=True,untouched_OOS=False,selection='One finite development screen, then freeze one diagnostic lead before later outcomes. Require>=30portfolio trades EACHcost, positive net,quoteDD<10 EACHcost, standard/higher net>=sameperiod control. Rank minimum acrosscosts of net / max(1,DDpercent). Failed screens preserved; if no eligible,rank diagnostic lead but never promote. No parameter refit or extra profiles after outcomes.',expiry='Original actual observed entry+60minutes stays reference. Changed lane uses actual observed entry+90/120minutes, capped16:00NY. Only time exit changes. Target, initialstop, entry features, entrywindows and riskcontroller stayfixed.',prior_study='spx15_holding_duration_v1 used500USD, older10-12entryrules/1.5R and developmentonly. This is a distinct5000USD shared1.5R/2R composition; not independent price evidence.',costs=COSTS,preserved_sha256=frozen,sources={f.name:sha(f) for f in Path(__file__).parent.glob('*.py')},promotion=False));(out/'source').mkdir()
    for f in Path(__file__).parent.glob('*.py'):shutil.copy2(f,out/'source'/f.name)
    write(out/'progress.json',dict(status='running',phase='load',completed=0,total=21));all_lanes,meta=inputs(root);lanes={n:l for n,l in all_lanes.items() if n in ['NAS15','SPX15']};identity=entry_identity(lanes);market=Market(root,archive);rows=[];books={};styles={'SPX15':'original','NAS15':'fixed_2'};archived=json.loads((base/'results.json').read_text());opportunity={}
    for cost in COSTS:
        d=json.loads((base/f'private_decisions_requested_{cost}.json').read_text());capital={'minimum_lot_above_trade_risk','shared_gross_risk_budget','broker_margin_plus_loss_reserve','conflicting_same_symbol_exposure','duplicate_economic_intent','daily_2pct_loss_pause','portfolio_10pct_drawdown_pause','quantity_rounding_or_cash'};opportunity[cost]={n:dict(raw_candidate_decisions=sum(r['lane']==n for r in d),executed=sum(r['lane']==n and r['status']=='EXECUTED' for r in d),capital_or_exposure_only_veto=sum(r['lane']==n and r['status']!='EXECUTED' and bool(r.get('reasons')) and set(r['reasons'])<=capital for r in d),interpretation='Capital-only veto is not a proven winning missed trade. Multiple raw veto reasons overlap. No filter is loosened to force a fill.') for n in lanes}
    write(out/'opportunity_audit.json',opportunity)
    for profile,changes in [('control',{})]+list(PROFILES.items()):
        for cost in COSTS:
            write(out/'progress.json',dict(status='running',phase='development',profile=profile,cost=cost,completed=len(rows),total=21));book=HoldingBook(market,lanes,meta,COSTS[cost],styles,durations=changes);book.run_to(SPLIT);r=dict(profile=profile,cost=cost,account=book.result(),metrics=describe(book,end=SPLIT),independent_validation=False);rows.append(r);books[(profile,cost)]=book;write(out/'development.json',rows)
            if profile=='control':
                original=json.loads((base/f'private_fills_requested_{cost}.json').read_text());prefix=[f for f in original if datetime.fromtimestamp(f['exit_at'],timezone.utc).astimezone(NY).date().isoformat()<SPLIT];assert book.fills==prefix,'Development state differs from preserved control'
    controls={r['cost']:r for r in rows if r['profile']=='control'};ranked=[]
    for profile in PROFILES:
        cases=[r for r in rows if r['profile']==profile];reasons=[]
        for r in cases:
            m=r['metrics'];a=r['account'];cost=r['cost']
            if m['trades']<30:reasons.append(cost+': fewer than30trades')
            if m['net_pnl']<=0:reasons.append(cost+': nonpositive net')
            if a['quote_drawdown_pct']>=10:reasons.append(cost+': drawdown>=10percent')
            if a['open_positions'] or a['incomplete_paths']:reasons.append(cost+': incomplete path')
            if cost in ['standard','higher'] and m['net_pnl']<controls[cost]['metrics']['net_pnl']-1e-7:reasons.append(cost+': net below control')
        ranked.append(dict(profile=profile,eligible=not reasons,reasons=reasons,score=min(r['metrics']['net_pnl']/max(1.,r['account']['quote_drawdown_pct']) for r in cases)))
    eligible=[r for r in ranked if r['eligible']];lead=max(eligible or ranked,key=lambda x:x['score'])['profile'];write(out/'selection.json',dict(frozen_utc=stamp(),lead=lead,development_qualifiers=len(eligible),ranked=sorted(ranked,key=lambda x:x['score'],reverse=True),independently_validated=False,promotion=False));full=[];audits={}
    for cost in COSTS:
        write(out/'progress.json',dict(status='running',phase='later_reused_continuation',profile=lead,cost=cost));book=books[(lead,cost)];book.run_to(END);account=book.result();assert not account['open_positions'] and not account['incomplete_paths'];audit=reconcile(market,book.fills,meta,COSTS[cost],account);audits[cost]=audit;reference=next(r for r in archived if r['cost']==cost);r=dict(profile=lead,cost=cost,durations=PROFILES[lead],account=account,metrics=describe(book),strategies={n:detailed([f for f in book.fills if f['strategy']==n],5000.) for n in lanes},comparison=dict(old_net=reference['net_pnl'],new_net=account['net_pnl'],net_delta=account['net_pnl']-reference['net_pnl'],old_drawdown=reference['quote_drawdown_pct'],new_drawdown=account['quote_drawdown_pct']),independent_validation=False);full.append(r);write(out/f'private_fills_{cost}.json',book.fills);write(out/f'private_decisions_{cost}.json',book.decisions);write(out/'results.json',full);print(json.dumps(dict(cost=cost,lead=lead,**r['comparison'],annualized=r['metrics']['annualized_extrapolation_pct'])),flush=True)
    assert entry_identity(lanes)==identity and all(sha(root/k)==v for k,v in frozen.items());write(out/'independent_audit.json',dict(all_pass=True,records=audits));write(out/'completed.json',dict(completed_utc=stamp(),development_cases=21,later_replays=3,entries_RR_stops_risk_unchanged=True,all_prices_reused=True,no_promotion=True,annual_target_all_costs=all(20<=r['metrics']['annualized_extrapolation_pct']<=30 for r in full),drawdown_below10_all_costs=all(r['account']['quote_drawdown_pct']<10 for r in full)));write(out/'progress.json',dict(status='completed',phase='complete'));print(json.dumps(dict(lead=lead,completed=True)))


if __name__=='__main__':main()
