"""One-shot anchored chronological validation. Final holdout has no execution path."""
import copy,json,hashlib,math
from pathlib import Path
from collections import Counter
from .engine_v4 import Engine,Hypothesis,Policy,Ledger,utc
from .dataset import validate_manifest,load_partition,AdmissionError
from .journal import digest
from .metrics import summarize,assess

ENGINE_SHA='b01fc9091c59e42eaddcc555c6433d14c3e775413fb9e0b40ad107568535c9e2'
def fold_rows(events,window):
 start,end=utc(window["start"]),utc(window["end"])
 # Replay administrative announcements only; engine applies effective dates as-of.
 return [r for r in events if (r["kind"]=="margin_update" and utc(r["available_at"])<start) or start<=utc(r["available_at"])<end]

def code_identity():
 root=Path(__file__).parent
 return digest({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))})

class ResearchEngine(Engine):
 """Stricter continuity and one global position for nonoverlapping-trade research."""
 def _bar(self,e,now,c):
  prior=self.state['bars'].get(e['contract'],[])
  if prior and utc(e['start'])!=utc(prior[-1]['end']):
   self.state['bars'][e['contract']]=[];self.state['pending'].pop(e['contract'],None)
  return super()._bar(e,now,c)
 def _quote(self,e,now,c):
  if self.state['positions'] and e['contract'] not in self.state['positions']:
   self.state['pending'].pop(e['contract'],None)
   return dict(status='skip',reason='one_global_position_research_policy')
  return super()._quote(e,now,c)

def validate_plan(plan,manifest,contracts):
 if plan.get('version')!='2.0.0' or plan.get('project')!='tradingbot':raise ValueError('wrong_pipeline_scope')
 if plan.get('code_identity')!=code_identity():raise ValueError('source_changed_since_registration')
 if plan.get('manifest_hash')!=digest(manifest) or plan.get('contracts_hash')!=digest(contracts):raise ValueError('registered_input_changed')
 if plan.get('final_holdout_access')!='locked':raise ValueError('final_holdout_locked')
 if plan.get('risk')!={'budget':500,'trade_risk':.005,'portfolio_risk':.01,'daily_pause':.02,'drawdown_pause':.10}:raise ValueError('risk_policy_change_prohibited')
 if not plan.get('hypotheses') or len(plan['hypotheses'])>10:raise ValueError('one_to_ten_preregistered_hypotheses')
 ids=[]
 for h in plan['hypotheses']:
  Hypothesis(**h);ids.append(digest(h))
 if len(ids)!=len(set(ids)):raise ValueError('duplicate_hypothesis')
 if plan.get('scenarios')!=[{'id':'baseline','fee_factor':1,'slippage_ticks':1},{'id':'stress','fee_factor':1.5,'slippage_ticks':2}]:raise ValueError('fixed_cost_scenarios_required')
 a,b=manifest['files']['train'],manifest['files']['validation']
 if not utc(a['start'])<utc(a['end'])<=utc(b['start'])<utc(b['end'])<=utc(manifest['final_holdout']['start']):raise ValueError('chronological_partition_overlap')
 if (utc(b['start'])-utc(a['end'])).total_seconds()<3600 or (utc(manifest['final_holdout']['start'])-utc(b['end'])).total_seconds()<3600:raise ValueError('one_hour_holding_period_embargo_required')
 previous=utc(b['start'])
 for index,fold in enumerate(plan['validation_windows']):
  start,end=utc(fold['start']),utc(fold['end'])
  if start<previous or not start<end or end>utc(b['end']):raise ValueError('overlapping_validation_windows')
  if index and (start-previous).total_seconds()<3600:raise ValueError('validation_window_embargo_required')
  previous=end
 if len(plan['validation_windows'])<2:raise ValueError('at_least_two_forward_validation_windows_required')
 for c in contracts.values():
  if c.get('root')=='QNDX':raise ValueError('excluded_contract')
  if not all(c.get(k) is True for k in ('spec_verified','permission_verified','costs_verified','data_verified')):raise AdmissionError('unverified_contract_evidence')
  for key in ('tick','multiplier','initial_margin','maintenance_margin','fee_per_side','daily_carry_fee'):
   v=c.get(key)
   if type(v) not in (int,float) or not math.isfinite(v) or v<0 or key in ('tick','multiplier','initial_margin','maintenance_margin') and v==0:raise AdmissionError('invalid_cost_or_contract_metadata')

def register(journal,experiment,plan,manifest,contracts):
 frozen=copy.deepcopy(plan)
 frozen.update(version='2.0.0',project='tradingbot',code_identity=code_identity(),manifest_hash=digest(manifest),contracts_hash=digest(contracts),final_holdout_access='locked')
 # Registration intentionally records deficient data plans too; admission logs failures.
 journal.append(experiment,'registered',{'plan':frozen,'plan_hash':digest(frozen)})
 return frozen

