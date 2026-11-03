"""One bounded, data-only execution-feasibility audit. No fills or broker imports.

Original schedules are projected to lane/decision/entry_at before use. Their
recorded outcomes, directions, prices, sizes and rejection reasons are ignored.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import numpy as np

from atlas_exit_research.data import NY, sha, stamp, write


START, END = '2025-12-15', '2026-05-31'
BASELINE_SECONDS = 60
WAIT_SECONDS = 60
REACTION_SECONDS = 1
MAX_GAP_SECONDS = 5
MIN_DISTINCT_TIMESTAMPS = 30
FEASIBILITY_MIN_DELAYED = 20
LANES = {'NAS15': 'NAS100', 'SPX15': 'SPX500'}
REFERENCES = [
    dict(title='Understanding Order Types', publisher='SEC Investor.gov',
         url='https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-14',
         scope='Stock order mechanics: market prices are uncertain; a limit price can prevent execution. This is not CFD strategy evidence.'),
    dict(title='Algorithmic Trading', publisher='Interactive Brokers',
         url='https://www.ibkrguides.com/ibkrdesktop/algorithmic-trading.htm',
         scope='Adaptive and Arrival Price descriptions motivate an execution-cost/price-risk tradeoff. Our proposed spread-conditioned wait is neither an IBKR algo reproduction nor a demonstrated CFD improvement.'),
]


def ticks(q, tick):
    spread = (np.asarray(q['ask']) - np.asarray(q['bid'])) / tick
    if not np.all(np.isfinite(spread)) or np.any(spread < -1e-7):
        raise ValueError('Nonfinite, negative or crossed spread')
    rounded = np.rint(spread)
    if np.any(np.abs(spread - rounded) > 1e-5):
        raise ValueError('Raw spread is inconsistent with the frozen price tick')
    return rounded.astype('i8')


def assess(q, scheduled, tick):
    """Information available up to each causal trigger only; no financial path."""
    t = q['t']
    i = int(np.searchsorted(t, scheduled))
    if i == len(t) or float(t[i]) - scheduled > MAX_GAP_SECONDS:
        return dict(status='arrival_quote_unavailable')
    # Exclude the arrival quote, its timestamp peers, and all later quotes.
    lo = int(np.searchsorted(t, scheduled - BASELINE_SECONDS))
    hi = int(np.searchsorted(t, scheduled))
    history = q[lo:hi]
    distinct = np.unique(history['t'])
    gaps = np.diff(np.r_[scheduled - BASELINE_SECONDS, distinct, scheduled])
    if len(distinct) < MIN_DISTINCT_TIMESTAMPS or float(gaps.max()) > MAX_GAP_SECONDS:
        return dict(status='baseline_coverage_unavailable', distinct_timestamps=len(distinct),
                    maximum_baseline_gap_seconds=float(gaps.max()))
    reference = float(median(ticks(history, tick).tolist()))
    arrival_spread = int(ticks(q[i:i + 1], tick)[0])
    base = dict(arrival_at=float(t[i]), reference_median_spread_ticks=reference,
                arrival_spread_ticks=arrival_spread, baseline_last_at=float(distinct[-1]))
    if arrival_spread <= reference:
        return dict(base, status='unchanged_arrival', prospective_entry_at=float(t[i]),
                    extra_delay_seconds=0.)
    # Wait is fixed ex ante. A gap cancels this possible intervention; it is
    # never repaired by interpolating prices or by assuming a resting limit fill.
    previous = float(t[i])
    deadline = previous + WAIT_SECONDS
    for j in range(i + 1, len(t)):
        when = float(t[j])
        if when - previous > MAX_GAP_SECONDS:
            return dict(base, status='waiting_path_unavailable')
        if when > deadline:
            return dict(base, status='wait_expired_without_trigger')
        previous = when
        if int(ticks(q[j:j + 1], tick)[0]) > reference:
            continue
        # The trigger quote is not a fill. Even a future financial experiment
        # would recheck every original guard at the next quote after reaction.
        k = int(np.searchsorted(t, when + REACTION_SECONDS))
        if k == len(t) or float(t[k]) - (when + REACTION_SECONDS) > MAX_GAP_SECONDS:
            return dict(base, status='reaction_quote_unavailable', trigger_at=when)
        if float(t[k]) > deadline:
            return dict(base, status='reaction_after_wait_deadline', trigger_at=when)
        return dict(base, status='delayed_quote_candidate', trigger_at=when,
                    prospective_entry_at=float(t[k]), extra_delay_seconds=float(t[k]) - float(t[i]),
                    trigger_spread_ticks=int(ticks(q[j:j + 1], tick)[0]),
                    reaction_spread_ticks=int(ticks(q[k:k + 1], tick)[0]))
    return dict(base, status='waiting_path_unavailable')


def schedule(path):
    rows = json.loads(path.read_text(encoding='utf-8'))
    # This allowlist deliberately removes every financial result/eligibility.
    result = [{k: r[k] for k in ['lane', 'decision', 'entry_at']} for r in rows]
    assert all(r['lane'] in LANES and r['entry_at'] == r['decision'] + 60 for r in result)
    assert len({(r['lane'], r['decision'], r['entry_at']) for r in result}) == len(result)
    return result


def frozen_audit(root):
    repo = root / 'work/tradingbot'
    original = json.loads((repo / 'local-results/atlas-forward-v2/freeze.json').read_text())
    checks = {name: sha(repo / ('trading_pipeline' if name == 'engine_v4.py' else 'research_monitor') / name) == value
              for name, value in original['source_hashes'].items()}
    assert len(checks) == 18 and all(checks.values())
    cohorts = {}
    for folder in ['atlas_pair_prospective_v1', 'atlas_nas15_prospective_v1']:
        protocol = root / 'outputs' / folder / 'protocol.json'
        data = json.loads(protocol.read_text())
        identity = json.loads(protocol.with_name('protocol_identity.json').read_text())['sha256']
        assert sha(protocol) == identity
        source_checks = {p: sha(root / p) == value for p, value in data['source_sha256'].items()}
        assert all(source_checks.values())
        cohorts[folder] = dict(protocol_sha256=identity, sources_verified=len(source_checks), all_match=True)
    return dict(original_financial_sources_verified=len(checks), all_match=True, cohorts=cohorts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    out = root / 'outputs/atlas_research_pipeline_v1/feasibility/spread_wait_v1'
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__)
    guard = frozen_audit(root)
    prior = root / 'outputs/atlas_research_pipeline_v1/cycles/003'
    paths = {cost: prior / f'private_decisions_control_{cost}.json'
             for cost in ['standard', 'higher', 'severe']}
    raw_schedule = schedule(paths['standard'])
    assert all(schedule(p) == raw_schedule for p in paths.values()), 'A cost-dependent schedule is not a raw entry universe'
    calendar = lambda at: datetime.fromtimestamp(at, timezone.utc).astimezone(NY).date().isoformat()
    assert all(START <= calendar(r['entry_at']) <= END for r in raw_schedule)
    schedule_id = hashlib.sha256(json.dumps(raw_schedule, sort_keys=True).encode()).hexdigest()
    identity_file = root / 'outputs/atlas_exit_management_v1/data_identity.json'
    identity = json.loads(identity_file.read_text())
    registry = root / 'outputs/atlas_research_pipeline_v1/experiment_registry.json'
    inputs = {s: dict(cache=identity[s]['cache'].replace('\\', '/'), sha256=identity[s]['sha256']) for s in LANES.values()}
    metadata_files = [root / 'outputs/nas100_quote_data_v1/metadata.json', root / 'work/mt5_symbol_metadata.json']
    metadata = {'NAS100': json.loads(metadata_files[0].read_text()),
                'SPX500': json.loads(metadata_files[1].read_text())['SPX500']}
    protocol = dict(registered_utc=stamp(), status='DATA_ONLY_FEASIBILITY_NO_FINANCIAL_SCORING',
        hypothesis='Wide arrival spreads may justify a bounded market-entry wait for a narrower observed spread, but delay can worsen prices or miss valid entries. First establish whether this rule has enough actual quote interventions to merit a separately frozen financial comparison.',
        references=REFERENCES, development=[START, END], all_history_previously_exposed=True,
        proposed_rules=dict(baseline='Tick-count median of raw bid/ask spreads in [scheduled entry minus60s,scheduled entry); exclude current and all later quotes.',
            baseline_seconds=BASELINE_SECONDS, minimum_distinct_timestamps=MIN_DISTINCT_TIMESTAMPS,
            maximum_quote_gap_seconds=MAX_GAP_SECONDS, initial_scheduled_delay_seconds=60,
            trigger='If arrival spread exceeds the fixed baseline median, wait for the FIRST subsequent spread at or below it. Otherwise preserve arrival.',
            maximum_additional_wait_seconds=WAIT_SECONDS, reaction_seconds=REACTION_SECONDS,
            execution='No resting limit, midpoint fill, assumed queue priority or price improvement. This audit only records quote times; a separate experiment must apply adverse market fills and every original guard at actual candidate time.',
            cancellation='Sparse baseline is unavailable, not imputed. A waiting-path gap or deadline failure is retained. No new session eligibility, financial outcome or opportunity validity is inferred.'),
        feasibility_gate=f'At least{FEASIBILITY_MIN_DELAYED} delayed_quote_candidate raw schedule events for EACH original lane, with complete frozen quote coverage and causal prefix parity. This does not establish20 executable trades.',
        no_tuning='If the gate fails, archive without alternate median windows, wait horizons, thresholds or sparse-data fallbacks. No later-history financial replay.',
        possible_future_financial_scope='If feasible, a SEPARATE six-case protocol would compare unchanged control and one fixed intervention at standard/higher/severe costs. Preserve SPX15/1.5R/60minutes,NAS15/2R/90minutes capped16NY, original signal rules and natural stops, and all approved5000USD limits. No case is started here.',
        duplicate_review=dict(registry_sha256=sha(registry), records=len(json.loads(registry.read_text())['experiments']),
            related=['atlas_pair_execution_delay_v1','spx15_execution_audit_v1','spx15_entry_quality_v2','atlas_opportunity_v1','risk_review.py:streak_cost08'],
            conclusion='Fixed5/10/60s timing, price retest confirmation, cost-to-stop rejection and busy/exposure admission are related but do not postpone a market entry conditional on a frozen backward spread median. This is one distinct execution feasibility hypothesis, not a retuned fixed-delay or price-pullback strategy.'),
        sources={source.name:sha(source), 'checks_spread.py':sha(source.with_name('checks_spread.py'))},
        schedule_sha256=schedule_id, source_decision_files={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in paths.values()},
        quote_inputs=inputs, metadata_files={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in metadata_files},
        frozen_sources=guard, observation='Stopped by explicit user decision; no new terminal connection or collector.',
        limitations=['Previously exposed development prices are not untouched evidence.',
            'Historical clock/DST, contract applicability, commissions, margins, liquidity and historical computation/receipt latency are unverified.',
            'Market quote candidates are not fills, successful trades, proven missed winners or broker execution evidence.',
            'This audit measures data intervention availability only and does not estimate profit or drawdown.'],
        financial_outcomes_scored=0, financial_cases_started=0, paper_only=True,
        active_paper_changed=False, observation_restarted=False, ict_used=False)
    write(out / 'protocol.json', protocol)
    (out / 'source_snapshot.py').write_bytes(source.read_bytes())
    (out / 'checks_snapshot.py').write_bytes(source.with_name('checks_spread.py').read_bytes())
    try:
        results, private = {}, []
        for lane, symbol in LANES.items():
            path = root / inputs[symbol]['cache']
            assert sha(path) == inputs[symbol]['sha256']
            q = np.load(path, mmap_mode='r')
            assert np.all(np.diff(q['t']) >= 0)
            tick = float(metadata[symbol]['trade_tick_size'])
            assert math.isfinite(tick) and tick > 0
            selected = [r for r in raw_schedule if r['lane'] == lane]
            rows = []
            for row in selected:
                result = assess(q, row['entry_at'], tick)
                if result['status'] in ['unchanged_arrival', 'delayed_quote_candidate']:
                    # Truncation at the selected observation leaves exactly the
                    # same result; nothing after that observation is required.
                    edge = int(np.searchsorted(q['t'], result['prospective_entry_at'], side='right'))
                    assert assess(q[:edge], row['entry_at'], tick) == result
                rows.append(dict(row, **result))
            counts = Counter(r['status'] for r in rows)
            changed = [r for r in rows if r['status'] == 'delayed_quote_candidate']
            results[lane] = dict(symbol=symbol, raw_scheduled_events=len(rows), status_counts=dict(counts),
                candidate_quote_delays=len(changed), median_extra_delay_seconds=median(r['extra_delay_seconds'] for r in changed) if changed else None,
                mean_raw_spread_change_ticks=sum(r['reaction_spread_ticks'] - r['arrival_spread_ticks'] for r in changed)/len(changed) if changed else None,
                causal_prefix_checks=sum(r['status'] in ['unchanged_arrival','delayed_quote_candidate'] for r in rows),
                feasibility_gate=len(changed) >= FEASIBILITY_MIN_DELAYED,
                economic_interpretation='Quote timing availability only; no net saving, executable trade or P&L is established.')
            private.extend(rows)
            assert sha(path) == inputs[symbol]['sha256']
        assert frozen_audit(root) == guard
        passed = all(r['feasibility_gate'] for r in results.values())
        write(out / 'private_quote_events.json', private)
        result = dict(completed_utc=stamp(),
            status='FEASIBLE_FOR_SEPARATE_FINANCIAL_PROTOCOL' if passed else 'DEFERRED_INSUFFICIENT_QUOTE_INTERVENTIONS',
            instruments=results, development=[START, END], all_history_previously_exposed=True,
            financial_outcomes_scored=0, financial_cases_started=0, independent_validation=False,
            active_paper_changed=False, observation_restarted=False,
            next_action='Require a separate frozen financial protocol, causal/adverse-fill/risk checks and original-control parity before any financial scoring.' if passed else 'Archive this fixed execution idea without threshold/window tuning or financial replay. Continue distinct research or obtain genuinely additional quality-audited observations.')
        write(out / 'results.json', result)
        write(out / 'completed.json', dict(completed_utc=stamp(), audit_completed=True,
            data_feasibility_passed=passed, financial_PASS=False, financial_cases=0,
            source_sha256=sha(source), protocol_sha256=sha(out/'protocol.json')))
        print(json.dumps(result, allow_nan=False))
    except Exception as exc:
        write(out / 'failure.json', dict(failed_utc=stamp(), error=repr(exc), evidence_preserved=True, financial_cases_started=0))
        raise


if __name__ == '__main__':
    main()
