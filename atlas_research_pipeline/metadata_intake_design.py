"""Inactive, metadata-only inventory review; never opens referenced archives.

Schema acceptance is not provenance authentication, unseen-data certification,
permission to transfer data, or an execution/financial evaluation protocol.
"""
import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from atlas_exit_research.data import sha, stamp, write
from .spread_preflight import frozen_audit

TOP = {'schema_version','purpose','created_utc','provider','archives'}
ARCHIVE = {'archive_id','source_path','sha256','bytes','coverage_start_utc','coverage_end_utc',
           'acquired_utc','timestamp_timezone','timestamp_basis','bar_size','what_to_show',
           'use_rth','roll_kind','roll_evidence_sha256','exposure','contract'}
CONTRACT = {'symbol','sec_type','con_id','local_symbol','expiry','exchange','currency','multiplier'}
EXPOSURE = {'status','evidence_sha256'}
REFERENCES = [
    dict(title='Interactive Brokers: Futures',url='https://www.interactivebrokers.com/docs/tws-api/contracts/futures',
         role='Contract identity includes security type, exchange, currency, expiry and multiplier. Continuous futures differ from dated contracts. These definitions do not verify an archive or its historical specification.'),
    dict(title='Interactive Brokers: Historical Bars',url='https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars',
         role='Bar size, whatToShow, useRTH and timestamp format/timezone matter. Documentation is not proof of actual coverage, feed alignment or first research receipt.'),
]


def text(value):
    return isinstance(value,str) and 0 < len(value) <= 1024 and not any(ord(c)<32 for c in value)


def utc(value):
    if not text(value):
        return None
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        return d if d.tzinfo is not None and d.utcoffset() is not None and d.utcoffset().total_seconds()==0 else None
    except ValueError:
        return None


