"""Save a self-contained local account report from completed immutable records."""
import argparse
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def money(value, signed=False):
    n=Decimal(str(round(value,8))).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    return ('+' if signed and n>=0 else '')+f'${n:,.2f}' if n>=0 else f'-${abs(n):,.2f}'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);root=parser.parse_args().root
    folder=root/'outputs/three_strategy_shared_account_v1';completed=json.loads((folder/'completed.json').read_text());rows=json.loads((folder/'results.json').read_text());assert len(rows)==completed['cases']==8
    protocol=json.loads((folder/'protocol.json').read_text())
    for name,digest in protocol['code_hashes'].items():assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==digest,(name,'source changed')
    audit=[]
    for r in rows:
        fills=json.loads((folder/f'private_fills_{r["ledger"]}.json').read_text())
        assert len(fills)==r['outcomes'] and abs(sum(f['pnl'] for f in fills)-r['net_pnl'])<1e-7
        assert abs(sum(m['net_pnl'] for m in r['monthly'].values())-r['net_pnl'])<1e-7
        assert sum(m['trades'] for m in r['monthly'].values())==r['outcomes']
        if r['composition']=='original_both_direction_RSI' and r['open_risk_cap']==75:
            for name in ['SPX15','NAS15','NAS5']:
                if name=='SPX15':ref=root/f'outputs/spx15_over60_v1/private_fills_both_{r["stress"]}.json'
                else:
                    d=root/('outputs/nasdaq_opportunities_v1' if name=='NAS15' else 'outputs/nasdaq_two_strategy_v1')
                    refrow=next(v for v in json.loads((d/'results.json').read_text()) if v['stress']==r['stress'] and (v['family']=='breakout' and v['variant']=='earlier_full' if name=='NAS15' else v['family']=='rsi2' and v['timeframe_minutes']==5 and v['variant']=='baseline'))
                    ref=d/f'private_fills_{refrow["ledger"]}.json'
                expected=json.loads(ref.read_text()); actual=[f for f in fills if f['strategy']==name]
                assert len(actual)==len(expected) and all({k:f[k] for k in e}==e for f,e in zip(actual,expected)),(name,r['stress'],'combined ledger parity')
                audit.append(dict(strategy=name,stress=r['stress'],actual_count=len(actual),expected_count=len(expected),exact_financial_fills=True))
    (folder/'reconciliation_audit.json').write_text(json.dumps(dict(monthly_and_cash_reconciled_cases=8,combined_75_ledger_parity=audit),indent=2))
    mainrows=[r for r in rows if r['composition']=='original_both_direction_RSI']
    safe=next(r for r in mainrows if r['open_risk_cap']==25 and not r['stress']);higher=next(r for r in mainrows if r['open_risk_cap']==25 and r['stress'])
    lines=['# Three-strategy shared account','', 'Starting balance: $500.00. Funded period: December 15, 2025–October 30, 2026. All figures are modeled USD, after assumed costs. Previously inspected data; no independent confirmation.','',
           '| Total open planned risk | Costs | Ending balance | Net P&L | Return | Trades | Win rate | Maximum drawdown |', '|---|---|---|---|---|---|---|---|']
    for r in mainrows:lines.append(f'| ${r["open_risk_cap"]:.0f} | {"Higher" if r["stress"] else "Standard"} | {money(r["ending_balance"])} | {money(r["net_pnl"],True)} | {r["return_pct"]:+.2f}% | {r["outcomes"]} | {r["win_rate"]:.2f}% | {r["quote_marked_drawdown_pct"]:.2f}% |')
    lines.extend(['','Strategies: SPX500 15m confirmed long morning breakout at 1.5R; NAS100 15m selective long breakout 09:00–15:00 New York at 1.5R; NAS100 5m original both-direction RSI-2 with native exits and ATR stop (no fixed RR).', '', 'Each strategy retains $25 normal risk / $10 after two negative exits and recovery trend confirmation. Shared budget and gross margin constrain admissions. Risk caps are fixed dollars, not compounding percentages. $75 total is a separate higher-exposure comparison, not the $25 portfolio ceiling.', '', 'Drawdown includes marked open positions, spreads, adverse slippage and estimated closing fees. Historical fees, clock/DST, contract and margin terms are unverified; margin uses current .005 notional proxy and no verified historical stop-out model. This is hindsight development on reused prices, not a live result or independent validation.'])
    (folder/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    def table(selected):
        result='<table><thead><tr><th>Open risk ceiling</th><th>Costs</th><th>Ending balance</th><th>Net P&L</th><th>Return</th><th>Trades</th><th>Win rate</th><th>Drawdown</th></tr></thead><tbody>'
        for r in selected:result+=f'<tr><td>${r["open_risk_cap"]:.0f}</td><td>{"Higher" if r["stress"] else "Standard"}</td><td>{money(r["ending_balance"])}</td><td class="{"positive" if r["net_pnl"]>=0 else "negative"}">{money(r["net_pnl"],True)}</td><td>{r["return_pct"]:+.2f}%</td><td>{r["outcomes"]}</td><td>{r["win_rate"]:.2f}%</td><td>{r["quote_marked_drawdown_pct"]:.2f}%</td></tr>'
        return result+'</tbody></table>'
    months=list(safe['monthly']); values=[500]+[safe['monthly'][m]['ending_balance'] for m in months]
    low=min(values+[500])-20;high=max(values+[500])+20;W,H=1000,250
    coords=[(30+i*(W-60)/(len(values)-1),H-25-(v-low)/(high-low)*(H-50)) for i,v in enumerate(values)]
    path='M '+' L '.join(f'{x:.2f},{y:.2f}' for x,y in coords)
    chart=f'<svg viewBox="0 0 {W} {H}" aria-label="Monthly closed account balance, standard costs and $25 shared open risk"><path d="{path}" fill="none" stroke="#63e1bc" stroke-width="3"/>'
    for (x,y),v in zip(coords,values):chart+=f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#63e1bc"><title>{money(v)}</title></circle>'
    chart+='</svg>'
    monthly='<table><thead><tr><th>Month</th><th>Standard net</th><th>Higher-cost net</th><th>Standard balance</th><th>Higher-cost balance</th><th>Trades std / higher</th></tr></thead><tbody>'
    for m in months:
        a=safe['monthly'][m];b=higher['monthly'].get(m,dict(net_pnl=0,ending_balance=0,trades=0))
        monthly+=f'<tr><td>{m}</td><td class="{"positive" if a["net_pnl"]>=0 else "negative"}">{money(a["net_pnl"],True)}</td><td class="{"positive" if b["net_pnl"]>=0 else "negative"}">{money(b["net_pnl"],True)}</td><td>{money(a["ending_balance"])}</td><td>{money(b["ending_balance"])}</td><td>{a["trades"]} / {b["trades"]}</td></tr>'
    monthly+='</tbody></table>'
    contributions='<table><thead><tr><th>Strategy</th><th>Standard net</th><th>Higher-cost net</th><th>Trades std / higher</th></tr></thead><tbody>'
    labels={'SPX15':'SPX500 · 15m confirmed breakout · 1.5R','NAS15':'NAS100 · 15m selective breakout · 1.5R','NAS5':'NAS100 · 5m RSI-2 · native exits'}
    for name,label in labels.items():
        a=safe['breakdown'][name];b=higher['breakdown'][name]
        contributions+=f'<tr><td>{label}</td><td class="{"positive" if a["net_pnl"]>=0 else "negative"}">{money(a["net_pnl"],True)}</td><td class="{"positive" if b["net_pnl"]>=0 else "negative"}">{money(b["net_pnl"],True)}</td><td>{a["trades"]} / {b["trades"]}</td></tr>'
    contributions+='</tbody></table>'
    rr=json.loads((root/'outputs/breakout_rr_comparison_v1/results.json').read_text());rr_table='<table><thead><tr><th>Breakout</th><th>Target R</th><th>Net std / higher</th><th>Drawdown std / higher</th><th>Trades std / higher</th><th>Target hits std / higher</th></tr></thead><tbody>'
    for symbol in ['SPX500','NAS100']:
        for target in [1,1.5,2,3,5]:
            pair=[r for r in rr if r['symbol']==symbol and r['rr']==target];a=next(r for r in pair if not r['stress']);b=next(r for r in pair if r['stress'])
            rr_table+=f'<tr><td>{symbol} 15m</td><td>{target:g}R</td><td>{money(a["ending_balance_after_modeled_costs"]-500,True)} / {money(b["ending_balance_after_modeled_costs"]-500,True)}</td><td>{a["quote_marked_drawdown_pct"]:.2f}% / {b["quote_marked_drawdown_pct"]:.2f}%</td><td>{a["outcomes"]} / {b["outcomes"]}</td><td>{a["target_hits"]} / {b["target_hits"]}</td></tr>'
    rr_table+='</tbody></table>'
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Trade Dashboard</title><style>
    :root{color-scheme:dark;font-family:Inter,Segoe UI,system-ui,sans-serif;color:#ebf2ff;background:#0b101b}*{box-sizing:border-box}body{margin:0;padding:36px;max-width:1500px;margin:auto;background:radial-gradient(ellipse at 90% 0%,#172d3b,transparent 50%)}h1{font-size:32px;letter-spacing:-1px;margin:8px 0}h2{font-size:19px;margin:0 0 15px}p{color:#a8b9cd;line-height:1.65}.eyebrow{color:#63e1bc;text-transform:uppercase;letter-spacing:2px;font-size:11px}.pill{padding:6px 12px;border:1px solid #334c59;border-radius:99px;font-size:12px;color:#90d8c5;float:right}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:26px 0}.card,section{background:#121d2cdb;border:1px solid #263548;border-radius:18px;padding:22px;margin-bottom:20px;box-shadow:0 16px 40px #0002;transition:transform .35s ease,background .35s ease}.card:hover{transform:translateY(-3px);background:#192a3b}.card small{color:#a8b9cd}.metric{font-size:28px;font-weight:650;margin:12px 0 6px}.positive{color:#63e1bc}.negative{color:#ff879a}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;white-space:nowrap}th{text-align:left;font-weight:500;color:#8fa4bc;font-size:12px;border-bottom:1px solid #344052;padding:13px 12px}td{padding:14px 12px;border-bottom:1px solid #243244}tbody tr{transition:background .3s ease}tbody tr:hover{background:#1d3042}.note{font-size:13px;color:#90a3b8}.chart-foot{display:flex;justify-content:space-between;color:#8fa4bc;font-size:12px}svg{width:100%;display:block}svg path{stroke-dasharray:3000;stroke-dashoffset:3000;animation:draw 2s ease forwards}@keyframes draw{to{stroke-dashoffset:0}}details summary{cursor:pointer;color:#b0c8e8;margin-bottom:16px}code{font-size:11px;word-break:break-all;color:#93a7be}@media(max-width:900px){body{padding:18px}.cards{grid-template-columns:repeat(2,1fr)}.metric{font-size:24px}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}svg path{stroke-dashoffset:0}}
    </style></head><body>'''
    page+=f'<span class="pill">Completed · Offline historical replay</span><div class="eyebrow">Shared account · Three strategies</div><h1>Trade Dashboard</h1><p>December 15, 2025 – October 30, 2026 · One $500 account · USD</p><div class="cards"><div class="card"><small>Ending balance · $25 shared ceiling</small><div class="metric">{money(safe["ending_balance"])}</div><small>Standard cost model</small></div><div class="card"><small>Net account change</small><div class="metric positive">{money(safe["net_pnl"],True)}</div><small>{safe["return_pct"]:+.2f}% after assumed costs</small></div><div class="card"><small>Maximum marked drawdown</small><div class="metric">{safe["quote_marked_drawdown_pct"]:.2f}%</div><small>Includes unrealized positions</small></div><div class="card"><small>Closed trades · win rate</small><div class="metric">{safe["outcomes"]} · {safe["win_rate"]:.1f}%</div><small>Shared capital and recovery state</small></div></div>'
    page+=f'<section><h2>Monthly closed balance</h2>{chart}<div class="chart-foot"><span>December 2025 · $500 start</span><span>October 2026 · {money(safe["ending_balance"])}</span></div><p class="note">Standard cost model, original RSI composition, $25 shared open-risk ceiling. This line shows month-end closed balances; drawdown is calculated separately from all retained intratrade quote marks.</p></section>'
    page+=f'<section><h2>One account, two exposure limits</h2><div class="scroll">{table(mainrows)}</div><p class="note">$25 shared ceiling is 5% of initial capital. $25 per strategy permits up to $75 combined, or 15% of initial capital, before legal lot and margin constraints. The higher exposure comparison does not change the original bot controls. Gap losses can exceed planned risk.</p></section>'
    page+=f'<section><h2>Strategy contributions · $25 shared ceiling</h2><div class="scroll">{contributions}</div><p class="note">SPX 15m: confirmed long 09:45–12:00 New York, prior-session boundary, H1 alignment, no chasing, strong close and directional efficiency. NAS 15m: selective long 09:00–15:00 with prior-session boundary, H1 alignment and no chasing. Both use 1.5R targets and one-hour expiry. NAS 5m: original both-direction RSI-2/SMA200, ATR stop and native RSI exits, no fixed R target.</p></section>'
    page+=f'<section><h2>Monthly account results · $25 shared ceiling</h2><div class="scroll">{monthly}</div></section>'
    page+=f'<section><details><summary>Separate short-only RSI composition</summary><div class="scroll">{table([r for r in rows if r["composition"]=="short_only_RSI_sensitivity"])}</div><p class="note">Exploratory sensitivity using the newer short-only NAS 5m candidate. It is separate from the original three-strategy composition; small samples do not establish a better future strategy.</p></details></section>'
    page+=f'<section><details><summary>Earlier target-distance comparison · separate $500 accounts</summary><div class="scroll">{rr_table}</div><p class="note">These are individual strategy runs, not the combined account. The shared-account comparison preserves 1.5R. Larger targets are often replaced by the fixed one-hour exit; nominal target R is not realized return R. SPX 5R reached no 5R targets in either cost case.</p></details></section>'
    page+='<section><h2>Interpretation and evidence</h2><p>These strategies and filters were selected after repeated use of the same historical period. A profitable replay is not independent repeatability or a forecast. Fees, historical clock/DST, contract terms, margins and forced-liquidation policy remain unverified. Current read-only MT5 observations support hedging account mode, current lot increments and a .005-notional margin proxy; gross margin receives no offset credit.</p><p>Standard / higher assumptions: historical bid/ask with spread 1× / 1.5×; adverse slippage 1 / 2 current ticks; roundtrip commission $6 / $12 per lot. Costs can change recovery state and later eligibility, so higher-cost trade counts and P&L need not follow the same path. Each strategy uses $25 planned risk, reduced to $10 after two negative exits with recovery trend confirmation; a positive exit restores $25. Shared cash, marked equity, margin and total planned open risk can resize or reject entries.</p>'
    page+=f'<p class="note">All six single-strategy standard/higher ledgers reproduce the archived fills exactly. Three shared-account synthetic checks and 98 repository checks passed. Completed cases: 8. No broker execution.</p><code>Protocol SHA-256: {hashlib.sha256((folder/"protocol.json").read_bytes()).hexdigest()}<br>Results SHA-256: {hashlib.sha256((folder/"results.json").read_bytes()).hexdigest()}</code></section></body></html>'
    assert not re.search(r'\b(demo|test)\b',re.sub('<[^>]+>',' ',page),re.I)
    (folder/'report.html').write_text(page,encoding='utf-8')
    snapshot=folder/'source';snapshot.mkdir(exist_ok=False)
    for name in protocol['code_hashes']: (snapshot/name).write_bytes(Path(__file__).with_name(name).read_bytes())
    (folder/'report_summary.json').write_text(json.dumps(dict(generated_utc=datetime.now(timezone.utc).isoformat(),period=protocol['dates'],main_composition='original_both_direction_RSI',main_rows=mainrows,results_sha256=hashlib.sha256((folder/'results.json').read_bytes()).hexdigest()),indent=2))
    print((folder/'summary.md').read_text())


if __name__=='__main__':main()
