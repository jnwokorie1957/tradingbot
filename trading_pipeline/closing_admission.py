"""Strict file admission for closing-strategy chronological research."""
import json,math
from pathlib import Path
from .dataset import AdmissionError,validate_manifest,load_partition,file_hash
from .engine_v4 import Engine,Ledger,utc
from .closing_continuation import decide
from datetime import timedelta

RISK=dict(budget=500,trade_risk=.005,portfolio_risk=.01,daily_pause=.02,drawdown_pause=.10)
SCENARIOS=[dict(id='baseline',fee_factor=1,slippage_ticks=1),dict(id='stress',fee_factor=1.5,slippage_ticks=2)]

def read_json(base,spec):
    base=Path(base).resolve();path=(base/spec['path']).resolve()
    if not path.is_relative_to(base):raise AdmissionError('evidence_path_outside_dataset')
    if file_hash(path)!=spec['sha256']:raise AdmissionError('evidence_hash_mismatch')
    return json.loads(path.read_text(encoding='utf-8'))

def admit(manifest,contracts,plan):
    synthetic=manifest.get('synthetic') is True
    validate_manifest(manifest,synthetic)
    if manifest.get('bar_seconds')!=300:raise AdmissionError('five_minute_trade_bars_required')
    if plan.get('risk')!=RISK or plan.get('scenarios')!=SCENARIOS:raise AdmissionError('fixed_risk_and_cost_scenarios_required')
    if plan.get('strategy')!='closing_half_hour_continuation/1.0.0':raise AdmissionError('fixed_closing_strategy_required')
    a,b=manifest['files']['train'],manifest['files']['validation'];hold=manifest['final_holdout']
    if not utc(a['start'])<utc(a['end'])<utc(b['start'])<utc(b['end'])<utc(hold['start']):raise AdmissionError('partition_overlap')
    if min((utc(b['start'])-utc(a['end'])).total_seconds(),(utc(hold['start'])-utc(b['end'])).total_seconds())<3600:raise AdmissionError('one_hour_embargo_required')
    previous=None
    if len(plan.get('validation_windows',[]))<2:raise AdmissionError('two_validation_windows_required')
    for window in plan['validation_windows']:
        start,end=utc(window['start']),utc(window['end'])
        if not utc(b['start'])<=start<end<=utc(b['end']):raise AdmissionError('invalid_fold_bounds')
        if previous and (start-previous).total_seconds()<3600:raise AdmissionError('fold_overlap_or_missing_embargo')
        previous=end
    admin=manifest.get('administrative',{})
    if (admin.get('complete') is not True or not admin.get('review_reference') or not admin.get('source_reference')
        or utc(admin['start'])>utc(a['start']) or utc(admin['end'])<utc(b['end'])):
        raise AdmissionError('complete_administrative_history_required')
    if manifest.get('static_costs_unchanged_verified') is not True:raise AdmissionError('static_cost_coverage_unverified')
    if not contracts:raise AdmissionError('contracts_required')
    for c in contracts.values():
        if c.get('root') not in ('MNQ','MES') and not (synthetic and c.get('root')=='TEST'):raise AdmissionError('unsupported_strategy_contract')
        if c.get('currency')!='USD' or type(c.get('contract_id')) is not int or c['contract_id']<=0:raise AdmissionError('invalid_contract_identity')
        if not all(c.get(k) is True for k in ('spec_verified','permission_verified','costs_verified','data_verified')):raise AdmissionError('unverified_contract_evidence')
        if (not c.get('evidence_source') or not c.get('evidence_available_at')
            or utc(c['evidence_available_at'])>utc(a['start']) or utc(c['valid_from'])>utc(a['start'])
            or utc(c['valid_until'])<utc(b['end']) or utc(c['exit_before'])<=utc(b['end'])):
            raise AdmissionError('contract_cost_evidence_does_not_cover_study')
        for k in ('tick','multiplier','initial_margin','maintenance_margin','fee_per_side','daily_carry_fee'):
            v=c.get(k)
            if type(v) not in (int,float) or not math.isfinite(v) or v<0 or (k in ('tick','multiplier','initial_margin','maintenance_margin') and v==0):raise AdmissionError('invalid_cost_or_margin')

def administrative(base,manifest,contracts):
    rows=read_json(base,manifest['administrative']);seen=set();last=None
    if not isinstance(rows,list):raise AdmissionError('administrative_list_required')
    ledger=Ledger(':memory:')
    try:
        engine=Engine(ledger,'admin-evidence-only',contracts,synthetic=manifest['synthetic'])
        for e in rows:
            if e.get('kind')!='margin_update' or e.get('contract') not in contracts:raise AdmissionError('margin_announcements_only')
            if e.get('source_kind')=='legacy_ibkr_observer' or e.get('partition','').startswith('protected'):raise AdmissionError('protected_admin_evidence')
            at=utc(e['available_at'])
            if e['id'] in seen or last and at<last:raise AdmissionError('duplicate_or_nonchronological_admin')
            if at>=utc(manifest['administrative']['end']):raise AdmissionError('admin_outside_coverage')
            engine.apply(e);seen.add(e['id']);last=at
    finally:ledger.close()
    return rows

def partition(base,manifest,phase,contracts):
    rows,quality=load_partition(Path(base),manifest,phase,contracts)
    if any(e['kind'] not in ('bar','quote') for e in rows):raise AdmissionError('market_file_bars_quotes_only')
    if any(e.get('quality')!='verified' or e.get('bar_kind')!='TRADES' for e in rows if e['kind']=='bar'):raise AdmissionError('verified_trade_bars_required')
    sessions=read_json(base,manifest['calendars'][phase])
    if not isinstance(sessions,dict) or not sessions:raise AdmissionError('sessions_required')
    for s in sessions.values():
        if s['contract'] not in contracts or utc(s['available_at'])>utc(s['open']):raise AdmissionError('calendar_not_known_before_open')
        decision=(utc(s['close'])-timedelta(minutes=30)).isoformat()
        decide([],s,contracts[s['contract']]['tick'],decision)
    return rows,sessions,quality

def fold_events(rows,sessions,admin,window):
    start,end=utc(window['start']),utc(window['end'])
    selected={sid:s for sid,s in sessions.items() if start<=utc(s['open'])<end}
    if not selected:raise AdmissionError('fold_has_no_sessions')
    for s in selected.values():
        if utc(s['previous_close'])<start or utc(s['close'])>=end:raise AdmissionError('whole_session_and_prior_close_required')
    events=[e for e in rows if start<=utc(e['available_at'])<end]
    events += [e for e in admin if utc(e['available_at'])<end]
    for sid,s in selected.items():
        events.extend([dict(id='generated-decision-'+sid,kind='decision',contract=s['contract'],session_id=sid,available_at=(utc(s['close'])-timedelta(minutes=30)).isoformat()),
                       dict(id='generated-close-'+sid,kind='clock',contract=s['contract'],available_at=s['close'])])
    if len({e['id'] for e in events})!=len(events):raise AdmissionError('cross_stream_duplicate_id')
    # Bars/announcements known at the clock are observed before its decision; quotes follow.
    events.sort(key=lambda e:(utc(e['available_at']),{'margin_update':0,'bar':1,'decision':2,'clock':2,'quote':3}[e['kind']]))
    return events,selected
