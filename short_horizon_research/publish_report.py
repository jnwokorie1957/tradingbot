"""Build current local overview and sanitized aggregate Git artifacts."""
import argparse,html,json,re
from pathlib import Path
from . import dashboard
from .run import write,stamp
from .data import sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();out=root/'outputs/short_horizon_mt5'
    dashboard.main();page=(out/'index.html').read_text(encoding='utf-8');versions=['short_horizon_mt5_v2','short_horizon_mt5_v3','short_horizon_mt5_v4'];records={v:json.loads((root/'outputs'/v/'results.json').read_text()) for v in versions};count=sum(len(v['development'])*2 for v in records.values())
    last=records[versions[-1]];lines=[];friendly={'prior_session_reclaim':'Prior-session reclaim','time_of_day_breakout':'Time-of-day breakout'}
    for c in last['development']:
        for cost,m in c['metrics'].items():
            values=[c['symbol'],str(c['minutes'])+'m',friendly[c['family']],c['rr'],cost,m['trades'],f"{m['win_rate']:.2f}%" if m['win_rate'] is not None else '—',f"${m['net_pnl']:+,.2f}",f"{m['drawdown_pct']:.2f}%",'FAIL']
            lines.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in values)+'</tr>')
    addition='<h2>Session-level and volatility families · latest completed batch</h2><p>32 further development cost cases, registered before financial replay. No candidate met the frozen selection rule, so no later-period selection was forced. December 15, 2025–May 31, 2026. Higher-cost outcomes and all failed cases are retained.</p><div class="scroll"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['Market','Candle','Approach','RR','Costs','Trades','Win rate','Net P&L','Quote drawdown','Target'])+'</tr></thead><tbody>'+''.join(lines)+'</tbody></table></div>'
    page=page.replace('<h2>Execution risk retained</h2>',addition+'<h2>Execution risk retained</h2>').replace('>96<',f'>{count}<').replace('6 families · 2 markets','8 families · 2 markets')
    page=page.replace('The next separate hypotheses are time-of-day volatility breakout and prior-session level reclaim. Their exact rules must be registered before financial replay.','Time-of-day volatility breakout and prior-session reclaim have now completed their registered batch; neither qualified. Any further hypothesis requires a new protocol before financial replay.')
    page=page.replace('<h2>Evidence and next work</h2>','<p><a href="../short_horizon_mt5_v4/report.html">Latest families · complete record</a> · <a href="../short_horizon_mt5_v4/audit.json">Latest audit</a></p><h2>Evidence and next work</h2>')
    names=friendly|{'channel_retest':'Channel pullback','band_reentry':'Band reentry','opening_range_failure':'Opening-range failure','inside_bar_trap':'Inside-bar trap','trend_ma_reclaim':'Trend MA reclaim','rsi2_trend_reclaim':'RSI2 trend reclaim'};leaders=[]
    for symbol in ['NAS100','SPX500']:
        for minutes in [1,5]:
            group=[d for value in records.values() for d in value['development'] if d['symbol']==symbol and d['minutes']==minutes]
            best=max(group,key=lambda d:d['metrics']['higher']['net_pnl']);m=best['metrics']['higher']
            values=[symbol,f'{minutes}m',names[best['family']],best['rr'],m['trades'],f"{m['win_rate']:.2f}%",f"${m['net_pnl']:+,.2f}",f"{m['drawdown_pct']:.2f}%",'FAIL']
            leaders.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in values)+'</tr>')
    page=re.sub(r'(<h2>Development leaders by market and candle</h2>.*?<tbody>).*?(</tbody></table></div>)',lambda match:match[1]+''.join(leaders)+match[2],page,flags=re.S)
    (out/'index.html').write_text(page,encoding='utf-8');write(out/'current.json',dict(updated_utc=stamp(),batches=versions,development_cost_cases=count,qualified=0,paper_only=True,independently_validated=False))
    public=root/'work/tradingbot/research/mt5-short-horizon/2026-11-02';public.mkdir(parents=True,exist_ok=True)
    summary=dict(updated_utc=stamp(),study='Separate NAS100/SPX500 1m/5m discovery',paper_only=True,initial_equity_per_isolated_candidate=5000,per_trade_risk='min(0.5% equity,$25) including estimated costs',combined_risk='1% equity gross; isolated one-position candidate books, no inferred combined portfolio',pauses='2% daily loss / 10% peak equity drawdown entry pauses; no daily quota',available_native_minute_dates=['2025-12-12','2026-10-30'],financial_development_dates=['2025-12-15','2026-05-31'],later_diagnostic_dates=['2026-06-01','2026-10-30'],development_cost_cases=count,qualified=0,prior_prices_exposed=True,independent_validation=False,limitations=['Broker index proxies are not MNQ/MES exchange futures','Native minute history is about 10.5 months, not 12-24 months','Fees, historic clock, margin and liquidity are unverified assumptions','Planned stops and pause thresholds do not guarantee realized caps','Multiple configurations share prices and are not independent samples'],batches={v:{k:d[k] for k in ['completed_utc','protocol_sha256','development','challenge','clock_stress','preserved_hashes_verified']}|dict(latency5=d.get('latency5',[])) for v,d in records.items()},local_raw_prices_or_individual_ledgers_published=False)
    write(public/'summary.json',summary)
    public_page=re.sub(r'<a href="(?!https?://)[^"]+">(.*?)</a>',r'\1 (local record)',page)
    public_page=public_page.replace('</main>','<h2>Aggregate record</h2><p><a href="summary.json">Download all aggregate metrics</a>. Detailed raw prices, individual ledgers, protocols and immutable source snapshots remain local.</p></main>')
    (public/'index.html').write_text(public_page,encoding='utf-8')
    (public/'README.md').write_text(f'''# Separate MT5 short-horizon discovery — November 2, 2026

{count} completed cost-adjusted development runs across eight fixed families, two markets, two native candle intervals and two reward targets. **No candidate qualifies for promotion.** The retained Nasdaq 5m channel-pullback diagnostic is below 60% win rate and lacks independent validation.

Open `index.html` for Trade Dashboard and `summary.json` for every aggregate metric, including failed cases. Source lives in `short_horizon_research/` at repository root. Original Atlas research and risk controls are unchanged.

Development: December 15, 2025–May 31, 2026. Later diagnostics for development-selected candidates: June 1–October 30, 2026. All historical prices were previously exposed, so later diagnostics are not untouched validation. Genuine MNQ/MES comparison and fresh forward validation remain pending.

Each candidate account begins at $5,000, with min(0.5% equity,$25) all-in planned trade risk, 1% gross planned open-risk limit, 2% daily-loss and 10% peak-equity drawdown entry pauses. These are planned controls, not guaranteed realized loss caps. Costs, historic clock, margin and fill liquidity remain estimates. No live orders or broker execution are enabled. Accounts are isolated; their profits cannot be added to infer a portfolio.

Raw prices, individual trade ledgers, runtime state and account identifiers are excluded from this public aggregate artifact. Older result files and protocols remain preserved locally.
''',encoding='utf-8')
    checkpoint=out/'notification_checkpoint.json';old=json.loads(checkpoint.read_text()) if checkpoint.exists() else {};old.update(updated_utc=stamp(),reported_results_sha256={v:sha(root/'outputs'/v/'results.json') for v in versions},qualified=0,completed_cost_cases=count,report='Latest32casebatchcompleted; no qualified improvement; all results retained');write(checkpoint,old)
    print(json.dumps(dict(public_folder=str(public),development_cost_cases=count,qualified=0,paper_only=True)))


if __name__=='__main__':main()
