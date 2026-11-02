"""Bounded development-only selection of causal NAS15 entry hypotheses."""
import argparse
import copy
import hashlib
import heapq
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from .atlas_capture_inputs import load
from .atlas_capture_quotes_v2 import feasible_envelopes
from .atlas_live_core import PaperBook
from .atlas_metrics import metrics, local_day
from .atlas_opportunity_study import COSTS
from .atlas_portfolio_controller import APPROVED
from .audited_run import NY
from .entry_quality_v2 import enrich
from .hourly_entry_quality import attach_hourly
from .native_data import aggregate
from .portfolio_inputs import load_quotes

FIRST, SPLIT, END = '2025-12-15', '2026-06-01', '2026-10-31'
PROFILES = ('control', 'strong_close', 'efficient_all', 'strong_and_efficient',
            'gap_cap_2ATR', 'retest15', 'retest15_strong')


def gap_pass(t, s):
    f = s.get('features', {})
    at = datetime.fromtimestamp(t, timezone.utc).astimezone(NY)
    # Require the opening minute to be complete before using its recorded open.
    return (at.hour * 60 + at.minute >= 571 and
            {'session_open', 'prior_close'} <= f.keys() and
            s.get('atr14', 0) > 0 and
            abs(f['session_open'] - f['prior_close']) <= 2 * s['atr14'])


def wilson(wins, count):
    if not count:
        return None
    z, p = 1.959963984540054, wins / count
    center = (p + z*z/(2*count)) / (1 + z*z/count)
    half = z * math.sqrt(p*(1-p)/count + z*z/(4*count*count)) / (1 + z*z/count)
    return [100*(center-half), 100*(center+half)]


def compact(m):
    return {k: v for k, v in m.items() if not k.startswith('daily_')}


def summary(book, name, cost, first, end, fills=None):
    fs = book.fills if fills is None else fills
    nas = metrics([f for f in fs if f['strategy'] == 'NAS15'], initial=5000., first=first, end=end)
    port = metrics(fs, initial=5000., first=first, end=end)
    nas['win_rate_wilson95_pct'] = wilson(nas['wins'], nas['trades'])
    return dict(profile=name, cost=cost, nas15=compact(nas), portfolio=compact(port),
                portfolio_quote_drawdown_pct=book.dd*100,
                drawdown_scope='continuous account from Dec15; phase P&L shown separately where applicable')


