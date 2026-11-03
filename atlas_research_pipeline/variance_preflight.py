"""One-time data-only feasibility audit; no financial scoring or broker imports."""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from atlas_exit_research.data import sha, stamp, write
from research_monitor.audit_support import clock_epoch


NY = ZoneInfo('America/New_York')
START, END = '2025-12-15', '2026-05-31'
LOOKBACK = 60
SOURCE = 'https://amoreira2.github.io/alan-moreira.github.io/VolPortfolios_published.pdf'
FILES = {
    'NAS100': 'outputs/nas100_quote_data_v1/NAS100_M1.csv',
    'SPX500': 'outputs/spx15_canonical_quote_data_v1/SPX500_M1.csv',
}


def weekdays(start, end):
    current, finish = date.fromisoformat(start), date.fromisoformat(end)
    while current <= finish:
        if current.weekday() < 5:
            yield current.isoformat()
        current += timedelta(days=1)


def previous_weekday(day):
    current = date.fromisoformat(day) - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current.isoformat()


def reference_variance(rows):
    """Reject gaps/duplicates; do not bridge missing minutes or fabricate bars."""
    if len(rows) != 390 or sorted(rows) != list(range(570, 960)):
        return None
    previous, terms = rows[570]['open'], []
    for minute in range(570, 960):
        row = rows[minute]
        values = [row[k] for k in ('open', 'high', 'low', 'close')]
        if not all(math.isfinite(v) and v > 0 for v in values):
            return None
        if row['low'] > min(values) or row['high'] < max(values):
            return None
        terms.append(math.log(row['close'] / previous) ** 2)
        previous = row['close']
    value = math.fsum(terms)
    return value if value > 0 and math.isfinite(value) else None


def features(variances, days):
    """All normalizer sessions precede the immediately preceding weekday."""
    result = []
    for day in days:
        previous = previous_weekday(day)
        history = sorted((d, v) for d, v in variances.items() if d < previous)
        row = dict(date=day, previous_weekday=previous)
        if previous not in variances:
            row.update(status='previous_reference_window_incomplete_or_absent')
        elif len(history) < LOOKBACK:
            row.update(status='insufficient_prior_complete_reference_windows', available=len(history))
        else:
            used = history[-LOOKBACK:]
            normalizer = median(v for _, v in used)
            row.update(status='feature_available', scale=min(1., normalizer / variances[previous]),
                       normalization_first=used[0][0], normalization_last=used[-1][0],
                       prior_variance=variances[previous], normalization_median=normalizer)
            assert row['normalization_last'] < previous < day and 0 < row['scale'] <= 1
        result.append(row)
    return result


