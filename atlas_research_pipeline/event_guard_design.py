"""Inactive, calendar-only research design. No quote, broker or financial evaluator."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from atlas_exit_research.data import sha, stamp, write


REFERENCES = [
    dict(title='Gurkaynak, Sack and Swanson (2004), Do Actions Speak Louder Than Words?',
         url='https://www.federalreserve.gov/pubs/feds/2004/200466/200466pap.pdf',
         role='Primary intraday evidence that policy actions and statement information can move asset prices. Not evidence that an entry exclusion is profitable.'),
    dict(title='Wongswan (2005), The Response of Global Equity Indexes to U.S. Monetary Policy Announcements',
         url='https://www.federalreserve.gov/pubs/ifdp/2005/844/ifdp844.htm',
         role='Section 2.1 describes a 10-minute-before/20-minute-after monetary-surprise window. Its equity-response analysis also uses a wider window. Neither is a recommended trading exclusion.'),
    dict(title='Federal Reserve meeting calendars and information',
         url='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
         role='Agency dates and links are metadata leads. A page retrieved today does not establish what this research system knew before a historical entry.'),
    dict(title='Federal Reserve January 28, 2026 statement release header',
         url='https://www.federalreserve.gov/newsevents/pressreleases/monetary20260128a.htm',
         role='The header explicitly states 2:00 p.m. EST for this release. Do not generalize that clock to every historical event or infer a CFD broker offset.'),
]


def aware(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def eligibility(at, events, calendar_available_at, coverage_confirmed):
    """Pure hypothetical admission label, with no position or order action.

    The coverage certificate and each event version must actually be available
    by admission time. Event dictionaries cannot contain price/return/surprise
    fields. A later retrieval is not substituted for earlier knowledge.
    """
    if not aware(at) or not aware(calendar_available_at) or calendar_available_at > at or coverage_confirmed is not True or not isinstance(events, list):
        return 'UNAVAILABLE_REQUIRES_REVIEW'
    for event in events:
        if not isinstance(event, dict) or set(event) != {'kind', 'release_at', 'available_at'}:
            return 'UNAVAILABLE_REQUIRES_REVIEW'
        if not aware(event['release_at']) or not aware(event['available_at']) or event['available_at'] > at:
            return 'UNAVAILABLE_REQUIRES_REVIEW'
    for event in events:
        if event['kind'] != 'FOMC_SCHEDULED_STATEMENT':
            continue
        if event['release_at'] - timedelta(minutes=10) <= at < event['release_at'] + timedelta(minutes=20):
            return 'EXCLUDE_THIS_NEW_NAS_ENTRY'
    return 'UNCHANGED_BASELINE_ELIGIBILITY'


def synthetic_checks():
    ny = ZoneInfo('America/New_York')
    event_at = datetime(2026, 1, 28, 14, tzinfo=ny)
    available = event_at - timedelta(days=30)
    event = dict(kind='FOMC_SCHEDULED_STATEMENT', release_at=event_at, available_at=available)
    run = lambda at, es=None, known=available, covered=True: eligibility(at, [event] if es is None else es, known, covered)
    checks = {}
    checks['half_open_boundaries'] = [run(event_at + timedelta(seconds=s)) for s in [-601,-600,1199,1200]] == [
        'UNCHANGED_BASELINE_ELIGIBILITY','EXCLUDE_THIS_NEW_NAS_ENTRY','EXCLUDE_THIS_NEW_NAS_ENTRY','UNCHANGED_BASELINE_ELIGIBILITY']
    checks['missing_coverage_not_no_event'] = run(event_at, covered=False) == 'UNAVAILABLE_REQUIRES_REVIEW'
    checks['future_calendar_receipt_rejected'] = run(event_at, known=event_at + timedelta(seconds=1)) == 'UNAVAILABLE_REQUIRES_REVIEW'
    checks['future_event_version_rejected'] = run(event_at, [dict(event, available_at=event_at + timedelta(seconds=1))]) == 'UNAVAILABLE_REQUIRES_REVIEW'
    checks['naive_clocks_rejected'] = run(event_at.replace(tzinfo=None)) == 'UNAVAILABLE_REQUIRES_REVIEW'
    checks['outcome_fields_not_accepted'] = run(event_at, [dict(event, surprise=0.5)]) == 'UNAVAILABLE_REQUIRES_REVIEW'
    invalid = dict(event, surprise=0.5)
    checks['full_calendar_validation_is_order_invariant'] = run(event_at, [event, invalid]) == run(event_at, [invalid, event]) == 'UNAVAILABLE_REQUIRES_REVIEW'
    checks['other_event_types_not_silently_added'] = run(event_at, [dict(event, kind='PRESS_CONFERENCE')]) == 'UNCHANGED_BASELINE_ELIGIBILITY'
    checks['ny_dst_distinct_from_broker_clock'] = event_at.astimezone(timezone.utc).hour == 19 and datetime(2026,3,18,14,tzinfo=ny).astimezone(timezone.utc).hour == 18
    assert all(checks.values()), checks
    return checks


def render(data):
    refs=''.join('<li><a href="'+escape(r['url'])+'">'+escape(r['title'])+'</a>: '+escape(r['role'])+'</li>' for r in data['references'])
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trade Dashboard</title><style>body{background:#0b1320;color:#e5edf8;font:15px/1.7 "Segoe UI",sans-serif;margin:auto;max-width:1000px;padding:36px}section{background:#142133;border:1px solid #293b53;padding:24px;margin:20px 0;border-radius:14px}a{color:#80b7ff}strong{color:#f4cf82}</style><h1>Trade Dashboard</h1><section><h2>Scheduled FOMC entry design</h2><p><strong>DESIGN ONLY · NOT ACTIVATED · NO FINANCIAL OBSERVATIONS SCORED</strong></p><p>One distinct research hypothesis: exclude a new NAS15 admission from ten minutes before to twenty minutes after an agency-scheduled FOMC statement, using only calendar versions actually available before that admission. The interval includes its starting instant and excludes its ending instant. Cancel that signal; do not delay it into a later fill. SPX remains unchanged.</p><p>This is an inference motivated by event research, not a published profitable trading rule. It can miss profitable news-driven entries. The window does not encompass a separate press conference, unscheduled announcements, or the risk of an already open position.</p></section><section><h2>Evidence and readiness</h2><p>The bounded semantic review covers 77 retained protocols: fixed clock/seasonal filters, price/MA/efficiency/retest regimes, loss-based pauses, exits/holding, risk sizing and spread-conditioned waiting. None defines this dated, exogenous statement-calendar mechanism. This bounded review is not a claim about every possible prior file or the broader literature.</p><p>Nine synthetic timestamp/as-of/schema checks passed. They establish only behavior of an inactive label function. There are no calendar-to-signal joins, intercepted-entry counts, new market observations, fills, net returns, win rates or drawdowns for this idea. Those financial values are NOT EVALUATED, not zero.</p><p>Required first: complete and versioned calendar provenance, actual as-of receipt evidence, event revisions, clock/contract compatibility and a separately frozen full evaluation protocol. Current agency pages do not certify historical knowledge. Missing calendar coverage blocks readiness. Observation remains stopped by user decision; future collection requires explicit reactivation and a new pre-observation freeze. Original prospective cohorts cannot adopt another worker.</p></section><section><h2>Limits preserved</h2><p>Research capital $5,000. Keep original entries, natural stops, SPX 1.5R/60 minutes and NAS 2R/90 minutes, all approved risk ceilings, legal increments and standard/higher/severe cost assumptions. No risk, leverage, stop, minimum-lot, fee or contract relaxation. Original $500 books remain separate. No financial replay, active-book change or deployment. Historical SPX specification applicability remains unresolved.</p><p>All MT5 history through October 30 was already exposed. No reused date is relabelled untouched. Future financial comparison must use one fixed candidate, all three costs, shared chronological portfolio risk, full paths and preregistered sample/uncertainty/qualification rules before observations; no neighboring-window search after outcomes.</p></section><section><h2>Primary sources</h2><ul>'''+refs+'''</ul><p>Source studies identify announcement effects, not the after-cost expectancy of this CFD entry guard. No announcement-price/shock dataset or ICT material was used.</p></section></html>'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve()
    out=root/'outputs/atlas_research_pipeline_v1';folder=out/'designs/fomc_entry_guard_v1'
    if folder.exists():raise RuntimeError('Preserve existing design; unchanged rerun or refit prohibited')
    registry_file=out/'experiment_registry.json';registry=json.loads(registry_file.read_text(encoding='utf-8'))
    assert len(registry['experiments'])==77
    inputs={}
    for record in registry['experiments']:
        assert 'ict' not in record['experiment'].lower()
        path=root/record['experiment']/'protocol.json';assert path.is_file();inputs[str(path.relative_to(root)).replace('\\','/')]=sha(path)
    assert len(inputs)==77
    protected={}
    for rel in ['outputs/atlas_pair_prospective_v1/protocol.json','outputs/atlas_nas15_prospective_v1/protocol.json']:
        protocol=json.loads((root/rel).read_text(encoding='utf-8'))
        for name,digest in protocol['source_sha256'].items():assert sha(root/name)==digest;protected[name]=digest
    checks=synthetic_checks()
    folder.mkdir(parents=True)
    source=Path(__file__);source_digest=sha(source);(folder/'source_snapshot.py').write_bytes(source.read_bytes())
    duplicate_review=dict(corpus_studies=77,corpus_protocols=77,scope='All protocol.json documents in the retained registry; no ICT files or financial outcome joins.',
        candidate_mechanism='Exogenous agency-scheduled statement date/time, with as-of calendar availability; one NAS-only entry gate.',
        nearest_prior=[
            dict(study='NAS_SPX_seasonal_study',difference='Meteorological seasons from broker calendar; not dated monetary-policy releases.'),
            dict(study='spx15_frequency_v1 and NAS opportunity/session studies',difference='Fixed time-of-day eligibility windows; not an exogenous event-specific gate.'),
            dict(study='portfolio_25_discipline_v1',difference='Pauses based on realized losses; not independent preannounced agency timestamps.'),
            dict(study='cycle003 and spread_wait_v1',difference='Lagged quote variance budget or observed-spread wait; not a dated calendar predicate.')],
        review='Distinct within this bounded retained-protocol corpus. Prior price, trend, retest, exit/holding, risk and execution rules remain archived.',
        input_protocol_sha256=inputs,financial_outcomes_consulted_for_rule_selection=False)
    protocol=dict(registered_utc=stamp(),status='DESIGN_ONLY_NOT_ACTIVATED',hypothesis='Avoiding new NAS entries in a fixed scheduled FOMC-statement identification window might improve after-cost robustness, but may discard profitable opportunities.',
        mechanism_rule=dict(lane='NAS15 only',event='Agency-scheduled FOMC statement only',interval_seconds=[-600,1200],boundaries='start inclusive,end exclusive',
            timestamp='Actual causal admission receipt time under the unchanged baseline; source/broker clock must first be reconciled.',
            within_window='Exclude that new signal. No deferred entry, post-window resurrection, altered stop or existing-position action.',
            outside_window='Unchanged baseline eligibility. No policy surprise, statement sentiment, price move or future information is an input.',
            unavailable='Incomplete calendar, later receipt/version or naive clock means unavailable/review; never silently no-event.'),
        source_role='Published identification window used as a fixed research adaptation, not an optimized or recommended trading pause.',references=REFERENCES,
        control='Retained two-lane exploratory reference: SPX15 1.5R/60min and NAS15 2R/90min, unchanged original entry definitions, natural stops, recovery and 60sec timing.',
        costs=['standard','higher','severe'],risk=dict(capital=5000,per_trade='min(0.5percent current equity,25USD) all-in',gross_open='1percent',daily_pause='2percent',peak_drawdown_pause='10percent',count_quota=None),
        before_financial_activation=['Complete agency calendar with versions/revisions and original publication versus actual research receipt timestamps. Current website retrieval is not historical vintage proof.',
            'Explicit event/timezone/NY clock and contract/source-clock reconciliation. No historical SPX precision/tick-value substitution.',
            'Calendar-only feasibility protocol frozen before any calendar-to-signal join; no profitable event/date selection.',
            'A separate complete evaluator/data/profile/sample/uncertainty/acceptance freeze before scoring or acquiring a new financial cohort. This design is not that freeze.',
            'Explicit user reactivation plus a new pre-observation freeze for any future collection; old prospective identities and stopped books remain untouched.'],
        trial_policy='One fixed rule, no 5/15/30/60-minute neighboring search after outcomes. Any future financial comparison includes all three costs and shared chronological portfolio risk; retain every failure.',
        calendar_fields=['event_kind','scheduled_release_utc','source_original_publication_utc','actual_calendar_receipt_utc','revision_lineage','source_uri','document_sha256','covered_period','retrieved_utc'],
        data_exposure='All existing MT5 dates through2026-10-30 already exposed. No new temporal financial evidence or untouched OOS claimed.',
        limitations=['No financial outcome, interception count or calendar-to-signal feature join was computed.','Separate press conferences/unscheduled events and already open positions remain outside this proposed new-entry gate.','CFD fee, margin, historical contract and clock assumptions remain estimates/unresolved. No futures relabelling.','A narrower entry universe may reduce net profit and opportunity capture; no benefit is assumed.'],
        duplicate_review='duplicate_review.json',source_sha256=source_digest,frozen_source_count=len(protected),synthetic_checks=checks,financial_cases_started=0,financial_observations_scored=0,active_paper_changed=False,observation_restarted=False,broker_connection=False,ict_used=False,deployment=False)
    write(folder/'protocol.json',protocol);write(folder/'duplicate_review.json',duplicate_review)
    write(folder/'input_identity.json',dict(registry_sha256=sha(registry_file),protocol_sha256=inputs,protected_source_sha256=protected))
    summary=dict(status='DESIGN_ONLY_NOT_ACTIVATED',registered_utc=protocol['registered_utc'],hypothesis=protocol['hypothesis'],rule=protocol['mechanism_rule'],
        references=REFERENCES,costs=protocol['costs'],risk=protocol['risk'],reviewed_protocols=77,synthetic_checks_passed=len(checks),calendar_to_signal_joins=0,
        financial_cases_started=0,financial_observations_scored=0,financial_result=None,independent_validation=False,active_paper_changed=False,observation_restarted=False,ict_used=False,deployment=False,
        readiness='Calendar vintage, complete coverage, clock/contract reconciliation and separate full evaluation freeze required. No ongoing collection; stopped by user.',
        limitations=protocol['limitations'],protocol_sha256=sha(folder/'protocol.json'),source_sha256=source_digest)
    write(folder/'public_summary.json',summary);write(folder/'progress.json',dict(status='design_only_not_activated',financial_cases_started=0,financial_observations_scored=0))
    (folder/'design.html').write_text(render(summary),encoding='utf-8')
    assert all(sha(root/name)==digest for name,digest in inputs.items())
    assert all(sha(root/name)==digest for name,digest in protected.items())
    write(folder/'post_design_audit.json',dict(recorded_utc=stamp(),inputs_unchanged=True,frozen_sources_unchanged=True,financial_cases_started=0,calendar_to_signal_joins=0,
        source_snapshot_matches=sha(folder/'source_snapshot.py')==source_digest,synthetic_checks_passed=len(checks),observation_restarted=False,ict_used=False))
    print(json.dumps(summary))


if __name__=='__main__':main()
