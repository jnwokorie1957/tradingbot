"""Finite documentary clock audit. No quote alignment, broker or outcome scoring."""
import argparse,json,math,re,subprocess
from collections import Counter
from html import escape
from pathlib import Path
from atlas_exit_research.data import sha,stamp,write
from .spread_preflight import frozen_audit

SYMBOLS=('NAS100','SPX500')
CONTEXT=('captured_utc','captured_at','snapshot_utc','last_poll_utc','updated_utc','at_utc','registered_utc')
EFFECTIVE=('effective_from','effective_to','valid_from','valid_to','effective_date')
SKIP={'account','account_info','private_fills','fills','curve','cash_curve','prices','quotes','bars','ticks','source_sha256','source_hashes','input_identities'}
REFERENCES=[
 dict(title='MetaQuotes Python copy_ticks_range',url='https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py',
      scope='Documents UTC tick/bar-open times and aware UTC requests. Documentation is not a broker-specific historical mapping or proof that this archive follows those semantics.'),
 dict(title='MetaQuotes TimeTradeServer',url='https://www.mql5.com/en/docs/dateandtime/timetradeserver',
      scope='Describes a current server-time estimate computed by the client and dependent on computer time settings. Not a historical server timezone revision service.'),
 dict(title='MetaQuotes universal time',url='https://www.mql5.com/en/book/common/timing/timing_gmt',
      scope='Distinguishes computer-derived UTC, local DST and chart/server time conversion. Local or New York DST does not establish this broker historical policy.'),
]

def valid_offset(v):
 return type(v) in (int,float) and math.isfinite(v) and abs(v)<=24

def extract(value,path=(),context=(),effective=()):
 """Only named offset fields and documentary context; never prices or account data."""
 found=[]
 if isinstance(value,dict):
  context=context+tuple((k,str(value[k])) for k in CONTEXT if value.get(k))
  effective=effective+tuple((k,str(value[k])) for k in EFFECTIVE if value.get(k))
  if 'offset_hours' in value:
   raw=value['offset_hours']
   if isinstance(raw,dict):
    pairs=[(s,raw[s],'protocol_or_mapping_assertion') for s in SYMBOLS if s in raw]
   else:
    symbol=next((p for p in reversed(path) if p in SYMBOLS),None)
    pairs=[(symbol,raw,'saved_clock_metadata')] if symbol else []
   for symbol,offset,role in pairs:
    state='UNAVAILABLE' if offset is None else ('NUMERIC_ASSERTION_UNVERIFIED' if valid_offset(offset) else 'INVALID_OFFSET_ASSERTION')
    found.append(dict(symbol=symbol,json_path='/'+'/'.join(path),offset_hours=offset if valid_offset(offset) else None,
      state=state,role=role,fresh_samples=value.get('fresh_samples') if type(value.get('fresh_samples')) is int else None,
      context_time_fields=list(context),explicit_effective_fields=list(effective),historical_applicability_verified=False))
  for key,child in value.items():
   if key not in SKIP and key!='offset_hours' and isinstance(child,(dict,list)):
    found+=extract(child,path+(key,),context,effective)
 elif isinstance(value,list):
  for i,child in enumerate(value):
   if isinstance(child,(dict,list)):found+=extract(child,path+(str(i),),context,effective)
 return found

def summarize(documents):
 result={}
 for symbol in SYMBOLS:
  records=[(d,n) for d in documents for n in d['nodes'] if n['symbol']==symbol]
  result[symbol]=dict(offset_records=len(records),documents_with_offset=len({d['file'] for d,n in records}),
   numeric_assertion_records=sum(n['state']=='NUMERIC_ASSERTION_UNVERIFIED' for d,n in records),
   unavailable_records=sum(n['state']=='UNAVAILABLE' for d,n in records),
   invalid_records=sum(n['state']=='INVALID_OFFSET_ASSERTION' for d,n in records),
   distinct_numeric_assertions=sorted({n['offset_hours'] for d,n in records if n['state']=='NUMERIC_ASSERTION_UNVERIFIED'}),
   protocol_or_mapping_assertions=sum(n['role']=='protocol_or_mapping_assertion' for d,n in records),
   records_with_explicit_effective_fields=sum(bool(n['explicit_effective_fields']) for d,n in records),
   independent_clock_observations_verified=0,historical_mapping_verified=False,DST_policy_verified=False,
   verdict='HISTORICAL_MAPPING_UNRESOLVED')
 return result

