"""User-requested SPX15/NAS15 ablation with the frozen $5,000 risk policy."""
import argparse
import hashlib
import heapq
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .atlas_capture_inputs import load
from .atlas_capture_quotes_v2 import feasible_envelopes
from .atlas_live_core import PaperBook
from .atlas_metrics import metrics
from .atlas_opportunity_study import COSTS
from .atlas_portfolio_controller import APPROVED
from .audited_run import NY
from .portfolio_inputs import load_quotes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root
    out = root / 'outputs/atlas_two_strategy_5000_v1'
    out.mkdir(exist_ok=False)
    old = root / 'outputs/atlas_opportunity_v1/approved5000'
    benchmark = json.loads((old / 'results.json').read_text())
    protected = []
    for folder in [root / 'outputs/three_strategy_shared_account_v1',
                   root / 'outputs/atlas_risk_audit_v1',
                   root / 'outputs/atlas_opportunity_v1']:
        protected.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix in ['.json', '.html', '.py', '.txt', '.md'])
    protected = sorted(set(protected))
    before = {str(p.relative_to(root)): digest(p) for p in protected}
    freeze_path = root / 'work/tradingbot/local-results/atlas-forward-v2/freeze.json'
    forward_freeze = json.loads(freeze_path.read_text())
    paths = [Path(__file__)]
    for name, h in forward_freeze['source_hashes'].items():
        p = root / 'work/tradingbot' / ('trading_pipeline' if name == 'engine_v4.py' else 'research_monitor') / name
        assert digest(p) == h, name
        paths.append(p)
    paths.append(Path(__file__).with_name('atlas_capture_quotes_v2.py'))
    source = {str(p.relative_to(root)): digest(p) for p in paths}
    assert APPROVED == dict(initial_equity=5000.0, per_trade_equity_pct=.005,
                            per_trade_dollar_ceiling=25.0, portfolio_equity_pct=.01,
                            daily_loss_pause_pct=.02, drawdown_pause_pct=.10,
                            daily_trade_count_limit=None, paper_only=True)
    protocol = dict(registered_utc=datetime.now(timezone.utc).isoformat(),
                    request='Remove NAS5 only from the approved5000 historical simulation; preserve every remaining rule and risk limit.',
                    included=['SPX15', 'NAS15'], excluded=['NAS5'], funded_dates=['2025-12-15', '2026-10-30'],
                    settings=APPROVED, costs={c: COSTS[c] for c in ['standard', 'higher']},
                    comparator=str((old / 'results.json').relative_to(root)),
                    method='Fresh causal portfolio replay, not subtraction of old NAS5 profit. Same chronological quotes and SPX-before-NAS tie ordering. Retain the full three-lane quote working set to keep comparison quote coverage identical.',
                    entry_rules='Retain 1.5R, native stops, existing entry/recovery confirmations and all transaction-cost assumptions for both remaining lanes. No parameter search or sizing/execution edits.',
                    exposure='Previously exposed historical prices. Exploratory composition comparison; not independent validation.',
                    limitations='Fees6/12 roundtrip per lot, historical clock/margin and actual executable liquidity unverified. Stops and entry pauses do not guarantee maximum realized loss/drawdown.',
                    source_sha256=source, preserved_benchmark_sha256=before,
                    forward_cohort='atlas-forward-v2 remains the existing three-strategy observer; this offline comparison does not deploy a change.')
    (out / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    (out / 'source').mkdir()
    for p in paths:
        (out / 'source' / p.name).write_bytes(p.read_bytes())
    worker = dict(pid=os.getpid(), status='loading_private_archives', completed=0, total=2)
    (out / 'worker.json').write_text(json.dumps(worker))
    all_lanes, meta, folders, _, _ = load(root)
    lanes = {n: all_lanes[n] for n in all_lanes if n in ('SPX15', 'NAS15')}
    assert set(lanes) == {'SPX15', 'NAS15'}
    sessions = load_quotes(folders)
    working = {}
    for symbol, data in sessions.items():
        union = {}
        for name, lane in all_lanes.items():
            if lane['symbol'] != symbol:
                continue
            for t, s in lane['signals'].items():
                at = datetime.fromtimestamp(t, timezone.utc).astimezone(NY)
                if lane['start'] <= at.hour * 60 + at.minute <= lane['end']:
                    union[t, name] = s
        working[symbol], _ = feasible_envelopes(data, union, meta[symbol], False, 540, 900, exit_delay=0.0)
    rows = []
    for cost in ['standard', 'higher']:
        cfg = COSTS[cost]
        book = PaperBook(lanes, meta, dict(atlas5000=True, defer_busy_gate=True,
                                         allow_multiple=True, direction_guard=True), cfg, 5000.0)
        seen = 0
        reconstructed_cash = peak = 5000.0
        reconstructed_dd = max_equity_error = 0.0

        def stream(symbol, data):
            for day, q, offset in data:
                for x in q:
                    yield float(x['time_msc']) / 1000 - offset * 3600, 0 if symbol == 'SPX500' else 1, symbol, float(x['bid']), float(x['ask'])

        for observations, (t, _, symbol, bid, ask) in enumerate(heapq.merge(*(stream(s, q) for s, q in working.items()), key=lambda x: (x[0], x[1])), 1):
            book.quote(symbol, t, bid, ask)
            for f in book.fills[seen:]:
                m = meta[f['symbol']]
                pnl = ((f['exit'] - f['entry']) * f['side'] * m['trade_tick_value_loss'] / m['trade_tick_size'] - cfg['fee']) * f['quantity']
                assert abs(pnl - f['pnl']) < 1e-7
                reconstructed_cash += pnl
            seen = len(book.fills)
            equity = reconstructed_cash
            for p in book.positions.values():
                b, a, _ = book.latest[p['symbol']]
                m = meta[p['symbol']]
                mult, slip = m['trade_tick_value_loss'] / m['trade_tick_size'], m['trade_tick_size'] * cfg['slip_ticks']
                equity += (((b if p['side'] == 1 else a) - p['side'] * slip - p['entry']) * p['side'] * mult - cfg['fee']) * p['quantity']
            error = abs(equity - book.equity())
            max_equity_error = max(error, max_equity_error)
            assert error < 1e-7
            peak = max(peak, equity)
            reconstructed_dd = max(reconstructed_dd, (peak - equity) / peak)
            if observations % 500000 == 0:
                worker.update(status='replaying', cost=cost, observations=observations, closed_trades=seen)
                (out / 'worker.json').write_text(json.dumps(worker))
                print(json.dumps(worker), flush=True)
        book.finish()
        assert not book.positions
        assert all(f['strategy'] != 'NAS5' for f in book.fills)
        assert abs(reconstructed_cash - book.cash) < 1e-7 and abs(reconstructed_dd - book.dd) < 1e-9
        r = book.result()
        r.update(cost=cost, included_strategies=list(lanes),
                 metrics=metrics(book.fills, initial=5000.0),
                 per_strategy={n: metrics([f for f in book.fills if f['strategy'] == n], initial=5000.0) for n in lanes},
                 verification=dict(ledger_net_matches=True, no_open_positions=True, maximum_equity_reconstruction_error=max_equity_error,
                                   quote_drawdown_reconstructed_pct=reconstructed_dd * 100, source_code_unchanged=True),
                 independently_validated=False)
        prior = next(x for x in benchmark if x['cost'] == cost)
        r['comparison'] = dict(original_three_strategy_net=prior['net_pnl'], original_three_strategy_drawdown_pct=prior['quote_drawdown_pct'],
                               net_improvement=r['net_pnl'] - prior['net_pnl'],
                               drawdown_improvement_percentage_points=prior['quote_drawdown_pct'] - r['quote_drawdown_pct'])
        key = f'{len(rows) + 1:02d}'
        r['ledger'] = key
        (out / f'private_fills_{key}.json').write_text(json.dumps(book.fills, indent=2))
        (out / f'private_decisions_{key}.json').write_text(json.dumps(book.decisions, indent=2))
        rows.append(r)
        (out / 'results.json').write_text(json.dumps(rows, indent=2))
        worker.update(completed=len(rows))
        print(json.dumps({k: r[k] for k in ['cost', 'trades', 'net_pnl', 'ending_balance', 'win_rate', 'quote_drawdown_pct', 'comparison']}), flush=True)
    for p in protected:
        assert digest(p) == before[str(p.relative_to(root))], p
    for p in paths:
        assert digest(p) == source[str(p.relative_to(root))], p
    (out / 'completed.json').write_text(json.dumps(dict(cases=2, originals_unchanged=True, risk_limits_unchanged=True,
                                                     forward_cohort_unchanged=True, independently_validated=False)))
    worker.update(status='completed', completed=2)
    (out / 'worker.json').write_text(json.dumps(worker))


if __name__ == '__main__':
    main()