def choose(rows):
    lookup = {(r['profile'], r['cost']): r for r in rows}
    eligible, reasons = [], {}
    for name in PROFILES[1:]:
        failures = []
        for cost in ['standard', 'higher']:
            r, b = lookup[name, cost], lookup['control', cost]
            n, bn = r['nas15'], b['nas15']
            if n['trades'] < max(15, math.ceil(.75*bn['trades'])):
                failures.append(cost + ': insufficient capture/sample')
            if n['net_pnl'] <= 0 or n['net_pnl'] < .95*bn['net_pnl']:
                failures.append(cost + ': NAS profit retention below95%')
            if r['portfolio']['net_pnl'] < .95*b['portfolio']['net_pnl']:
                failures.append(cost + ': portfolio profit retention below95%')
            if r['portfolio_quote_drawdown_pct'] > b['portfolio_quote_drawdown_pct'] + 1e-8:
                failures.append(cost + ': portfolio drawdown worsens')
        reasons[name] = failures
        if not failures:
            eligible.append(name)
    diagnostic = [n for n in PROFILES[1:] if all(lookup[n, c]['nas15']['trades'] >= 15 and lookup[n, c]['nas15']['net_pnl'] > 0 for c in ['standard', 'higher'])]
    pool = eligible or diagnostic
    def rank(name):
        return (min(lookup[name, c]['nas15']['win_rate'] or 0 for c in ['standard', 'higher']),
                lookup[name, 'higher']['nas15']['net_pnl'],
                min(lookup[name, c]['nas15']['trades'] for c in ['standard', 'higher']))
    selected = max(pool, key=rank) if pool else None
    return dict(selected=selected, development_qualified=selected in eligible if selected else False,
                diagnostic_only=not bool(eligible), eligible=eligible, vetoes=reasons,
                rule='Dev-only rank by minimum two-cost NAS15 win rate, then higher-cost NAS net, then sample. Qualification requires75% capture, at least15 NAS trades per cost,95% NAS/portfolio profit retention, positive NAS profit, no portfolioDD increase. If none qualify, a positive>=15-trade diagnostic may be checked without promotion. No later-period reselection.')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    root = p.parse_args().root
    out = root / 'outputs/atlas_nas15_winrate_v1'
    out.mkdir(exist_ok=False)
    baseline = root / 'outputs/atlas_two_strategy_5000_v1'
    frozen = root / 'work/tradingbot/local-results/atlas-forward-v2/freeze.json'
    freeze = json.loads(frozen.read_text())
    protected = [frozen, baseline/'results.json', baseline/'protocol.json', baseline/'report.html']
    protected += list(baseline.glob('private_fills_*.json'))
    protected += [root/'outputs/atlas_opportunity_v1/approved5000/results.json', root/'outputs/three_strategy_shared_account_v1/results.json']
    hashes = {str(x.relative_to(root)): hashlib.sha256(x.read_bytes()).hexdigest() for x in protected}
    source = {Path(__file__).name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for name, h in freeze['source_hashes'].items():
        path = root/'work/tradingbot'/('trading_pipeline' if name == 'engine_v4.py' else 'research_monitor')/name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == h
        source[name] = h
    protocol = dict(registered_utc=datetime.now(timezone.utc).isoformat(), development=[FIRST, '2026-05-31'],
                    later=[SPLIT, '2026-10-30'], profiles=PROFILES, risk=APPROVED,
                    costs={c: COSTS[c] for c in ['standard', 'higher']},
                    hypotheses='Only NAS15 entry confirmations vary. Existing strongclose65, prior20 efficiency>=.30, gap<=2ATR, and completed1m retest of prior20-bar breakout within15min. No threshold grid. SPX15/risk/exits/1.5R remain unchanged.',
                    retest='Original impulse natural stop retained; stop touch or15minuteexpiry cancels. Confirmation uses completed1m closes strictly after impulse; next quote is eligible60seconds later. Fresh completed-hour context attached at confirmation decision.',
                    selection_rule='At least15 NAS trades and75% baseline capture at each cost, positive NAS net and>=95% NAS/portfolio baseline profit, no greater portfolioDD. Rank minimum two-cost NAS win rate, then higher-cost net, then sample. Diagnostic fallback is clearly nonqualifying; later never reselects.',
                    exposure='All dates were previously reviewed. Development and later checks are reused-history research, not untouched OOS or independent walk-forward validation. No deployment or optimization on the active forward cohort.',
                    protected_hashes=hashes, source_sha256=source,
                    limitations='Fees, historical clock/margin and execution remain estimates. Stops and entry pauses are not guaranteed realized-loss caps.')
    (out/'protocol.json').write_text(json.dumps(protocol, indent=2))
    state = dict(pid=os.getpid(), phase='loading', completed=0, development_cases=14)
    (out/'worker.json').write_text(json.dumps(state))
    all_lanes, meta, folders, one, _ = load(root)
    base = {n: all_lanes[n] for n in all_lanes if n in ['SPX15', 'NAS15']}
    impulse = {t:s for t,s in base['NAS15']['signals'].items() if s['side']==1 and 540 <= ((lambda a:a.hour*60+a.minute)(datetime.fromtimestamp(t,timezone.utc).astimezone(NY))) <= 900}
    native = aggregate(one['NAS100'], 15)
    retests = attach_hourly(enrich(native, one['NAS100'], impulse, 'retest15'), one['NAS100'])
    variants = {}
    for name in PROFILES:
        lanes = copy.deepcopy(base)
        if name == 'strong_close': lanes['NAS15']['confirmation'] = 'strong_close'
        if name == 'efficient_all': lanes['NAS15']['confirmation'] = 'efficient'
        if name == 'strong_and_efficient': lanes['NAS15']['confirmation'] = 'both'
        if name == 'gap_cap_2ATR': lanes['NAS15']['signals'] = {t:s for t,s in lanes['NAS15']['signals'].items() if gap_pass(t,s)}
        if name.startswith('retest15'):
            lanes['NAS15']['signals'] = retests
            if name.endswith('_strong'): lanes['NAS15']['confirmation'] = 'strong_close'
        variants[name] = lanes
    # Record all filtered-out decisions and changes in clocks/stops for audit.
    audit = {}
    for name, lanes in variants.items():
        plans = lanes['NAS15']['signals']
        audit[name] = dict(raw_plans=len(plans), removed_original_plan_times=sorted(set(base['NAS15']['signals'])-set(plans)))
    (out/'input_audit.json').write_text(json.dumps(audit, indent=2))
    sessions = load_quotes(folders)
    working = {}
    for symbol, data in sessions.items():
        union = {}
        for name, lanes in variants.items():
            for lane_name, lane in lanes.items():
                if lane['symbol'] != symbol: continue
                for t,s in lane['signals'].items():
                    at = datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
                    if lane['start'] <= at.hour*60+at.minute <= lane['end']: union[t,name,lane_name] = s
        working[symbol], _ = feasible_envelopes(data, union, meta[symbol], False, 540, 900)
    policy = dict(atlas5000=True, defer_busy_gate=True, allow_multiple=True, direction_guard=True)
    books = {(n,c): PaperBook(lanes,meta,dict(policy),COSTS[c],5000.) for n,lanes in variants.items() for c in ['standard','higher']}
    def events(first,end):
        def stream(symbol):
            for day,q,offset in working[symbol]:
                if not first<=day<end: continue
                for x in q: yield float(x['time_msc'])/1000-offset*3600,0 if symbol=='SPX500' else 1,symbol,float(x['bid']),float(x['ask'])
        return heapq.merge(*(stream(s) for s in working),key=lambda x:(x[0],x[1]))
    for i,(t,_,symbol,bid,ask) in enumerate(events(FIRST,SPLIT),1):
        for b in books.values(): b.quote(symbol,t,bid,ask)
        if i%200000==0:
            state.update(phase='development_only',observations=i)
            (out/'worker.json').write_text(json.dumps(state));print(json.dumps(state),flush=True)
    development=[]
    for (name,cost),b in books.items():
        assert not b.positions
        development.append(summary(b,name,cost,FIRST,SPLIT))
        (out/f'dev_fills_{name}_{cost}.json').write_text(json.dumps(b.fills,indent=2))
        (out/f'dev_decisions_{name}_{cost}.json').write_text(json.dumps(b.decisions,indent=2))
    (out/'development.json').write_text(json.dumps(development,indent=2))
    selection=choose(development)
    selection['frozen_utc']=datetime.now(timezone.utc).isoformat()
    (out/'selection.json').write_text(json.dumps(selection,indent=2))
    names=['control']+([selection['selected']] if selection['selected'] else [])
    continuing={(n,c):books[n,c] for n in names for c in ['standard','higher']}
    counts={k:len(b.fills) for k,b in continuing.items()}
    state.update(phase='frozen_candidate_later_check',selected=selection['selected'],completed=14)
    (out/'worker.json').write_text(json.dumps(state));print(json.dumps(selection),flush=True)
    for i,(t,_,symbol,bid,ask) in enumerate(events(SPLIT,END),1):
        for b in continuing.values(): b.quote(symbol,t,bid,ask)
        if i%500000==0:
            state.update(observations=i);(out/'worker.json').write_text(json.dumps(state));print(json.dumps(state),flush=True)
    later,full=[],[]
    for (name,cost),b in continuing.items():
        b.finish();assert not b.positions
        later.append(summary(b,name,cost,SPLIT,END,b.fills[counts[name,cost]:]))
        full.append(summary(b,name,cost,FIRST,END))
        (out/f'full_fills_{name}_{cost}.json').write_text(json.dumps(b.fills,indent=2))
        (out/f'full_decisions_{name}_{cost}.json').write_text(json.dumps(b.decisions,indent=2))
        if name=='control':
            r=next(x for x in json.loads((baseline/'results.json').read_text()) if x['cost']==cost)
            old=json.loads((baseline/f'private_fills_{r["ledger"]}.json').read_text())
            assert b.fills==old and abs(b.dd*100-r['quote_drawdown_pct'])<1e-7
    (out/'later.json').write_text(json.dumps(later,indent=2));(out/'results.json').write_text(json.dumps(full,indent=2))
    for x in protected: assert hashlib.sha256(x.read_bytes()).hexdigest()==hashes[str(x.relative_to(root))]
    (out/'completed.json').write_text(json.dumps(dict(development_cases=14,later_cases=len(continuing),baseline_exactly_reproduced=True,benchmarks_preserved=True,independently_validated=False,forward_deployed=False)))
    state.update(phase='completed',completed=14+len(continuing));(out/'worker.json').write_text(json.dumps(state));print(json.dumps(full),flush=True)


if __name__=='__main__':
    main()
