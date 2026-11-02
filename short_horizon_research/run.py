"""Finite, isolated MT5 discovery batch. Never connects to a trading terminal."""
import argparse
import html
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .data import NY, archives, candles, quotes, sha
from .engine import Account, COSTS, RISK
from .signals import Signals, FAMILIES, HOLIDAYS, EARLY_CLOSE

VERSION='short_horizon_mt5_v2'
SOURCES=[{'title':'John Bollinger: band rules','url':'https://www.bollingerbands.com/bollinger-band-rules','role':'Band reentry is our adaptation, not a claimed replication; band touches alone are not signals.'},
 {'title':'Dan Chesler: Hikkake','url':'https://www.peterlbrandt.com/wp-content/uploads/2016/06/Hikkake-Dan-Chesler.pdf','role':'Original-author research lead; close-confirmed trap is our adaptation. PDF retrieval unavailable at registration.'}]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(path)


def stamp():return datetime.now(timezone.utc).isoformat()


def qualify(results,minimum):
    return all(r['trades']>=minimum and (r['win_rate'] or 0)>=60 and r['net_pnl']>0 and (r['profit_factor'] or 0)>=1.2 and r['drawdown_pct']<10 for r in results.values())


def metrics(account,start,end,cut=None):
    result=account.result(start,end)
    if cut is not None:
        fills=account.fills[cut:];v=[f['pnl'] for f in fills];w=[x for x in v if x>0];l=[x for x in v if x<0]
        start_cash=account.fills[cut-1]['equity_after'] if cut else 5000.
        result.update(trades=len(v),wins=len(w),win_rate=100*len(w)/len(v) if v else None,net_pnl=sum(v),initial_equity=start_cash,ending_balance=account.cash,profit_factor=sum(w)/-sum(l) if l else None,expectancy=sum(v)/len(v) if v else None,average_win=sum(w)/len(w) if w else None,average_loss=sum(l)/len(l) if l else None)
    days=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).days
    result['annualized_return_pct_estimate']=100*((result['ending_balance']/result['initial_equity'])**(365.25/max(days,1))-1)
    result['trades_per_week']=result['trades']/(days/7);result['trades_per_month']=result['trades']/(days/30.4375)
    losses=longest=0
    for f in (account.fills if cut is None else account.fills[cut:]):
        losses=losses+1 if f['pnl']<0 else 0;longest=max(longest,losses)
    result['maximum_consecutive_losses']=longest
    return result