def digest(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def review_manifest(packet, as_of):
    """Pure object review: values/path strings are never opened or echoed.

    All future input must remain a preserved private metadata receipt. This
    function is not wired to a connector, directory watcher or quote evaluator.
    """
    errors=set();missing=set();flags=set()
    result=dict(status='REJECTED_METADATA_SHAPE',schema_accepted=False,issue_codes=[],
                archive_bytes_opened=0,archive_hashes_verified=False,contract_verified=False,
                prior_exposure_verified=False,new_temporal_independence_verified=False,
                scoring_authorized=False,transfer_authorized=False,broker_connection=False)
    known=utc(as_of)
    if not isinstance(packet,dict) or set(packet)!=TOP or known is None:
        result['issue_codes']=['TOP_LEVEL_SCHEMA_OR_REVIEW_CLOCK'];return result
    created=utc(packet['created_utc'])
    if created is None or created>known: errors.add('INVALID_OR_FUTURE_METADATA_RECEIPT')
    if packet['schema_version']!=1 or type(packet['schema_version']) is not int or packet['purpose']!='METADATA_ONLY_INVENTORY' or packet['provider']!='IBKR':
        errors.add('WRONG_SCOPE_OR_VERSION')
    archives=packet['archives']
    if not isinstance(archives,list) or len(archives)>1000:
        result['issue_codes']=['ARCHIVE_LIST_SHAPE'];return result
    if not archives: missing.add('NO_AVAILABLE_ARCHIVES_REPORTED')
    ids=set();hashes=set();contracts={}
    for a in archives:
        if not isinstance(a,dict) or set(a)!=ARCHIVE:
            errors.add('ARCHIVE_SCHEMA_UNKNOWN_OR_MISSING_FIELDS');continue
        if not text(a['archive_id']) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',a['archive_id']): errors.add('ARCHIVE_ID')
        elif a['archive_id'] in ids: errors.add('DUPLICATE_ARCHIVE_ID')
        else: ids.add(a['archive_id'])
        # A remote path is only an opaque inventory claim, never a local target.
        if a['source_path'] is None: missing.add('ARCHIVE_PATH_UNREPORTED')
        elif not text(a['source_path']): errors.add('ARCHIVE_PATH_SHAPE')
        if a['sha256'] is None: missing.add('ARCHIVE_DIGEST_UNREPORTED')
        elif not digest(a['sha256']): errors.add('ARCHIVE_DIGEST_FORMAT')
        elif a['sha256'] in hashes: flags.add('DUPLICATE_CONTENT_DIGEST_REQUIRES_REVIEW')
        else: hashes.add(a['sha256'])
        if a['bytes'] is None: missing.add('ARCHIVE_LENGTH_UNREPORTED')
        elif type(a['bytes']) is not int or a['bytes']<=0: errors.add('ARCHIVE_LENGTH_FORMAT')
        begin,end,acquired=(utc(a[k]) for k in ('coverage_start_utc','coverage_end_utc','acquired_utc'))
        if begin is None or end is None or begin>=end: errors.add('INVALID_COVERAGE_INTERVAL')
        elif created is not None:
            if end>created: errors.add('COVERAGE_END_AFTER_METADATA_CREATION')
            # Conservative calendar-date flag only; it is not a synchronized join.
            if begin.date().isoformat()<='2026-10-30' and end.date().isoformat()>='2025-12-15':
                flags.add('POSSIBLE_OVERLAP_WITH_EXPOSED_MT5_DATES_NOT_INDEPENDENT')
        if a['acquired_utc'] is None: missing.add('ORIGINAL_ACQUISITION_TIME_UNREPORTED')
        elif acquired is None or created is None or acquired>created or (end is not None and acquired<end): errors.add('INVALID_ACQUISITION_TIME')
        if a['timestamp_timezone'] is None: missing.add('SOURCE_TIMESTAMP_TIMEZONE_UNREPORTED')
        elif not text(a['timestamp_timezone']): errors.add('SOURCE_TIMEZONE_SHAPE')
        else:
            try: ZoneInfo(a['timestamp_timezone'])
            except (ZoneInfoNotFoundError,ValueError): errors.add('SOURCE_TIMEZONE_UNRECOGNIZED')
        if a['timestamp_basis'] not in ('BAR_OPEN','BAR_CLOSE','UNKNOWN'): errors.add('TIMESTAMP_BASIS')
        elif a['timestamp_basis']=='UNKNOWN': missing.add('TIMESTAMP_BASIS_UNRESOLVED')
        for k in ('bar_size','what_to_show'):
            if a[k] is None: missing.add(k.upper()+'_UNREPORTED')
            elif not text(a[k]): errors.add(k.upper()+'_SHAPE')
        if a['use_rth'] is None: missing.add('RTH_POLICY_UNREPORTED')
        elif type(a['use_rth']) is not bool: errors.add('RTH_POLICY_REQUIRES_BOOLEAN')
        if a['roll_kind'] not in ('SINGLE_CONTRACT','CONTINUOUS','UNKNOWN'): errors.add('ROLL_KIND')
        elif a['roll_kind']!='SINGLE_CONTRACT': flags.add('ROLL_CONSTRUCTION_REQUIRES_INDEPENDENT_REVIEW')
        if a['roll_evidence_sha256'] is not None and not digest(a['roll_evidence_sha256']): errors.add('ROLL_EVIDENCE_DIGEST')
        if a['roll_kind']=='CONTINUOUS' and a['roll_evidence_sha256'] is None: missing.add('ROLL_EVIDENCE_UNREPORTED')
        exposure=a['exposure']
        if not isinstance(exposure,dict) or set(exposure)!=EXPOSURE: errors.add('EXPOSURE_SCHEMA')
        else:
            if exposure['status'] not in ('NONE_REPORTED','FEATURES_INSPECTED','OUTCOMES_SCORED','MIXED','UNKNOWN'): errors.add('EXPOSURE_STATUS')
            if exposure['evidence_sha256'] is not None and not digest(exposure['evidence_sha256']): errors.add('EXPOSURE_EVIDENCE_DIGEST')
            if exposure['status'] in ('UNKNOWN','MIXED') or exposure['evidence_sha256'] is None: missing.add('EXPOSURE_SCOPE_OR_EVIDENCE_UNRESOLVED')
            # Even a NONE_REPORTED claim with a digest cannot certify unused dates.
            flags.add('EXPOSURE_ASSERTION_REQUIRES_INDEPENDENT_REVIEW')
        c=a['contract']
        if not isinstance(c,dict) or set(c)!=CONTRACT: errors.add('CONTRACT_SCHEMA');continue
        if c['symbol'] not in ('MNQ','MES') or c['sec_type'] not in ('FUT','CONTFUT'): errors.add('CONTRACT_OUTSIDE_INVENTORY_SCOPE')
        if c['con_id'] is None: missing.add('CONTRACT_ID_UNREPORTED')
        elif type(c['con_id']) is not int or c['con_id']<=0: errors.add('CONTRACT_ID_FORMAT')
        else:
            signature=json.dumps({k:v for k,v in c.items() if k!='con_id'},sort_keys=True)
            if c['con_id'] in contracts and contracts[c['con_id']]!=signature: flags.add('CONTRACT_IDENTITY_CONFLICT_REQUIRES_REVIEW')
            contracts[c['con_id']]=signature
        for k in ('local_symbol','exchange','currency'):
            if c[k] is None: missing.add('CONTRACT_'+k.upper()+'_UNREPORTED')
            elif not text(c[k]): errors.add('CONTRACT_'+k.upper()+'_SHAPE')
        if c['expiry'] is None:
            if c['sec_type']=='FUT': missing.add('DATED_CONTRACT_EXPIRY_UNREPORTED')
        elif not isinstance(c['expiry'],str) or not re.fullmatch(r'\d{6}(\d{2})?',c['expiry']): errors.add('CONTRACT_EXPIRY_FORMAT')
        else:
            try: datetime.strptime(c['expiry'],'%Y%m' if len(c['expiry'])==6 else '%Y%m%d')
            except ValueError: errors.add('CONTRACT_EXPIRY_DATE')
        if c['multiplier'] is None: missing.add('CONTRACT_MULTIPLIER_UNREPORTED')
        else:
            try:
                if not isinstance(c['multiplier'],str): raise InvalidOperation
                value=Decimal(c['multiplier'])
                if not value.is_finite() or value<=0: raise InvalidOperation
            except (InvalidOperation,ValueError): errors.add('CONTRACT_MULTIPLIER_FORMAT')
        if c['sec_type']=='CONTFUT':
            flags.add('CONTINUOUS_NOT_DATED_FUTURES_REVIEW_REQUIRED')
            if a['roll_kind']!='CONTINUOUS': errors.add('CONTINUOUS_CONTRACT_ROLL_CONFLICT')
    result['schema_accepted']=not errors
    result['status']='REJECTED_METADATA_SHAPE' if errors else ('INCOMPLETE_METADATA_REVIEW_REQUIRED' if missing else 'METADATA_SHAPE_ACCEPTED_REVIEW_REQUIRED')
    result['issue_codes']=sorted(errors|missing|flags)
    return result


def fixture():
    # All identifiers, paths, sizes and hashes below are invented synthetic values.
    a=dict(archive_id='synthetic_archive',source_path='unopened-other-computer/synthetic.json',sha256='a'*64,bytes=123,
           coverage_start_utc='2024-01-01T00:00:00Z',coverage_end_utc='2024-01-02T00:00:00Z',acquired_utc='2024-01-03T00:00:00Z',
           timestamp_timezone='America/New_York',timestamp_basis='BAR_OPEN',bar_size='1 min',what_to_show='TRADES',use_rth=False,
           roll_kind='SINGLE_CONTRACT',roll_evidence_sha256=None,exposure=dict(status='NONE_REPORTED',evidence_sha256='b'*64),
           contract=dict(symbol='MNQ',sec_type='FUT',con_id=123,local_symbol='SYNTHETIC',expiry='202403',exchange='SYNTHETIC',currency='USD',multiplier='99'))
    return dict(schema_version=1,purpose='METADATA_ONLY_INVENTORY',created_utc='2026-11-03T00:00:00Z',provider='IBKR',archives=[a])


def synthetic_checks():
    now='2026-11-03T01:00:00Z';checks={}
    def run(change=None):
        p=fixture()
        if change: change(p)
        return review_manifest(p,now)
    valid=run()
    checks['complete_shape_never_authorizes_scoring']=valid['status']=='METADATA_SHAPE_ACCEPTED_REVIEW_REQUIRED' and valid['scoring_authorized'] is False and valid['contract_verified'] is False
    checks['older_date_not_certified_unused']=not valid['new_temporal_independence_verified'] and not valid['prior_exposure_verified']
    checks['archive_path_never_opened_or_echoed']=valid['archive_bytes_opened']==0 and fixture()['archives'][0]['source_path'] not in json.dumps(valid)
    checks['top_price_payload_rejected']=not run(lambda p:p.update(prices=[1]))['schema_accepted']
    checks['nested_outcome_payload_rejected']=not run(lambda p:p['archives'][0]['contract'].update(net=1))['schema_accepted']
    checks['naive_review_time_rejected']=not review_manifest(fixture(),'2026-11-03T01:00:00')['schema_accepted']
    checks['future_receipt_rejected']=not run(lambda p:p.update(created_utc='2026-11-04T00:00:00Z'))['schema_accepted']
    checks['reversed_coverage_rejected']=not run(lambda p:p['archives'][0].update(coverage_end_utc='2023-12-31T00:00:00Z'))['schema_accepted']
    checks['unrecognized_timezone_rejected']=not run(lambda p:p['archives'][0].update(timestamp_timezone='invented/zone'))['schema_accepted']
    checks['missing_hash_stays_unresolved']=run(lambda p:p['archives'][0].update(sha256=None))['status']=='INCOMPLETE_METADATA_REVIEW_REQUIRED'
    checks['digest_syntax_not_hash_verification']=not valid['archive_hashes_verified']
    checks['duplicate_id_rejected']=not run(lambda p:p['archives'].append(copy.deepcopy(p['archives'][0])))['schema_accepted']
    def duplicate(p):
        other=copy.deepcopy(p['archives'][0]);other['archive_id']='another';p['archives'].append(other)
    checks['duplicate_content_not_independent']='DUPLICATE_CONTENT_DIGEST_REQUIRES_REVIEW' in run(duplicate)['issue_codes']
    def conflict(p):
        duplicate(p);p['archives'][1]['contract']['symbol']='MES'
    checks['contract_identity_conflict_flagged']='CONTRACT_IDENTITY_CONFLICT_REQUIRES_REVIEW' in run(conflict)['issue_codes']
    def overlap(p):
        p['archives'][0].update(coverage_start_utc='2026-01-01T00:00:00Z',coverage_end_utc='2026-01-02T00:00:00Z',acquired_utc='2026-01-03T00:00:00Z')
    checks['other_feed_overlap_not_new_evidence']='POSSIBLE_OVERLAP_WITH_EXPOSED_MT5_DATES_NOT_INDEPENDENT' in run(overlap)['issue_codes']
    def continuous(p):
        p['archives'][0]['contract'].update(sec_type='CONTFUT',expiry=None);p['archives'][0]['roll_kind']='CONTINUOUS'
    checks['continuous_requires_roll_review']='ROLL_EVIDENCE_UNREPORTED' in run(continuous)['issue_codes']
    checks['empty_inventory_not_data_availability']=run(lambda p:p.update(archives=[]))['status']=='INCOMPLETE_METADATA_REVIEW_REQUIRED'
    checks['bool_not_integer_rth']=not run(lambda p:p['archives'][0].update(use_rth=1))['schema_accepted']
    checks['nonfinite_multiplier_rejected']=not run(lambda p:p['archives'][0]['contract'].update(multiplier='NaN'))['schema_accepted']
    checks['unknown_exposure_stays_unresolved']=run(lambda p:p['archives'][0]['exposure'].update(status='UNKNOWN'))['status']=='INCOMPLETE_METADATA_REVIEW_REQUIRED'
    assert all(checks.values()),checks
    return checks


def render(public):
    refs=''.join('<li><a href="'+escape(r['url'])+'">'+escape(r['title'])+'</a>: '+escape(r['role'])+'</li>' for r in REFERENCES)
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trade Dashboard</title><style>body{background:#0b1320;color:#e5edf8;font:16px/1.7 "Segoe UI",sans-serif;margin:auto;max-width:1000px;padding:36px}section{background:#142133;padding:24px;margin:20px 0;border-radius:14px}a{color:#80b7ff}</style><h1>Trade Dashboard</h1><section><h2>IBKR metadata intake preparation</h2><p><strong>INACTIVE - METADATA SHAPE ONLY - NO DATA ACQUIRED</strong></p><p>A strict inventory schema records MNQ/MES archive identity, dates, timezone/bar semantics, dated versus continuous contracts, roll provenance and prior-exposure assertions. It rejects unknown fields rather than admitting prices, outcomes or account content. Referenced archive paths are opaque strings: the review opens no archive, verifies no archive hash and connects to no broker or other computer.</p><p>Twenty synthetic checks passed. They establish shape handling only. Even a complete packet always requires independent provenance review and never authorizes a transfer, financial scoring, unseen-data certification or deployment. An earlier date or different feed is not certified independent evidence. Incomplete clocks, hashes, exposure scope or continuous-series roll records stay unresolved.</p></section><section><h2>Evidence still needed</h2><p>No actual inventory receipt has been evaluated. The previous metadata-only chat handoff remains unexecuted; no repeat message or alternate access attempt occurred. Once the user supplies metadata, preserve its receipt and identity privately before any separate review. Actual archive coverage, byte hashes, prior research exposure, historical contract/tick terms, fees, margins and clocks need independent evidence. A separate complete model/evaluation preregistration is required before outcomes or financial cases. Original MT5 benchmarks and every failed protocol remain preserved; historical SPX execution-sensitive scoring remains deferred.</p><p>Observation remains stopped by user decision. No collector, helper, MT5 initialization, financial case, account action, order or ICT comparison occurred. Returns, win rate and drawdown for this preparation are NOT EVALUATED.</p></section><section><h2>Primary documentation</h2><ul>'''+refs+'''</ul><p>Documentation motivates distinctions in the schema; it cannot certify this user's archive availability or properties.</p></section></html>'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve()
    out=root/'outputs/atlas_research_pipeline_v1';folder=out/'designs/ibkr_metadata_intake_v1'
    if folder.exists(): raise FileExistsError('Preserve existing finite preparation; do not rerun unchanged work')
    registry=json.loads((out/'experiment_registry.json').read_bytes().decode('utf-8'))['experiments'];assert len(registry)==78
    inputs={r['experiment']+'/protocol.json':sha(root/r['experiment']/'protocol.json') for r in registry}
    protected=frozen_audit(root)
    # Read only protocol metadata for the bounded prior-artifact review.
    matches=[]
    for rel in inputs:
        value=json.loads((root/rel).read_bytes().decode('utf-8'))
        if re.search(r'IBKR|metadata.only|metadata_only|handoff|prior.exposure',json.dumps(value),re.I): matches.append(rel)
    folder.mkdir(parents=True)
    (folder/'source_snapshot.py').write_bytes(Path(__file__).read_bytes())
    protocol=dict(registered_utc=stamp(),status='INACTIVE_METADATA_INTAKE_DESIGN',
        purpose='Metadata-only intake shape preparation for a future user-supplied other-computer MNQ/MES inventory. Not an alpha hypothesis, data acquisition, provenance approval or financial comparison.',
        input_scope='Only an in-memory metadata object is reviewed by synthetic fixtures. No actual handoff, archive, quote, fill, account or broker data is opened.',
        source_sha256=sha(Path(__file__)),corpus_protocol_sha256=inputs,bounded_prior_artifact_matches=matches,
        prior_artifact_review='The78-protocol inventory and closest provenance/history-search records distinguish this future receipt schema from the completed SPX/NAS snapshot audit, historical quote diagnostics and inactive FOMC label. This is not a claim that every possible file or research mechanism was semantically reviewed.',
        scope_difference='New pure metadata shape review for a future other-computer inventory; no field can certify archive bytes, original acquisition, exposure, historical contract applicability or independent evidence.',
        schema_fields=dict(packet=sorted(TOP),archive=sorted(ARCHIVE),contract=sorted(CONTRACT),exposure=sorted(EXPOSURE)),
        no_automatic_approval=True,no_archive_dereference=True,no_live_intake_watcher=True,
        observed_exposure_date_flag='Possible calendar overlap with exposed MT5 dates2025-12-15 through2026-10-30 is flagged conservatively, not a synchronized financial join; earlier dates are never automatically unseen.',
        references=REFERENCES,frozen_financial_identities=protected,financial_cases_started=0,financial_observations_scored=0,
        transfer_authorized=False,observation_restarted=False,active_paper_changed=False,ict_used=False)
    write(folder/'protocol.json',protocol)
    try:
        checks=synthetic_checks()
        assert frozen_audit(root)==protected and all(sha(root/rel)==v for rel,v in inputs.items())
        public=dict(completed_utc=stamp(),status='INACTIVE_METADATA_SHAPE_PREPARATION_COMPLETE',synthetic_checks_passed=len(checks),
            actual_metadata_receipts_reviewed=0,archive_bytes_opened=0,archive_hashes_verified=False,new_data_acquired=False,
            financial_cases_started=0,financial_observations_scored=0,financial_PASS=False,net=None,win_rate=None,drawdown=None,
            independent_validation=False,scoring_authorized=False,transfer_authorized=False,observation_restarted=False,
            original_benchmarks_and_risk_unchanged=True,ict_used=False,references=REFERENCES)
        write(folder/'synthetic_checks.json',checks);write(folder/'public_summary.json',public)
        (folder/'report.html').write_text(render(public),encoding='utf-8')
        write(folder/'progress.json',dict(status='metadata_shape_preparation_complete_inactive',financial_cases_started=0,financial_observations_scored=0,actual_metadata_receipts_reviewed=0))
        write(folder/'completed.json',dict(completed_utc=stamp(),preparation_completed=True,financial_PASS=False,
            protocol_sha256=sha(folder/'protocol.json'),source_sha256=sha(Path(__file__)),synthetic_checks_passed=len(checks),
            original_sources_unchanged=True,scoring_authorized=False,financial_cases=0))
        print(json.dumps(public))
    except Exception as exc:
        write(folder/'failure.json',dict(failed_utc=stamp(),error=repr(exc),financial_cases_started=0,preserved=True));raise


if __name__=='__main__': main()