def checks():
 n=dict(clock={'NAS100':dict(offset_hours=None,fresh_samples=0)})
 numeric=dict(last_poll_utc='2026-11-02T20:00:00Z',clock={'NAS100':dict(offset_hours=3,fresh_samples=10)})
 a=extract(n)[0];b=extract(numeric)[0]
 c={}
 c['null_not_UTC_or_policy_change']=a['state']=='UNAVAILABLE' and a['offset_hours'] is None and not a['historical_applicability_verified']
 c['bool_not_numeric_offset']=extract(dict(clock={'NAS100':dict(offset_hours=True)}))[0]['state']=='INVALID_OFFSET_ASSERTION'
 c['nonfinite_offset_rejected']=extract(dict(clock={'NAS100':dict(offset_hours=float('nan'))}))[0]['state']=='INVALID_OFFSET_ASSERTION'
 c['capture_not_effective_interval']=bool(b['context_time_fields']) and not b['explicit_effective_fields']
 c['explicit_interval_not_auto_approved']=not extract(dict(numeric,effective_from='2025-12-15',effective_to='2026-10-30'))[0]['historical_applicability_verified']
 c['mapping_not_measurement']=extract(dict(offset_hours={'NAS100':3}))[0]['role']=='protocol_or_mapping_assertion'
 c['account_and_price_content_excluded']=extract(dict(numeric,account=n,prices=[n]))==extract(numeric)
 d=[dict(file='a',sha256='same',nodes=[b]),dict(file='b',sha256='same',nodes=[a])]
 s=summarize(d)['NAS100']
 c['numeric_and_null_not_conflicting_DST']=s['distinct_numeric_assertions']==[3] and s['unavailable_records']==1 and not s['DST_policy_verified']
 assert all(c.values()),c
 return c

def discover(root):
 command=['rg','-l','--max-filesize','500K','"offset_hours"','outputs','work','-g','*.json',
  '-g','!outputs/ict_mentorship_2022_v1/**','-g','!work/ict*/**','-g','!**/.git/**',
  '-g','!**/site-packages/**','-g','!**/node_modules/**','-g','!**/data/**','-g','!**/quarantine/**',
  '-g','!**/publication_payload*','-g','!**/publication_history/**']
 p=subprocess.run(command,cwd=root,capture_output=True,text=True,check=True)
 return command,sorted({Path(p).as_posix() for p in p.stdout.splitlines()})

