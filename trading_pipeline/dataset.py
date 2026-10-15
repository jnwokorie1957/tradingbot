"""Separate physical development/validation files; final holdout is never opened."""
import hashlib,json,math
from .engine_v3 import utc,finite

class AdmissionError(ValueError):pass
def file_hash(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_manifest(m,synthetic):
 if m.get('synthetic') is not synthetic:raise AdmissionError('synthetic_label_mismatch')
 if m.get('partition')!='development':raise AdmissionError('protected_or_non_development_dataset')
 if m.get('source_kind')=='legacy_ibkr_observer':raise AdmissionError('legacy_receipt_protected_no_scoring')
 if m.get('verified') is not True or not m.get('review_reference'):raise AdmissionError('provenance_not_independently_verified')
 if m.get('timestamp_semantics_verified') is not True:raise AdmissionError('timestamp_semantics_unverified')
 if m.get('quote_path_verified') is not True:raise AdmissionError('no_verified_next_quote_path')
 if m.get('effective_costs_verified') is not True:raise AdmissionError('effective_dated_costs_unverified')
 if not m.get('source_reference'):raise AdmissionError('source_reference_missing')
 if not synthetic and m.get('prior_exposure')!='unseen_validation':raise AdmissionError('validation_previously_used_or_unknown')
 if set(m.get('files',{}))!={'train','validation'}:raise AdmissionError('separate_train_validation_files_required')
 if m['files']['train']['path']==m['files']['validation']['path']:raise AdmissionError('same_train_validation_file')
 if not m.get('final_holdout',{}).get('commitment_sha256'):raise AdmissionError('holdout_commitment_missing')
 if m['final_holdout'].get('access')!='locked':raise AdmissionError('final_holdout_not_locked')

def load_partition(base,m,phase,contracts):
 spec=m['files'][phase];path=(base/spec['path']).resolve()
 if not path.is_relative_to(base.resolve()):raise AdmissionError('dataset_path_outside_package')
 if file_hash(path)!=spec['sha256']:raise AdmissionError('dataset_hash_mismatch')
 rows=[];seen=set();last=None;last_quotes={};last_bars={};counts={'bars':0,'quotes':0,'rolls':0,'gaps':0}
 start,end=utc(spec['start']),utc(spec['end'])
 for line in path.read_text(encoding='utf-8').splitlines():
  e=json.loads(line);at=utc(e['available_at']);key=e['contract']
  if not start<=at<end:raise AdmissionError('event_outside_partition')
  if last is not None and at<last:raise AdmissionError('out_of_order_events')
  if e['id'] in seen:raise AdmissionError('duplicate_event_identity')
  if key not in contracts:raise AdmissionError('unknown_contract')
  if e.get('partition') in ('protected_holdout_observation','protected_holdout'):raise AdmissionError('protected_observation')
  # Historical availability is distinct from ingestion. Do not relabel legacy receipts.
  if e.get('source_kind')=='legacy_ibkr_observer':raise AdmissionError('legacy_receipt_protected_no_scoring')
  c=contracts[key];tick=c['tick'];finite(tick)
  if tick<=0:raise AdmissionError('invalid_tick')
  if e['kind']=='bar':
   a,b=utc(e['start']),utc(e['end']);finite(e['open'],e['high'],e['low'],e['close'],e['volume'])
   if not a<b<=at or (b-a).total_seconds()!=m['bar_seconds'] or e['volume']<=0:raise AdmissionError('invalid_or_incomplete_bar')
   if not 0<e['low']<=min(e['open'],e['close'])<=max(e['open'],e['close'])<=e['high']:raise AdmissionError('invalid_ohlc')
   if any(abs(e[k]/tick-round(e[k]/tick))>1e-6 for k in ('open','high','low','close')):raise AdmissionError('off_tick_bar')
   previous=last_bars.get(key)
   if previous is not None and a<previous:raise AdmissionError('overlapping_bar')
   if previous is not None and a!=previous:counts['gaps']+=1
   last_bars[key]=b;counts['bars']+=1
  elif e['kind']=='quote':
   qt=utc(e['quote_at']);finite(e['bid'],e['ask'],e['bid_size'],e['ask_size'])
   if not 0<e['bid']<=e['ask'] or min(e['bid_size'],e['ask_size'])<1 or not 0<=(at-qt).total_seconds()<=5 or e.get('quality')!='verified':raise AdmissionError('invalid_quote')
   if any(abs(e[k]/tick-round(e[k]/tick))>1e-6 for k in ('bid','ask')):raise AdmissionError('off_tick_quote')
   if key in last_quotes and qt<=last_quotes[key]:raise AdmissionError('ambiguous_or_regressing_quote')
   last_quotes[key]=qt;counts['quotes']+=1
  elif e['kind']=='roll':counts['rolls']+=1
  elif e['kind']!='margin_update':raise AdmissionError('unsupported_event_type')
  rows.append(e);seen.add(e['id']);last=at
 if not counts['bars'] or not counts['quotes']:raise AdmissionError('bars_and_quotes_required')
 return rows,counts
