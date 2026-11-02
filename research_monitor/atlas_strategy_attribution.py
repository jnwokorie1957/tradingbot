"""Read-only attribution of preserved shared-account ledgers; no strategy edits."""
import argparse
import hashlib
import heapq
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .atlas_capture_inputs import load
from .atlas_capture_quotes_v2 import feasible_envelopes
from .atlas_live_core import PaperBook
from .atlas_metrics import metrics
from .atlas_opportunity_study import COSTS
from .audited_run import NY
from .portfolio_inputs import load_quotes


class Drawdown:
    def __init__(self, initial):
        self.initial = self.peak = float(initial)
        self.fraction = self.dollars = 0.0
        self.at = None

    def mark(self, equity, at):
        self.peak = max(self.peak, equity)
        loss = self.peak - equity
        fraction = loss / self.peak
        self.dollars = max(self.dollars, loss)
        if fraction > self.fraction:
            self.fraction, self.at = fraction, at

    def result(self):
        return dict(quote_drawdown_pct=100 * self.fraction,
                    maximum_drawdown_dollars=self.dollars,
                    maximum_fraction_at_utc=datetime.fromtimestamp(self.at, timezone.utc).isoformat() if self.at is not None else None)


def ledger_metrics(fills, initial):
    m = metrics(fills, initial=initial)
    cash = initial
    closed = Drawdown(initial)
    for f in fills:
        cash += f['pnl']
        closed.mark(cash, f['exit_at'])
    m = {k: v for k, v in m.items() if not k.startswith('daily_')}
    m['closed_trade_drawdown_pct'] = 100 * closed.fraction
    return m


def original_attribution(root, cost, meta):
    folder = root / 'outputs/atlas_risk_audit_v1'
    r = next(x for x in json.loads((folder / 'results.json').read_text())
             if x['kind'] == 'portfolio' and x['system'] == 'original' and x['scenario'] == cost)
    fills = json.loads((folder / f'private_fills_{r["ledger"]}.json').read_text())
    original = json.loads((root / f'outputs/three_strategy_shared_account_v1/private_fills_{r["ledger"]}.json').read_text())
    assert [{k: v for k, v in f.items() if k not in ('entry_event', 'exit_event')} for f in fills] == original
    with np.load(folder / f'private_quote_trace_{r["ledger"]}.npz') as z:
        trace = z['trace']
    last = {s: np.maximum.accumulate(np.where(trace['symbol'] == i, np.arange(len(trace)), -1))
            for i, s in enumerate(sorted(meta))}
    rows, combined = {}, np.full(len(trace), 500.0)
    for lane in ['SPX15', 'NAS15', 'NAS5']:
        selected = [f for f in fills if f['strategy'] == lane]
        flows, unreal = np.zeros(len(trace)), np.zeros(len(trace))
        for f in selected:
            start, end = f['entry_event'] - 1, f['exit_event'] - 1
            m = meta[f['symbol']]
            mult, slip, fee = m['trade_tick_value_loss'] / m['trade_tick_size'], m['trade_tick_size'] * COSTS[cost]['slip_ticks'], COSTS[cost]['fee']
            pnl = ((f['exit'] - f['entry']) * f['side'] * mult - fee) * f['quantity']
            assert abs(pnl - f['pnl']) < 1e-7
            flows[end] += pnl
            ix = last[f['symbol']][start:end]
            executable = trace['bid'][ix] if f['side'] == 1 else trace['ask'][ix]
            unreal[start:end] += ((executable - f['side'] * slip - f['entry']) * f['side'] * mult - fee) * f['quantity']
        equity = 500.0 + np.cumsum(flows) + unreal
        peak = np.maximum.accumulate(np.r_[500.0, equity])[1:]
        dd = (peak - equity) / peak
        i = int(np.argmax(dd))
        rows[lane] = dict(**ledger_metrics(selected, 500.0), quote_drawdown_pct=float(dd[i] * 100),
                          maximum_drawdown_dollars=float(np.max(peak - equity)),
                          maximum_fraction_at_utc=datetime.fromtimestamp(float(trace['t'][i]), timezone.utc).isoformat())
        combined += equity - 500.0
    error = float(np.max(np.abs(combined - trace['equity'])))
    assert error < 1e-7
    assert abs(sum(x['net_pnl'] for x in rows.values()) - r['net_pnl']) < 1e-7
    return dict(account='original500', cost=cost, initial=500.0, strategies=rows,
                portfolio_net=r['net_pnl'], portfolio_drawdown_pct=r['quote_marked_drawdown_pct'],
                exact_original_ledger_match=True, maximum_attribution_equity_error=error)