def audit(path):
    sessions, duplicates = defaultdict(dict), Counter()
    rows_read = 0
    first = None
    with path.open(newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            local = datetime.fromtimestamp(clock_epoch(int(row['time_epoch_mt5']), 'ny_dst_inferred'), timezone.utc).astimezone(NY)
            day, minute = local.date().isoformat(), local.hour * 60 + local.minute
            if day > END:
                continue
            rows_read += 1
            first = min(first, day) if first else day
            if local.weekday() >= 5 or not 570 <= minute < 960:
                continue
            if minute in sessions[day] or local.second != 0:
                duplicates[day] += 1
            sessions[day][minute] = {k: float(row[k]) for k in ('open', 'high', 'low', 'close')}
    variances = {d: v for d, rows in sessions.items()
                 if not duplicates[d] and (v := reference_variance(rows)) is not None}
    days = list(weekdays(START, END))
    rows = features(variances, days)
    available = [r for r in rows if r['status'] == 'feature_available']
    # Prefix invariance is a causal check: adding later rows cannot alter an earlier feature.
    causal = all(features({d: v for d, v in variances.items() if d < row['date']}, [row['date']])[0] == row for row in rows)
    assert causal
    summary = dict(first_observed_date=first, latest_admitted_date=END,
                   rows_admitted_through_development_end=rows_read,
                   full_reference_windows=len(variances), duplicate_reference_dates=len(duplicates),
                   development_weekdays=len(days), feature_available_days=len(available),
                   feature_first=available[0]['date'] if available else None,
                   feature_last=available[-1]['date'] if available else None,
                   reduced_budget_days=sum(r['scale'] < 1 for r in available),
                   unavailable_reasons=dict(Counter(r['status'] for r in rows if r['status'] != 'feature_available')),
                   causal_prefix_invariance=causal, feasibility_gate=len(available) >= 20,
                   missing_weekdays_are_not_classified_as_holidays=True,
                   financial_outcomes_scored=0)
    return summary, dict(reference_minute_counts={d: len(sessions.get(d, {})) for d in days}, features=rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    out = root / 'outputs/atlas_research_pipeline_v1/feasibility/variance_budget_v1'
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__)
    paths = {s: root / p for s, p in FILES.items()}
    identities = {s: dict(path=FILES[s], sha256=sha(p)) for s, p in paths.items()}
    registry = root / 'outputs/atlas_research_pipeline_v1/experiment_registry.json'
    records = json.loads(registry.read_text(encoding='utf-8'))['experiments']
    related = ['spx15_adaptive_2026_10_31', 'spx15_drawdown_2026_10_31',
               'spx15_recovery_ramp_v1', 'spx15_sub20_2026_10_31',
               'portfolio_25_protection_v1', 'portfolio_25_discipline_v1',
               'atlas_pair_holding_v1', 'atlas_research_pipeline_v1/cycles/002']
    protocol = dict(registered_utc=stamp(), status='FEASIBILITY_ONLY_NO_FINANCIAL_SCORING',
        purpose='Assess whether existing development data can support one causal, capped variance-budget hypothesis before any financial implementation.',
        literature=dict(title='Volatility-Managed Portfolios', authors=['Alan Moreira', 'Tyler Muir'],
            year=2017, doi='10.1111/jofi.12513', url=SOURCE,
            paraphrase='The paper scales monthly factor returns using prior-month realized variance. Its factor evidence does not establish an intraday CFD result.',
            adaptation='Daily 1m reference-window variance, a trailing median normalization and a cap-only budget are our proposed adaptation, not the published implementation.'),
        proposed_hypothesis='Reducing only planned new-entry risk after unusually volatile completed sessions may reduce adverse portfolio exposure. Natural-stop sizing already reduces quantity as stop width grows, so this can double-reduce exposure and worsen minimum-lot capture.',
        proposed_rules=dict(reference_window='09:30-16:00 America/New_York,390 complete minute bars under the existing inferred clock; not independently verified venue hours',
            variance='Squared log close-to-close returns; first minute uses its open. No overnight return. Reject incomplete, duplicated or invalid windows.',
            lag='Immediately preceding weekday must be complete; missing holidays or early closes remain unavailable rather than inferred.',
            normalization='Median of60 complete reference-window variances strictly before the lag session',
            scale='min(1,median60/prior_variance)',
            planned_budget='A possible future experimental wrapper may only reduce min(0.5% current equity,25USD), original recovery controls and remaining gross portfolio headroom. No leverage or risk increase.',
            entries_and_exits='Preserve original SPX15 1.5R60minutes and NAS15 2R90minutes capped16NY, including natural initial stops, signal rules, legal lots and cost assumptions.',
            future_costs=['standard','higher','severe'], fallback='No imputation or reduced warmup; no alternate lookback or threshold selected from this audit.'),
        development=[START, END], feasibility_gate='At least20 development weekdays with a causal feature for EACH instrument; this is data feasibility, not financial sample sufficiency.',
        duplicate_review=dict(registry_sha256=sha(registry), prior_records=len(records), related=related,
            conclusion='Prior fixed/loss/drawdown risk cuts, ATR entry gates, holding changes and break-even exits are related but do not use this lagged realized-variance budget. A negative text search alone was not treated as semantic proof.'),
        inputs=identities, source_sha256=sha(source), source_file='atlas_research_pipeline/variance_preflight.py',
        limitations=['All prices are previously exposed; no independent validation.', 'Historical server/DST, commissions, margin, liquidity and reference-window coverage remain uncertain.',
                    'Feature availability is not an eligible trade, missed winner, return forecast or target pass.',
                    'No candidate selection, financial replay, paper-book change or new collection occurs in this audit.'],
        paper_only=True, financial_outcomes_scored=0, active_paper_changed=False,
        atlas_observation='Stopped by explicit user decision; this audit does not initialize a terminal.',
        ict_source_used=False)
    write(out / 'protocol.json', protocol)
    (out / 'source_snapshot.py').write_bytes(source.read_bytes())
    try:
        rows = {}
        for symbol, path in paths.items():
            rows[symbol], private = audit(path)
            write(out / f'private_features_{symbol}.json', private)
            assert sha(path) == identities[symbol]['sha256']
        passed = all(r['feasibility_gate'] for r in rows.values())
        result = dict(completed_utc=stamp(), status='FEASIBLE_FOR_SEPARATE_FINANCIAL_PROTOCOL' if passed else 'DEFERRED_INSUFFICIENT_REFERENCE_COVERAGE',
            instruments=rows, financial_outcomes_scored=0, financial_cases_started=0,
            independent_validation=False, active_paper_changed=False, observation_restarted=False,
            next_action='A separate frozen six-case financial protocol and synthetic allocator checks would be needed before any scoring.' if passed else 'Acquire additional quality-audited history; do not shorten the registered warmup or repair missing reference windows from outcomes.')
        write(out / 'results.json', result)
        write(out / 'completed.json', dict(completed_utc=stamp(), audit_completed=True, data_feasibility_passed=passed,
            financial_PASS=False, financial_cases=0, source_sha256=sha(source), protocol_sha256=sha(out / 'protocol.json')))
        print(json.dumps(result, allow_nan=False))
    except Exception as exc:
        write(out / 'failure.json', dict(failed_utc=stamp(), error=repr(exc), preserved=True, financial_cases_started=0))
        raise


if __name__ == '__main__':
    main()
