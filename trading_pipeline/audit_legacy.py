"""Admission-only audit of the existing pre-protection development snapshot.

No OHLC calculations, strategy scoring or fills. Never opens observer ledgers.
"""
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from .journal import Journal,digest

EXPECTED='41d61b113938909b0010941a349d98ec81e5887087148c72f7cc23790a5290b6'
def audit(source,output):
 source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=False)
 journal=Journal(output/'journal.sqlite');experiment='legacy-september-admission-v1'
 plan={'type':'admission_only','source_sha256':EXPECTED,'strategy_evaluation':False,'allowed_market_month':'2026-09','protected_observer_files_accessed':False}
 journal.append(experiment,'registered',plan);journal.claim(experiment,digest(plan))
 try:
  if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('unexpected_source_hash')
  data=json.loads(source.read_text());counts={}
  for root in ['1OZ','NES','SIC']:
   item=data['contracts'][root]
   september=sum(datetime.fromtimestamp(int(b['time']),timezone.utc).strftime('%Y-%m')=='2026-09' for b in item['bars'])
   counts[root]={'raw_september_timestamp_rows':september,'historical_request_end_received':item.get('end_received') is True}
  report={'status':'blocked_for_performance_backtest','source_hash_verified':True,'source_sha256':EXPECTED,'data_kind':'actual_historical_bars_not_synthetic','checks':counts,'blockers':['No verified historical bid/ask execution path','Effective-dated account costs, margins and eligibility unavailable','Bar timestamp/availability semantics still require independent verification','September is reused development data, not unseen out-of-sample validation'],'market_backtests_completed':0,'paper_orders':0,'fills_computed':0,'win_rate':None,'profit_factor':None,'expectancy':None,'qualified_for_paper':False,'holdout_accessed':False,'strategy_scoring_performed':False}
 except Exception as exc:report={'status':'failed_admission','error_class':type(exc).__name__,'qualified_for_paper':False}
 journal.append(experiment,'finished',report);report['journal_head']=journal.verify();journal.close()
 (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 return report
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True);a=parser.parse_args()
 print(json.dumps(audit(a.source,a.output),indent=2))