def approved_attribution(root, lanes, meta, sessions, cost):
    cfg = COSTS[cost]
    book = PaperBook(lanes, meta, dict(atlas5000=True, defer_busy_gate=True, allow_multiple=True, direction_guard=True), cfg, 5000.0)
    prior = next(r for r in json.loads((root / 'outputs/atlas_opportunity_v1/approved5000/results.json').read_text()) if r['cost'] == cost)
    old = json.loads((root / f'outputs/atlas_opportunity_v1/approved5000/fills_{prior["ledger"]}.json').read_text())
    realized = {n: 0.0 for n in lanes}
    marks = {n: Drawdown(5000.0) for n in lanes}
    equity = {n: 5000.0 for n in lanes}
    seen = 0

    def stream(symbol, data):
        for day, q, offset in data:
            for x in q:
                yield float(x['time_msc']) / 1000 - offset * 3600, 0 if symbol == 'SPX500' else 1, symbol, float(x['bid']), float(x['ask'])

    for count, (t, _, symbol, bid, ask) in enumerate(heapq.merge(*(stream(s, q) for s, q in sessions.items()), key=lambda x: (x[0], x[1])), 1):
        book.quote(symbol, t, bid, ask)
        for f in book.fills[seen:]:
            realized[f['strategy']] += f['pnl']
        seen = len(book.fills)
        b, a, _ = book.latest[symbol]
        _, mult, slip, fee = book.economics(symbol)
        for name, lane in lanes.items():
            if lane['symbol'] != symbol:
                continue
            eq = 5000.0 + realized[name]
            for p in book.positions.values():
                if p['lane'] == name:
                    eq += (((b if p['side'] == 1 else a) - p['side'] * slip - p['entry']) * p['side'] * mult - fee) * p['quantity']
            equity[name] = eq
            marks[name].mark(eq, t)
        if count % 250000 == 0:
            assert abs(sum(equity.values()) - 10000.0 - book.equity()) < 1e-7
            print(json.dumps(dict(cost=cost, observations=count, matched_fills_so_far=seen)), flush=True)
    book.finish()
    assert not book.positions and book.fills == old
    assert abs(book.dd * 100 - prior['quote_drawdown_pct']) < 1e-7
    rows = {n: dict(**ledger_metrics([f for f in book.fills if f['strategy'] == n], 5000.0), **marks[n].result()) for n in lanes}
    assert abs(sum(x['net_pnl'] for x in rows.values()) - prior['net_pnl']) < 1e-7
    return dict(account='approved5000', cost=cost, initial=5000.0, strategies=rows,
                portfolio_net=prior['net_pnl'], portfolio_drawdown_pct=prior['quote_drawdown_pct'],
                exact_preserved_ledger_match=True, exact_portfolio_drawdown_match=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    args = p.parse_args()
    root = args.root
    out = root / 'outputs/atlas_strategy_attribution_v1'
    out.mkdir(exist_ok=False)
    inputs = [root / 'outputs/three_strategy_shared_account_v1/results.json', root / 'outputs/atlas_opportunity_v1/approved5000/results.json']
    inputs += sorted((root / 'outputs/three_strategy_shared_account_v1').glob('private_fills_0[12].json'))
    inputs += sorted((root / 'outputs/atlas_opportunity_v1/approved5000').glob('fills_*.json'))
    hashes = {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs}
    protocol = dict(registered_utc=datetime.now(timezone.utc).isoformat(), method='Read-only ledger and quote attribution; no strategy/risk/execution modification or optimization.',
                    original='Original both-direction NAS5 three-strategy shared500 account with25 combined ceiling; NOT the later340.38 recovery-filter result.',
                    dates=['2025-12-15', '2026-10-30'], costs=COSTS, source_inputs=hashes,
                    drawdown_definition='For each lane: initial whole-account capital plus only that lane actual shared-account realized/unrealized P&L, marked at each retained quote with modeled liquidation costs. Attribution curves sum back to the shared account after removing duplicate initial capital. These are NOT independent standalone replays, not additive drawdowns, and capital differs500vs5000.',
                    exposure='Reused historical prices; modeled fees and unverified historical clock/margin. No independent validation.',
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    lanes, meta, folders, _, _ = load(root)
    rows = [original_attribution(root, c, meta) for c in ['standard', 'higher']]
    (out / 'results.json').write_text(json.dumps(rows, indent=2))
    sessions = load_quotes(folders)
    working = {}
    for symbol in sessions:
        union = {}
        for name, lane in lanes.items():
            if lane['symbol'] != symbol:
                continue
            for t, s in lane['signals'].items():
                a = datetime.fromtimestamp(t, timezone.utc).astimezone(NY)
                if lane['start'] <= a.hour * 60 + a.minute <= lane['end']:
                    union[t, name] = s
        working[symbol], _ = feasible_envelopes(sessions[symbol], union, meta[symbol], False, 540, 900, exit_delay=0.0)
    for cost in ['standard', 'higher']:
        rows.append(approved_attribution(root, lanes, meta, working, cost))
        (out / 'results.json').write_text(json.dumps(rows, indent=2))
        print(json.dumps(dict(completed_account='approved5000', cost=cost)), flush=True)
    for f in inputs:
        assert hashlib.sha256(f.read_bytes()).hexdigest() == hashes[str(f.relative_to(root))]
    (out / 'completed.json').write_text(json.dumps(dict(cases=len(rows), originals_unchanged=True, optimization=False, independent_validation=False)))


if __name__ == '__main__':
    main()
