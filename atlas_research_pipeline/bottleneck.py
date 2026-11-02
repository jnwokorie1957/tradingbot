"""Read-only attribution of saved paired-ledger performance;no financial rerun."""
import argparse,json
from collections import Counter
from pathlib import Path
from statistics import mean
from atlas_exit_research.data import write,sha,stamp

RISK_REASONS={'minimum_lot_above_trade_risk','shared_gross_risk_budget','broker_margin_plus_loss_reserve','conflicting_same_symbol_exposure','daily_2pct_loss_pause','portfolio_10pct_drawdown_pause','duplicate_economic_intent','quantity_rounding_or_cash'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve();source=root/'outputs/atlas_pair_holding_v1';out=root/'outputs/atlas_pair_bottleneck_audit_v1';out.mkdir(exist_ok=False);names=['results.json','opportunity_audit.json','paired_trade_audit.json','protocol.json']+[f'private_{kind}_{c}.json'for kind in ['fills','decisions']for c in ['standard','higher','severe']];before={n:sha(source/n)for n in names};rows=json.loads((source/'results.json').read_text());fills={c:json.loads((source/f'private_fills_{c}.json').read_text())for c in ['standard','higher','severe']};records=[]
    for r in rows:
        c=r['cost'];ds=json.loads((source/f'private_decisions_{c}.json').read_text());pure=[d for d in ds if d['status']!='EXECUTED'and d.get('reasons')and set(d['reasons'])<=RISK_REASONS];lanes={};assert abs(sum(f['pnl']for f in fills[c])-r['metrics']['net_pnl'])<1e-6
        for lane in ['SPX15','NAS15']:
            fs=[f for f in fills[c]if f['strategy']==lane];ls=[d for d in ds if d['lane']==lane];ps=[d for d in pure if d['lane']==lane];lanes[lane]=dict(raw_decisions=len(ls),executed=len(fs),noncapital_rules_passed=len(fs)+len(ps),capital_exposure_only=len(ps),minimum_lot_above_cap=sum('minimum_lot_above_trade_risk'in d['reasons']for d in ps),veto_combinations=dict(Counter('|'.join(sorted(d['reasons']))for d in ps)),net=sum(f['pnl']for f in fs),win_rate=100*sum(f['pnl']>0 for f in fs)/len(fs),exit_reasons=dict(Counter(f['reason']for f in fs)),average_win=mean(f['pnl']for f in fs if f['pnl']>0),average_loss=mean(f['pnl']for f in fs if f['pnl']<0))
        m=r['metrics'];records.append(dict(cost=c,net=m['net_pnl'],expectancy=m['expectancy_dollars'],trades_per_month=m['trades_per_month'],average_win=m['average_win'],average_loss=m['average_loss'],commission=m['commission_dollars'],slippage=m['modeled_roundtrip_slippage_dollars'],lanes=lanes))
    base={f['id']:f for f in fills['standard']};effects={}
    for c in ['higher','severe']:
        target={f['id']:f for f in fills[c]};common=set(base)&set(target);lost=set(base)-set(target);added=set(target)-set(base);a=sum(base[k]['pnl']-target[k]['pnl']for k in common);b=sum(base[k]['pnl']for k in lost);d=sum(target[k]['pnl']for k in added);total=sum(f['pnl']for f in base.values())-sum(f['pnl']for f in target.values());assert abs(a+b-d-total)<1e-6;effects[c]=dict(common_trades=len(common),standard_only=len(lost),other_only=len(added),common_net_reduction=a,standard_only_net=b,other_only_net=d,total_net_reduction=total,interpretation='Composition attribution,not direct fee-only causal effect;entries,quantities and stateful recovery can change across costs')
    assert all(sha(source/n)==h for n,h in before.items());m=records[0];required={str(t):5000*t/m['expectancy']for t in [.15,.20,.25]};result=dict(created_utc=stamp(),period=['2025-12-15','2026-10-30'],initial_equity=5000,records=records,cost_composition_effects=effects,arithmetic_only_monthly_target=dict(current_trades_per_month=m['trades_per_month'],current_expectancy=m['expectancy'],required_trades_at_unchanged_expectancy=required,interpretation='Illustrative starting-equity arithmetic only,not a strategyforecast or permission to multiply correlated trades/risk'),prior_opportunity_audit_provenance='Original holding study opportunity_audit.json was sourced from60minutecontrol decisions,not the selectedNAS90 ledgers. Both archived unchanged;this audit labels NAS90 explicitly.',interpretation='Raw signals and noncapital-rule passes are NOT proven missed winners or fully executable trades. No rejected trade outcome is invented. All prices already exposed;no independentvalidation.',source_sha256=before,originals_unchanged=True,active_paper_changed=False,new_financial_simulation=False);write(out/'results.json',result);write(out/'completed.json',dict(at_utc=stamp(),all_arithmetic_pass=True,originals_preserved=True));print(json.dumps(result))


if __name__=='__main__':main()