def run(journal,experiment,plan,manifest,contracts,dataset_base,output_dir):
 journal.claim(experiment,digest(plan))
 report=dict(experiment=experiment,plan_hash=digest(plan),code_identity=code_identity(),synthetic=manifest.get('synthetic') is True,trials=[],status='started',qualified_for_paper=False,broker_execution_enabled=False,final_holdout='untouched_locked',market_performance_claim=False)
 output=Path(output_dir)
 try:
  registered=journal.db.execute("SELECT payload FROM records WHERE experiment=? AND kind='registered' ORDER BY seq LIMIT 1",(experiment,)).fetchone()
  if not registered or json.loads(registered[0])['plan_hash']!=digest(plan):raise ValueError('plan_not_registered')
  validate_manifest(manifest,report['synthetic']);validate_plan(plan,manifest,contracts)
  if hashlib.sha256(Path(__file__).with_name('engine_v3.py').read_bytes()).hexdigest()!=ENGINE_SHA:raise ValueError('preserved_engine_changed')
  output.mkdir(parents=True,exist_ok=True)
  training,tq=load_partition(Path(dataset_base),manifest,'train',contracts);report['training_quality']=tq
  def trial(rows,h,phase,scenario,fold):
   identity={'hypothesis':h,'phase':phase,'scenario':scenario,'fold':fold};trial_id=digest(identity)[:20]
   journal.append(experiment,'trial_started',dict(trial_id=trial_id,**identity,data_hash=digest(rows)))
   ledger=None;result=None
   try:
    cs=copy.deepcopy(contracts)
    for c in cs.values():c['fee_per_side']*=scenario['fee_factor'];c['daily_carry_fee']*=scenario['fee_factor']
    policy=Policy(**plan['risk'],slippage_ticks=scenario['slippage_ticks'],max_bar_gap_seconds=1)
    ledger=Ledger(str(output/(trial_id+'.sqlite')))
    engine=ResearchEngine(ledger,experiment+'-'+trial_id,cs,policy,Hypothesis(**h),report['synthetic'])
    fills=[];equity=[500.];skips=Counter();last_entry=None
    for event in rows:
     out=engine.apply(event);equity.append(engine.state['equity'])
     if out['status']=='entry':last_entry=event['available_at']
     if out['status']=='exit':
      fills.append(dict(entry_at=last_entry,exit_at=event['available_at'],net_pnl=out['net_pnl'],reason=out['reason'],cost_evidence_valid=out['cost_evidence_valid'],quantity=1));last_entry=None
     if out['status']=='skip':skips[out['reason']]+=1
    clean=not engine.state['positions'] and not engine.state['invalid_cost_fills'];m=summarize(fills,equity,report['synthetic'])
    result=dict(trial_id=trial_id,**identity,status='completed_exploratory' if clean and fills else 'inconclusive',unresolved_positions=len(engine.state['positions']),invalid_cost_fills=engine.state['invalid_cost_fills'],metrics=m,skip_counts=dict(skips),trades=fills,assessment=assess(m,synthetic=report['synthetic'],clean=clean))
   except Exception as exc:result=dict(trial_id=trial_id,**identity,status='failed',error_class=type(exc).__name__)
   finally:
    if ledger:ledger.close()
   journal.append(experiment,'trial_finished',result);report['trials'].append(result)
   return result
  train_results=[]
  for h in plan['hypotheses']:train_results.append(trial(training,h,'training',plan['scenarios'][0],0))
  candidates=[t for t in train_results if t['status']=='completed_exploratory' and t['metrics']['expectancy']>0]
  if not candidates:
   report['status']='rejected_training_no_eligible_candidate'
  else:
   # Only training results select a spec; tie break is deterministic specification hash.
   winner=sorted(candidates,key=lambda t:(-t['metrics']['net_pnl'],t['metrics']['maximum_drawdown_fraction'],digest(t['hypothesis'])))[0]['hypothesis']
   journal.append(experiment,'selection_frozen',{'hypothesis':winner,'selection_data':'training_only'})
   report['selected_hypothesis']=winner
   journal.consume_validation(experiment,manifest,contracts)
   validation,vq=load_partition(Path(dataset_base),manifest,'validation',contracts);report['validation_quality']=vq
   if {r['id'] for r in validation}&{r['id'] for r in training}:raise AdmissionError('cross_partition_duplicate_id')
   for i,window in enumerate(plan['validation_windows']):
    rows=fold_rows(training+validation,window)
    for scenario in plan['scenarios']:trial(rows,winner,'validation',scenario,i)
   validation_results=[t for t in report['trials'] if t['phase']=='validation']
   report['status']='completed_research_not_qualified'
   report['all_validation_windows_positive']=all(t['status']=='completed_exploratory' and t['metrics']['expectancy']>0 for t in validation_results)
   report['statistical_screen_pass']=report['all_validation_windows_positive'] and all(t['assessment']['statistical_screen_pass'] for t in validation_results)
 except Exception as exc:
  report.update(status='blocked_or_failed',error_class=type(exc).__name__,reason=str(exc) if isinstance(exc,(AdmissionError,ValueError)) else 'execution_failure')
 finally:
  journal.append(experiment,'finished',report)
  report['journal_head']=journal.verify()
  output.mkdir(parents=True,exist_ok=True)
  # Repeated experiment ID is blocked by claim; never overwrite a previous report.
  with (output/'report.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False)
 return report
