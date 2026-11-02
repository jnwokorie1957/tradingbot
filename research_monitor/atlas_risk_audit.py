"""Audit frozen Atlas systems, no optimization and no broker execution."""
import argparse,copy,gc,hashlib,json,os,shutil
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from .portfolio_inputs import load_lanes,load_quotes
from .portfolio_discipline_rules import apply
from .atlas_quote_envelopes import feasible_envelopes
from .atlas_audit_engine import replay
from .atlas_metrics import metrics,reconstruct,contribution_metrics,local_day
from .replay_window import assert_fills_in_window

SCENARIOS={
 'standard':dict(spread=1.,fee=6.,slip_ticks=1,entry_extra=0.,exit_delay=0.,margin_multiplier=1.),
 'higher':dict(spread=1.5,fee=12.,slip_ticks=2,entry_extra=0.,exit_delay=0.,margin_multiplier=1.),
 'spread_2x':dict(spread=2.,fee=6.,slip_ticks=1,entry_extra=0.,exit_delay=0.,margin_multiplier=1.),
 'commission_18':dict(spread=1.,fee=18.,slip_ticks=1,entry_extra=0.,exit_delay=0.,margin_multiplier=1.),
 'slippage_4ticks':dict(spread=1.,fee=6.,slip_ticks=4,entry_extra=0.,exit_delay=0.,margin_multiplier=1.),
 'entry_extra_5s':dict(spread=1.,fee=6.,slip_ticks=1,entry_extra=5.,exit_delay=0.,margin_multiplier=1.),
 'exit_delay_1s':dict(spread=1.,fee=6.,slip_ticks=1,entry_extra=0.,exit_delay=1.,margin_multiplier=1.),
 'margin_2x':dict(spread=1.,fee=6.,slip_ticks=1,entry_extra=0.,exit_delay=0.,margin_multiplier=2.),
 'combined_severe':dict(spread=2.,fee=18.,slip_ticks=4,entry_extra=5.,exit_delay=1.,margin_multiplier=2.),
}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root;out=root/'outputs/atlas_risk_audit_v1';out.mkdir(exist_ok=True)
    if (out/'protocol.json').exists():raise FileExistsError('Use a new audit version;do not overwrite financial records')
    code=Path(__file__).parent
    protocol=dict(registered_utc=datetime.now(timezone.utc).isoformat(),objective='ProjectAtlas:controlledrisk,25-40percentannualnettarget,below10percentmaximumdrawdown,notmaximumprofit. Paperonly.',activity='Reconcile and evaluate frozen rules ONLY. No threshold optimization,no new strategy,no risk cap change,no orders/authentication/settings changes.',initial_balance=500.,funded_dates=['2025-12-15','2026-10-30'],warmup='Dec12-14 sourcebars,excludedfromfundedequity',systems={'original':'Originalshared25portfolio,NAS5bothdirections','benchmark':'Strongerpre-recovery-filterbenchmark,NAS5shortonly','recovery':'FrozenbenchmarkplusNAS15efficiency>=.30onlyaftertwoactualnegativeNAS15exits'},scenarios=SCENARIOS,standalone_cases='SPX15,NAS15base,NAS5both,NAS5short,NAS15recovery eachstandard/higher on separate500USDaccounts. Distinguish from shared-account contributions.',max_cases=30,
        metrics='PF=sumpositiveNETfills/abs(sumnegativeNETfills);expectancy=meanNETPnL;avgwin/lossNET;streak counts consecutive negative exits in realized event order. Sharpe=sqrt252*meanweekdayreturn/sampleSD;Sortino=sqrt252*meanreturn/sqrt(mean(min(return,0)^2)),rf=MAR=0. Include all Mon-Fri (holidays included aszero);verify allpositionsintraday before deriving dailyreturnsfromclosedcash. No annual strategy return verified: (end/start)^(365.2425/320)-1 uses ACT elapsed calendardays computed fromDec15inclusive-Oct31exclusive and is extrapolation only,not a forecast or GIPS return.',
        independent_reconciliation='Quote event ordinals are attached to frozen fills. Separate vectorized ledger reconstruction forms cash,costs and every intratrade marked equity observation;compare errors and quoteDD to archived reports. Never use daily/closed-onlyDD as full maximumDD.',
        stress='Onefactorandcombinedsevereadverse assumptions only,not candidate selection. Exitdelay is market-if-touch conditional execution after1second;restingtargetfillbenefit notassumed. Minimumlot and marginrejections retained;no fabricated fills. Pruner uses favorable6fee/1tick/1spread25USDfeasibilitysuperset,extends throughfirstquoteafterworstscheduledexitplusdelay.',
        risk_overlay='No model change or livecapitalmovement. Show fixed500active sleeve plus750segregatedcash,unavailabletomargin/sizing,0cashinterest;25risk=2percenttotal1250. Arithmetic on SAME fills;maxDDrecomputedbyaddingconstant750toeveryquoteequity. Not a validated future below10 guarantee. Amount chosenby2percentplannedrisk convention,not optimized over prices.',
        OOS='Do not label reused dates out-of-sample. PriorseasonalworkexposesolderH1/H4periods too. Current probes returned0inJune/November andshortDec11quote-detailonpreviouslyexposedseasonalperiod. Untouched OOS and genuine historicalwalk-forward areblocked ifno eligible period. Show N/A,nofabricatedscores. Compute chronologicalfixedrulecohorts only as contaminated stabilitydiagnostics,no refitting.',
        original_controls='Current25sharedplannedceiling,25/10per-lanerecovery,naturalstops,legalincrement/currentmarginproxy. Do not modify originalfutures2.50/aggregate5controls. Atlas remainsofflinepaperonly evenifsourceMT5accountisreal.',
        source_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in code.glob('*.py')},reference_hashes={name:hashlib.sha256((root/'outputs'/name/'results.json').read_bytes()).hexdigest() for name in ['three_strategy_shared_account_v1','portfolio_25_discipline_v1']})
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2));snapshot=out/'source';snapshot.mkdir(exist_ok=False)
    for name in protocol['source_hashes']:shutil.copy2(code/name,snapshot/name)
    state=dict(pid=os.getpid(),status='running',phase='load',completed=0,total=30)
    def checkpoint():(out/'worker.json').write_text(json.dumps(state,indent=2))
    checkpoint();lanes,meta,folders=load_lanes(root);sessions=load_quotes(folders);original=copy.deepcopy(lanes);original['NAS5']['direction']='all';systems={'original':original,'benchmark':lanes,'recovery':apply(lanes,'nas15_eff_after2')};rows=[];thin={}
    oldroot=root/'outputs/three_strategy_shared_account_v1';old=json.loads((oldroot/'results.json').read_text());newroot=root/'outputs/portfolio_25_discipline_v1';new=json.loads((newroot/'results.json').read_text())
    def observations(cfg,active):
        key=(cfg['entry_extra'],cfg['exit_delay'],tuple(sorted({l['symbol'] for l in active.values()})))
        if key in thin:return thin[key]
        # Include both NAS5directions in the common envelope,independent of the selected system.
        result={}
        for symbol in key[2]:
            union={}
            for name,lane in original.items():
                if lane['symbol']!=symbol:continue
                for t,s in lane['signals'].items():
                    if lane['direction']=='long_only' and s['side']!=1:continue
                    s=dict(s,entry_at=s['entry_at']+cfg['entry_extra']);union[(t,name)]=s
            result[symbol],_=feasible_envelopes(sessions[symbol],union,meta[symbol],False,540,900,exit_delay=cfg['exit_delay'])
        thin[key]=result;return result
    def run(system,scenario,active,kind='portfolio'):
        cfg=SCENARIOS[scenario];active=copy.deepcopy(active)
        if cfg['entry_extra']:
            for lane in active.values():lane['signals']={t:dict(s,entry_at=s['entry_at']+cfg['entry_extra']) for t,s in lane['signals'].items()}
        capture=scenario in ('standard','higher');state.update(phase='quote_replay',system=system,scenario=scenario,kind=kind);checkpoint()
        r=replay(observations(cfg,active),active,meta,open_risk_cap=25.,scenario=cfg,capture=capture);fills=r.pop('private_fills');trace=r.pop('trace');ids=r.pop('symbol_ids');admissions=r.pop('admissions');assert r['status']=='completed';assert_fills_in_window(fills,'2025-12-15','2026-10-31')
        for a in admissions:
            assert a['used_risk']+a['new_risk']<=25+1e-7 and a['new_risk']<=a['lane_cap']+1e-7 and a['new_margin']<=a['available_margin']+1e-7
            m=meta[active[a['strategy']]['symbol']];assert a['quantity']>=m['volume_min']-1e-9 and abs(a['quantity']/m['volume_step']-round(a['quantity']/m['volume_step']))<1e-7
        parity=None
        if kind=='portfolio' and scenario in ('standard','higher'):
            stress=scenario=='higher'
            if system=='recovery':ref=next(x for x in new if x['stage']=='full' and x['variant']=='nas15_eff_after2' and x['stress']==stress);refroot=newroot
            else:ref=next(x for x in old if x['composition']==('original_both_direction_RSI' if system=='original' else 'short_only_RSI_sensitivity') and x['open_risk_cap']==25 and x['stress']==stress);refroot=oldroot
            expected=json.loads((refroot/f'private_fills_{ref["ledger"]}.json').read_text());assert len(fills)==len(expected) and all({k:f[k] for k in e}==e for f,e in zip(fills,expected)),(system,scenario,'archivedfillparity')
            assert abs(r['quote_marked_drawdown_pct']-ref['quote_marked_drawdown_pct'])<1e-7;parity=dict(exact_financial_fills=len(fills),archived_drawdown_matched=True)
        m=metrics(fills);assert m['all_positions_closed_intraday'];r.update(metrics=m,system=system,scenario=scenario,kind=kind,parity=parity)
        if trace is not None:
            state['phase']='independent_reconstruction';checkpoint();r['audit']=reconstruct(trace,fills,meta,ids,cfg,r['quote_marked_drawdown_pct']);r['contributions']=contribution_metrics(fills)
            reserve_metrics=metrics(fills,initial=1250.);r['audit']['reserve_overlay'].update({k:reserve_metrics[k] for k in ['net_pnl','ending_balance','return_pct','annualized_extrapolation_pct','sharpe_annualized_rf0','sortino_annualized_MAR0']})
            r['cohorts']=[]
            for first,last in [('2025-12-15','2026-03-01'),('2026-03-01','2026-06-01'),('2026-06-01','2026-09-01'),('2026-09-01','2026-10-31')]:
                f=[x for x in fills if first<=local_day(x['exit_at'])<last];initial=500+sum(x['pnl'] for x in fills if local_day(x['exit_at'])<first);subset=metrics(f,initial=initial,first=first,end=last)
                from .audited_run import NY
                lo=datetime.fromisoformat(first).replace(tzinfo=NY).timestamp();hi=datetime.fromisoformat(last).replace(tzinfo=NY).timestamp();q=trace['equity'][(trace['t']>=lo)&(trace['t']<hi)];peaks=np.maximum.accumulate(np.r_[initial,q])[1:];subset['quote_drawdown_pct']=100*float(np.max((peaks-q)/peaks)) if len(q) else 0.;r['cohorts'].append(dict(first=first,end_exclusive=last,interpretation='Reused chronological diagnostic,not untouchedwalk-forward',metrics=subset))
        key=f'{len(rows)+1:02d}';r['ledger']=key;(out/f'private_fills_{key}.json').write_text(json.dumps(fills,indent=2));(out/f'admissions_{key}.json').write_text(json.dumps(admissions,indent=2))
        if trace is not None:np.savez_compressed(out/f'private_quote_trace_{key}.npz',trace=trace)
        rows.append(r);(out/'results.json').write_text(json.dumps(rows,indent=2,allow_nan=False));state['completed']=len(rows);checkpoint();print(json.dumps(dict(case=len(rows),system=system,scenario=scenario,kind=kind,trades=r['outcomes'],net=r['net_pnl'],dd=r['quote_marked_drawdown_pct'],parity=parity)),flush=True);del trace;gc.collect()
    for system in ['original','benchmark','recovery']:
        for scenario in ['standard','higher']:run(system,scenario,systems[system])
    standalone={'SPX15':{'SPX15':lanes['SPX15']},'NAS15_base':{'NAS15':lanes['NAS15']},'NAS5_both':{'NAS5':original['NAS5']},'NAS5_short':{'NAS5':lanes['NAS5']},'NAS15_recovery':{'NAS15':systems['recovery']['NAS15']}}
    for name,active in standalone.items():
        for scenario in ['standard','higher']:run(name,scenario,active,'standalone')
    for scenario in list(SCENARIOS)[2:]:
        for system in ['original','recovery']:run(system,scenario,systems[system])
    (out/'completed.json').write_text(json.dumps(dict(cases=len(rows),original_benchmarks_preserved=True,no_optimization=True,untouched_OOS_status='blocked_noeligibleunusedperiod',genuine_walkforward_status='blocked_noeligiblechronologicalunseenfolds',paper_only=True),indent=2));state.update(status='completed',phase='complete');checkpoint()


if __name__=='__main__':main()