def report(out,result):
    def table(rows):
        lines=[]
        for row in rows:
            for cost,m in row['metrics'].items():
                lines.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [row['symbol'],str(row['minutes'])+'m',row['family'],row['rr'],cost,m['trades'],f"{m['win_rate']:.2f}%" if m['win_rate'] is not None else '—',f"${m['net_pnl']:+,.2f}",f"{m['profit_factor']:.2f}" if m['profit_factor'] else '—',f"{m['drawdown_pct']:.2f}%",row.get('decision','Development')])+'</tr>')
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['Market','Candle','Approach','RR','Costs','Trades','Win rate','Net P&L','PF','Quote drawdown','Decision'])+'</tr></thead><tbody>'+''.join(lines)+'</tbody></table></div>'
    body='''<!doctype html><html><head><meta charset="utf-8"><title>Trade Dashboard</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    :root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#090f1c;color:#dce7f4;font:15px system-ui;padding:36px}main{max-width:1500px;margin:auto}h1{font-size:34px;margin:4px 0}h2{margin-top:34px;font-size:21px}.eyebrow{color:#64d9cc;letter-spacing:3px;text-transform:uppercase}p{line-height:1.6;color:#aebcd2;max-width:1100px}.cards{display:flex;gap:16px;flex-wrap:wrap}.card{background:#121e32;border:1px solid #27344a;border-radius:16px;padding:22px;flex:1;min-width:220px}.value{font-size:26px;font-weight:650;color:#fff}.scroll{overflow:auto;border:1px solid #27344a;border-radius:12px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{text-align:left;padding:13px;border-bottom:1px solid #263044}th{background:#17243a;color:#8ed8cf}a{color:#77c4ff}.flag{color:#f1be6b}details{margin:24px 0}summary{cursor:pointer}td{transition:background .3s ease}tr:hover td{background:#19263b}</style></head><body><main>'''
    body+='<div class="eyebrow">Separate short-horizon study · Paper only</div><h1>Trade Dashboard</h1><p>NAS100 and SPX500 broker-index history. These instruments are proxies for later MNQ/MES comparison, with different contracts, costs and execution conditions.</p>'
    n=sum(x.get('decision')=='HISTORICAL SCREEN PASS — INDEPENDENT VALIDATION PENDING' for x in result.get('challenge',[]))
    body+=f'<div class="cards"><div class="card">Starting balance per isolated candidate<div class="value">$5,000</div></div><div class="card">Historical screen passes<div class="value">{n}</div></div><div class="card">Independent validation<div class="value">Pending</div></div><div class="card">Usable minute coverage<div class="value">~10½ months</div></div></div>'
    body+='<p class="flag">Neither 12 nor 24 months of native minute coverage is available in the connected MT5 archive. Older returned records are hourly/daily and excluded. All financial results below are modeled, not broker fills. The historical price period was exposed in earlier projects: chronological later-period checks are not untouched independent evidence.</p>'
    body+='<h2>Frozen selections · June 1–October 30, 2026</h2><p>Selected once from December 15–May 31. No later-period reselection. Drawdown is continuous quote-equity drawdown since development began, including intratrade losses. A diagnostic selection is not a qualifying system.</p>'+table(result.get('challenge',[]))
    body+='<h2>Alternative historical clock · fixed UTC+3</h2>'+table(result.get('clock_stress',[]))
    body+='<details><summary>All development configurations · December 15, 2025–May 31, 2026</summary>'+table(result.get('development',[]))+'</details>'
    body+='<h2>Risk and evidence</h2><p>All-in planned trade risk: min(0.5% of equity, $25). Gross planned open risk: 1% of equity. Daily loss entry pause: 2%. Peak-equity drawdown entry pause: 10%. One position per isolated candidate; no arbitrary daily count quota. Pauses and stops cannot guarantee realized loss limits. No combined new-strategy portfolio is inferred from isolated candidate results.</p><p>Standard costs use recorded bid/ask, one adverse tick per side and $6 per full lot round trip. Higher costs use 1.5× recorded spread, two ticks per side and $12 per full lot. Commissions, historical clock and margin are estimates. Current lot increments and contract values are verified snapshots, not verified historical terms. Quote availability does not prove fill liquidity. Signals use closed candles with a 60-second execution delay.</p>'
    body+='<p>Historical gate: at least 100 development and 30 later trades; ≥60% net-positive trade rate, positive net P&L, PF≥1.2 and quote drawdown below 10% at both costs, plus both full-history clock runs. Passing remains a discovery screen and requires fresh prospective or actual micro-futures validation. Multiple comparisons and reused prices limit inference.</p>'
    body+='<h2>Files and sources</h2><p><a href="results.json">Complete metrics</a> · <a href="protocol.json">Frozen protocol</a> · <a href="selection.json">Selection record</a> · <a href="coverage.json">Coverage</a></p>'
    body+='<p>'+' · '.join(f'<a href="{s["url"]}">{html.escape(s["title"])}</a>' for s in SOURCES)+'</p><p>Updated '+html.escape(stamp())+'</p></main></body></html>'
    (out/'report.html').write_text(body,encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();out=root/'outputs'/VERSION
    if (out/'protocol.json').exists():raise SystemExit('Existing registered run: preserve it; do not rerun or overwrite.')
    src=Path(__file__).parent
    archive=archives(root);meta=json.loads((out/'data/contract_snapshot.json').read_text());preserved=json.loads((out/'preserved_research_hashes.json').read_text())
    configs=[dict(symbol=s,minutes=m,family=f,rr=rr,id=f'{s}_{m}m_{f}_rr{rr:g}') for s in archive for m in [1,5] for f in FAMILIES for rr in [1.,1.5]]
    protocol=dict(registered_utc=stamp(),paper_only=True,version=VERSION,risk=RISK,costs=COSTS,configs=configs,source_sha256={x.name:sha(x) for x in src.glob('*.py')},inputs=archive,contract_sha256=sha(out/'data/contract_snapshot.json'),development=['2025-12-15','2026-06-01'],later=['2026-06-01','2026-10-31'],primary_clock='UTC+3 during New York DST, otherwise UTC+2; inferred and unverified',clock_sensitivity='fixed UTC+3',selection='One per symbol/timeframe. First prefer all development target gates (100 trades, >=60% win, positive net, PF>=1.2, DD<10% at BOTH costs); then maximize minimum net across costs. If no target qualifier: diagnostic with >=30 trades, positive net at BOTH costs, DD<10%; else no selection. No later reselection.',later_gate='>=30 trades, >=60% wins, positive net, PF>=1.2, continuous DD<10 at BOTH costs; primary full and fixed3 full also qualify >=100 trades',independent_validation=False,prior_price_exposure=True,minimum_data_warning='Native minute coverage starts 2025-12-12; older sparse records excluded',sources=SOURCES)
    protocol.update(calendar=dict(holidays=sorted(HOLIDAYS),early_close=EARLY_CLOSE,source='https://www.nyse.com/trade/hours-calendars'),replacement_reason='v1 failed closed-market liquidation on 2026-01-19; holiday calendar corrected without changing strategy parameters. v1 protocol, source and failure retained.')
    write(out/'protocol.json',protocol);write(out/'protocol_identity.json',dict(sha256=sha(out/'protocol.json'),registered_utc=protocol['registered_utc']))
    coverage=[];books={c['id']:{cost:Account(meta[c['symbol']],values,c['rr']) for cost,values in COSTS.items()} for c in configs}
    engines={(s,m):Signals(m,meta[s]['trade_tick_size']) for s in archive for m in [1,5]}
    def progress(phase,symbol,date):write(out/'progress.json',dict(updated_utc=stamp(),pid=os.getpid(),phase=phase,symbol=symbol,date=date,paper_only=True))
    try:
        # Financial development only. Earlier observations supply indicator warmup.
        for symbol,rows in archive.items():
            subset=[c for c in configs if c['symbol']==symbol]
            for row in rows:
                date=row['date']
                if date>='2026-06-01':break
                if row.get('status')!='captured':continue
                t,bid,ask=quotes(root,out,symbol,row,'inferred_ny')
                if not len(t):continue
                plans={m:engines[symbol,m].generate(candles(t,bid,m)) for m in [1,5]}
                coverage.append(dict(symbol=symbol,date=date,phase='development',quotes=len(t),minutes=len(candles(t,bid,1)),five_minute_bars=len(candles(t,bid,5))))
                if date>='2025-12-15':
                    for c in subset:
                        for book in books[c['id']].values():book.run_day(date,t,bid,ask,plans[c['minutes']][c['family']])
                progress('development',symbol,date)
        dev=[dict(c,metrics={k:metrics(v,'2025-12-15','2026-06-01') for k,v in books[c['id']].items()}) for c in configs]
        selected=[]
        for symbol in archive:
            for m in [1,5]:
                group=[d for d in dev if d['symbol']==symbol and d['minutes']==m];qualified=[d for d in group if qualify(d['metrics'],100)]
                diagnostic=[d for d in group if all(v['trades']>=30 and v['net_pnl']>0 and v['drawdown_pct']<10 for v in d['metrics'].values())]
                pool=qualified or diagnostic
                if pool:
                    best=max(pool,key=lambda d:min(v['net_pnl'] for v in d['metrics'].values()))
                    selected.append(dict(id=best['id'],symbol=symbol,minutes=m,family=best['family'],rr=best['rr'],selection_class='target-qualified' if qualified else 'diagnostic-only'))
        selection=dict(frozen_utc=stamp(),development_results_sha256=None,selected=selected,no_later_reselection=True)
        write(out/'development.json',dev);selection['development_results_sha256']=sha(out/'development.json');write(out/'selection.json',selection)
        # Checkpoint entire development, including all rejected candidates.
        for c in configs:
            for cost,book in books[c['id']].items():
                write(out/'ledgers/development'/f'{c["id"]}_{cost}.json',dict(fills=book.fills,decisions=book.decisions,metrics=dev[configs.index(c)]['metrics'][cost]))
        cuts={(s['id'],k):len(v.fills) for s in selected for k,v in books[s['id']].items()}
        for symbol,rows in archive.items():
            subset=[s for s in selected if s['symbol']==symbol]
            if not subset:continue
            for row in rows:
                date=row['date']
                if date<'2026-06-01' or row.get('status')!='captured':continue
                t,bid,ask=quotes(root,out,symbol,row,'inferred_ny')
                if not len(t):continue
                plans={m:engines[symbol,m].generate(candles(t,bid,m)) for m in [1,5]}
                coverage.append(dict(symbol=symbol,date=date,phase='later',quotes=len(t),minutes=len(candles(t,bid,1)),five_minute_bars=len(candles(t,bid,5))))
                for s in subset:
                    for book in books[s['id']].values():book.run_day(date,t,bid,ask,plans[s['minutes']][s['family']])
                progress('later',symbol,date)
        challenge=[]
        for s in selected:
            b=books[s['id']];row=dict(s,metrics={k:metrics(v,'2026-06-01','2026-10-31',cuts[s['id'],k]) for k,v in b.items()},full_metrics={k:metrics(v,'2025-12-15','2026-10-31') for k,v in b.items()})
            row['decision']='Pending clock sensitivity'
            challenge.append(row)
            for cost,book in b.items():write(out/'ledgers/full'/f'{s["id"]}_{cost}.json',dict(fills=book.fills,decisions=book.decisions,metrics=row['full_metrics'][cost]))
        clocks=[]
        for symbol,rows in archive.items():
            subset=[s for s in selected if s['symbol']==symbol]
            if not subset:continue
            e={m:Signals(m,meta[symbol]['trade_tick_size']) for m in [1,5]};b={s['id']:{k:Account(meta[symbol],v,s['rr']) for k,v in COSTS.items()} for s in subset}
            for row in rows:
                date=row['date']
                if row.get('status')!='captured':continue
                t,bid,ask=quotes(root,out,symbol,row,'fixed3')
                if not len(t):continue
                plans={m:e[m].generate(candles(t,bid,m)) for m in [1,5]}
                if date>='2025-12-15':
                    for s in subset:
                        for book in b[s['id']].values():book.run_day(date,t,bid,ask,plans[s['minutes']][s['family']])
                progress('clock_sensitivity',symbol,date)
            for s in subset:
                row=dict(s,metrics={k:metrics(v,'2025-12-15','2026-10-31') for k,v in b[s['id']].items()},decision='Historical clock sensitivity')
                clocks.append(row)
                for cost,book in b[s['id']].items():write(out/'ledgers/fixed3'/f'{s["id"]}_{cost}.json',dict(fills=book.fills,decisions=book.decisions,metrics=row['metrics'][cost]))
        for row in challenge:
            clock=next(c for c in clocks if c['id']==row['id'])
            good=row['selection_class']=='target-qualified' and qualify(row['metrics'],30) and qualify(row['full_metrics'],100) and qualify(clock['metrics'],100)
            row['decision']='HISTORICAL SCREEN PASS — INDEPENDENT VALIDATION PENDING' if good else 'FAIL: profitability / sample / win rate / drawdown / clock gate'
        assert all(sha(root/p)==v for p,v in preserved.items()),'Prior research identity changed'
        assert all(sha(src/p)==v for p,v in protocol['source_sha256'].items()),'Registered source changed'
        result=dict(completed_utc=stamp(),protocol_sha256=sha(out/'protocol.json'),development=dev,challenge=challenge,clock_stress=clocks,preserved_hashes_verified=True,paper_only=True,independently_validated=False)
        write(out/'coverage.json',coverage);write(out/'results.json',result);report(out,result);progress('complete','ALL','2026-10-30')
        print(json.dumps(dict(completed_utc=result['completed_utc'],development_cases=len(dev)*2,selected=selected,challenge=challenge,clock_stress=clocks),indent=2))
    except Exception:
        for c in configs:
            for cost,book in books[c['id']].items():write(out/'ledgers/interrupted'/f'{c["id"]}_{cost}.json',dict(fills=book.fills,decisions=book.decisions,metrics=book.result()))
        write(out/'failure.json',dict(at=stamp(),pid=os.getpid(),traceback=traceback.format_exc()));raise


if __name__=='__main__':main()