def render(data):
 rows=''.join('<tr><td>'+escape(s)+'</td><td>'+str(v['offset_records'])+'</td><td>'+str(v['numeric_assertion_records'])+'</td><td>'+str(v['unavailable_records'])+'</td><td>'+str(v['records_with_explicit_effective_fields'])+'</td><td>UNRESOLVED</td></tr>' for s,v in data['instruments'].items())
 refs=''.join('<li><a href="'+escape(r['url'])+'">'+escape(r['title'])+'</a>: '+escape(r['scope'])+'</li>' for r in REFERENCES)
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trade Dashboard</title><style>body{background:#0b1320;color:#e5edf8;font:16px/1.7 Segoe UI,sans-serif;max-width:1100px;margin:auto;padding:32px}section{background:#142133;border-radius:14px;padding:24px;margin:20px 0}a{color:#80b7ff}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #293b53}.scroll{overflow:auto}</style></head><body><h1>Trade Dashboard</h1><section><h2>Historical clock provenance</h2><p>DOCUMENTARY REVIEW ONLY - HISTORICAL MAPPING UNRESOLVED</p><p>'+escape(data['corpus_scope'])+'</p><div class="scroll"><table><tr><th>Instrument</th><th>Offset records</th><th>Numeric assertions</th><th>Unavailable</th><th>Effective-interval records</th><th>Mapping</th></tr>'+rows+'</table></div><p>A numeric saved offset is a claim at its documented context, not an independently verified historical regime. Protocol assumptions are separate from captured clock metadata. A null offset is unavailable, not UTC, a new broker timezone or a DST switch. Multiple files can repeat the same observation; document hashes do not prove independence.</p></section><section><h2>Evidence boundary</h2><p>The earlier clock-grid protocol concerned price alignment. This audit does not execute it or open price, bar, fill or database archives. It projects only named clock metadata. Source API documentation cannot alone certify this broker historical behavior; no automatic zero-hour or three-hour correction follows. Broker-origin historical interval/revision evidence, archive timestamp semantics and independently corroborated clock observations remain needed before a new model version. Missing metadata is not a mandate to restart observation.</p><p>No clock, risk, stop, cost, original benchmark or frozen cohort changed. Observation remains stopped by user decision. No new financial case, new quotes, calendar join, broker contact, MT5 connection or ICT comparison. Net, win rate and drawdown are NOT EVALUATED, not zero. Original modeled financial values remain unchanged.</p></section><section><h2>Primary documentation</h2><ul>'+refs+'</ul><p>Recorded '+escape(data['completed_utc'])+'.</p></section></body></html>'

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve()
 out=root/'outputs/atlas_research_pipeline_v1';folder=out/'feasibility/clock_provenance_v1'
 if folder.exists():raise FileExistsError('Preserve completed finite documentary review; no unchanged rerun')
 registry=json.loads((out/'experiment_registry.json').read_bytes().decode('utf-8'))['experiments'];assert len(registry)==79
 prior={r['experiment']+'/protocol.json':sha(root/r['experiment']/'protocol.json') for r in registry}
 nearest=['outputs/spx15_clock_grid_audit_v1/protocol.json','outputs/spx15_causality_audit_v1/protocol.json',
  'outputs/atlas_research_pipeline_v1/feasibility/contract_provenance_v1/protocol.json','outputs/atlas_research_pipeline_v1/designs/ibkr_metadata_intake_v1/protocol.json']
 protected=frozen_audit(root);command,paths=discover(root);identities={p:sha(root/p) for p in paths};synthetic=checks()
 folder.mkdir(parents=True);(folder/'source_snapshot.py').write_bytes(Path(__file__).read_bytes())
 protocol=dict(registered_utc=stamp(),purpose='Post-failure documentary inventory of saved offset assertions and validity evidence, not a blind strategy hypothesis or price alignment.',
  source_sha256=sha(Path(__file__)),corpus_protocol_sha256=prior,nearest_prior_artifacts={p:prior[p] for p in nearest},
  scope_difference='The preserved clock-grid protocol joins archived/reference prices; causality audit compares decision prefixes; contract provenance projects contract terms; metadata intake is a synthetic future receipt schema. This audit only projects saved clock validity metadata. No prior module is rerun.',
  prior_review_limit='All79 protocol identities inventoried; nearest four purpose/method records reviewed. No claim of exhaustive semantic review of every possible file or new alpha mechanism.',
  discovery_command=command,input_identities=identities,corpus_files=len(paths),
  corpus_scope='Bounded to rg-visible JSON files at most 500K under outputs/work containing the exact offset_hours key, with dependency, data/quarantine, publication-payload/history and ICT folders excluded. Ignored, larger or differently named evidence and broker documents elsewhere are not claimed searched.',
  method='Project named offset assertions, context timestamps, role and explicit effective fields; null remains unavailable. Do not infer historical validity, independent observations, broker DST policy or an archive correction.',
  references=REFERENCES,synthetic_checks_passed=len(synthetic),frozen_financial_sources=protected,financial_cases_started=0,financial_observations_scored=0,broker_connections=0,ict_used=False)
 write(folder/'protocol.json',protocol);write(folder/'synthetic_checks.json',synthetic)
 try:
  documents=[]
  for name in paths:
   assert sha(root/name)==identities[name]
   documents.append(dict(file=name,sha256=identities[name],nodes=extract(json.loads((root/name).read_bytes().decode('utf-8')))))
  summary=summarize(documents);duplicates=Counter(d['sha256'] for d in documents)
  result=dict(completed_utc=stamp(),status='DOCUMENTARY_CLOCK_AUDIT_COMPLETE_MAPPING_UNRESOLVED',corpus_scope=protocol['corpus_scope'],
   matching_documents=len(documents),instruments=summary,duplicate_content_groups=sum(v>1 for v in duplicates.values()),
   synthetic_checks_passed=len(synthetic),historical_clock_mapping_verified=False,broker_DST_policy_verified=False,
   reference_price_alignment_performed=False,financial_cases_started=0,financial_observations_scored=0,financial_PASS=False,
   profit_delta=None,net=None,win_rate=None,drawdown=None,references=REFERENCES,observation_restarted=False,ict_used=False)
  write(folder/'private_document_projection.json',documents);write(folder/'results.json',result);write(folder/'public_summary.json',result)
  (folder/'report.html').write_text(render(result),encoding='utf-8')
  assert all(sha(root/name)==h for name,h in identities.items()) and all(sha(root/name)==h for name,h in prior.items())
  assert frozen_audit(root)==protected
  write(folder/'completed.json',dict(completed_utc=stamp(),documentary_review_completed=True,financial_PASS=False,financial_cases=0,
   protocol_sha256=sha(folder/'protocol.json'),results_sha256=sha(folder/'results.json'),source_sha256=sha(Path(__file__)),
   historical_mapping_resolved=False,input_identities_unchanged=True,frozen_financial_identities_unchanged=True))
  print(json.dumps(dict(status=result['status'],matching_documents=len(documents),instruments=summary,synthetic_checks=len(synthetic),financial_cases=0),ensure_ascii=True))
 except Exception as exc:
  write(folder/'failure.json',dict(failed_utc=stamp(),error=repr(exc),financial_cases_started=0,preserved=True));raise

if __name__=='__main__':main()
