"""Read-only diagnosis of a failed spread audit; never infer replacement specs."""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from atlas_exit_research.data import NY, sha, stamp, write
from .spread_preflight import LANES, START, END, frozen_audit, schedule


def off_grid(prices, tick):
    units = np.asarray(prices) / tick
    return np.abs(units - np.rint(units)) > 1e-5


def raw_correspondence(root, identity, example):
    """Check the original archive, not only a transformed cache."""
    day = datetime.fromtimestamp(example['t'], timezone.utc).astimezone(NY).date().isoformat()
    row = next(r for r in identity['sources'] if r['date'] == day)
    source = root / row['file']
    assert sha(source) == row['sha256']
    raw = np.load(source)['quotes']
    offset = 3 if datetime.fromisoformat(day).replace(hour=12, tzinfo=NY).dst() else 2
    source_msc = round((example['t'] + offset * 3600) * 1000)
    same = raw[raw['time_msc'] == source_msc]
    assert any(abs(float(q['bid']) - example['bid']) < 1e-8 and
               abs(float(q['ask']) - example['ask']) < 1e-8 for q in same)
    return dict(date=day, source_sha256=row['sha256'], raw_bid_ask_match=True,
                clock='Existing inferred offset used only to locate the original row; not historical clock verification.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    base = root / 'outputs/atlas_research_pipeline_v1'
    out = base / 'feasibility/quote_precision_v1'
    out.mkdir(parents=True, exist_ok=False)
    failed = base / 'feasibility/spread_wait_v1'
    guard = frozen_audit(root)
    identity_file = root / 'outputs/atlas_exit_management_v1/data_identity.json'
    identity = json.loads(identity_file.read_text())
    metadata_files = {'NAS100': root / 'outputs/nas100_quote_data_v1/metadata.json',
                      'SPX500': root / 'work/mt5_symbol_metadata.json'}
    metadata = {s: json.loads(p.read_text()) for s, p in metadata_files.items()}
    metadata['SPX500'] = metadata['SPX500']['SPX500']
    schedule_file = base / 'cycles/003/private_decisions_control_standard.json'
    schedules = schedule(schedule_file)
    protocol = dict(registered_utc=stamp(), purpose='Post-failure descriptive precision diagnosis, not a strategy or parameter search.',
        failure_sha256=sha(failed/'failure.json'), failed_protocol_sha256=sha(failed/'protocol.json'),
        population='Raw original scheduled-entry preceding60second quote windows in previously exposed development,15Dec2025-31May2026. Windows do not overlap within an instrument.',
        method='Count bid, ask and spread values inconsistent with saved metadata point/tick units using an absolute1e-5 tolerance in unit counts. Verify one example per instrument against original hashed quote archives. No candidate fills or financial outcomes are calculated.',
        existing_fill_diagnostic='Count off-grid recorded entry/stop/target/exit prices in preserved full-history NAS90/SPX60 hypothetical ledgers, separately at each cost. This diagnoses assumed precision, not legal execution or economic impact.',
        source_file='atlas_research_pipeline/quote_precision_audit.py', source_sha256=sha(Path(__file__)),
        dependency_sha256=sha(Path(__file__).with_name('spread_preflight.py')),
        metadata_sha256={s:sha(p) for s,p in metadata_files.items()},
        quote_identity_sha256=sha(identity_file), schedule_projection_source_sha256=sha(schedule_file),
        frozen_sources=guard,
        official_reference=dict(title='Price representation accuracy and change steps',
            url='https://www.mql5.com/en/book/automation/symbols/symbols_point_tick',
            scope='Point/digits describe representation; tick size is the minimum price change, and tick value has a distinct monetary meaning. Documentation does not identify this account historical specifications.'),
        no_repair='Do not round or rewrite quotes, replace tick size/digits/value, scale P&L, alter slippage assumptions, rerun benchmarks or reopen MT5. A historical contract timeline is unavailable.',
        no_inference='Off-grid relative to saved metadata is an observed mismatch, not proof a historical quote was invalid, an order could not execute, or an alternative tick size/value is correct.',
        financial_cases_started=0, financial_outcomes_scored=0, observation_restarted=False,
        active_paper_changed=False, ict_used=False)
    write(out/'protocol.json', protocol)
    (out/'source_snapshot.py').write_bytes(Path(__file__).read_bytes())
    try:
        results, examples = {}, {}
        for lane, symbol in LANES.items():
            m = metadata[symbol]
            tick, point = float(m['trade_tick_size']), float(m['point'])
            path = root / identity[symbol]['cache']
            assert sha(path) == identity[symbol]['sha256']
            q = np.load(path, mmap_mode='r')
            times, counts, days = q['t'], Counter(), Counter()
            previous = float('-inf')
            for row in (r for r in schedules if r['lane'] == lane):
                assert row['entry_at'] - 60 > previous
                previous = row['entry_at']
                lo = int(np.searchsorted(times, row['entry_at'] - 60))
                hi = int(np.searchsorted(times, row['entry_at']))
                window = q[lo:hi]
                assert np.all((window['bid'] > 0) & (window['ask'] >= window['bid']))
                spread = window['ask'] - window['bid']
                bid_bad, ask_bad, spread_bad = (off_grid(a, tick) for a in [window['bid'],window['ask'],spread])
                any_bad = bid_bad | ask_bad | spread_bad
                counts.update(windows=1, quote_rows=len(window), bid_off_tick=int(bid_bad.sum()),
                              ask_off_tick=int(ask_bad.sum()), spread_off_tick=int(spread_bad.sum()),
                              any_off_tick=int(any_bad.sum()),
                              any_off_point=int((off_grid(window['bid'],point)|off_grid(window['ask'],point)|off_grid(spread,point)).sum()))
                day = datetime.fromtimestamp(row['entry_at'], timezone.utc).astimezone(NY).date().isoformat()
                if np.any(any_bad):
                    days[day] += int(any_bad.sum())
                if symbol not in examples and len(window):
                    j = int(np.flatnonzero(any_bad)[0]) if np.any(any_bad) else 0
                    examples[symbol] = {k:float(window[k][j]) for k in ['t','bid','ask']}
                elif np.any(any_bad) and not off_grid([examples[symbol]['bid'],examples[symbol]['ask']],tick).any():
                    j = int(np.flatnonzero(any_bad)[0])
                    examples[symbol] = {k:float(window[k][j]) for k in ['t','bid','ask']}
            correspondence = raw_correspondence(root, identity[symbol], examples[symbol])
            fills = {}
            for cost in ['standard','higher','severe']:
                p = root / 'outputs/atlas_pair_holding_v1' / f'private_fills_{cost}.json'
                rows = [r for r in json.loads(p.read_text()) if r['symbol'] == symbol]
                fills[cost] = dict(trades=len(rows),
                    off_tick_counts={key:sum(bool(off_grid([r[key]],tick)[0]) for r in rows if r.get(key) is not None)
                                     for key in ['entry','stop','target','exit']},
                    unchanged_ledger_sha256=sha(p), diagnostic_only=True)
            results[symbol] = dict(metadata={k:m.get(k) for k in ['point','digits','trade_tick_size','trade_tick_value_loss','trade_contract_size']},
                development=[START,END], counts=dict(counts),
                affected_development_dates=len(days), first_affected_date=min(days) if days else None,
                last_affected_date=max(days) if days else None,
                original_archive_check=correspondence, preserved_full_history_fills=fills,
                historical_contract_timeline_verified=False,
                verdict='PRECISION_COMPATIBILITY_UNRESOLVED' if counts['any_off_tick'] else 'NO_MISMATCH_IN_THIS_BOUNDED_SAMPLE_NOT_HISTORICAL_SPEC_VERIFICATION')
            assert sha(path) == identity[symbol]['sha256']
        assert frozen_audit(root) == guard
        write(out/'private_examples.json', examples)
        result = dict(completed_utc=stamp(), status='COMPLETED_DIAGNOSTIC_MODEL_LIMITATION_REMAINS',
            instruments=results, financial_cases_started=0, financial_outcomes_scored=0,
            independent_validation=False, benchmarks_changed=False, active_paper_changed=False,
            observation_restarted=False,
            conclusion='SPX historical quote precision is not reconciled with saved current-style metadata. Preserve all quoted modeled results as estimates; no financial correction or replacement specification is inferred. The spread-wait probe remains failed, not silently repaired or rescored.',
            next_action='Resolve source provenance and broker historical precision/tick value/contract applicability through documentary evidence when available. Until then defer execution-sensitive strategy scoring; continue nonfinancial provenance work or distinct research design.')
        write(out/'results.json', result)
        write(out/'completed.json', dict(completed_utc=stamp(), diagnostic_completed=True,
            financial_PASS=False, financial_cases=0, mismatch_resolved=False,
            protocol_sha256=sha(out/'protocol.json')))
        print(json.dumps(result,allow_nan=False))
    except Exception as exc:
        write(out/'failure.json',dict(failed_utc=stamp(),error=repr(exc),financial_cases_started=0,preserved=True))
        raise


if __name__ == '__main__':
    main()
