"""Fixed closing strategy, training gate, forward windows; no holdout execution."""
import copy,json
from collections import Counter
from pathlib import Path
from .closing_admission import admit,administrative,partition,fold_events,RISK,SCENARIOS
from .closing_execution import ClosingEngine
from .engine_v4 import Ledger,Policy,utc
from .journal import digest,Journal
from .runner import code_identity
from .metrics import summarize,assess

def register(journal,experiment,plan,manifest,contracts):
    frozen=copy.deepcopy(plan)
    frozen.update(version='closing-walkforward-1.0.2',code_identity=code_identity(),manifest_hash=digest(manifest),contracts_hash=digest(contracts),final_holdout_access='locked')
    journal.append(experiment,'registered',dict(plan=frozen,plan_hash=digest(frozen)))
    return frozen

def run(journal,experiment,plan,manifest,contracts,base,output):
    journal.claim(experiment,digest(plan))
    report=dict(experiment=experiment,plan_hash=digest(plan),synthetic=manifest.get('synthetic') is True,status='started',trials=[],qualified_for_paper=False,broker_execution_enabled=False,loop_enabled=False,profit_claim=False,final_holdout='untouched_locked')
    output=Path(output)
    try:
        row=journal.db.execute("SELECT payload FROM records WHERE experiment=? AND kind='registered' ORDER BY seq LIMIT 1",(experiment,)).fetchone()
        if not row or json.loads(row[0])['plan_hash']!=digest(plan):raise ValueError('plan_not_registered')
        if (plan.get('version')!='closing-walkforward-1.0.2' or plan['code_identity']!=code_identity()
            or plan['manifest_hash']!=digest(manifest) or plan['contracts_hash']!=digest(contracts)
            or plan.get('final_holdout_access')!='locked'):raise ValueError('registered_identity_changed')
        admit(manifest,contracts,plan)
        train_spec=manifest['files']['train']
        journal.reserve_training(experiment,manifest,contracts)
        admin=administrative(base,manifest,contracts)
        training,train_sessions,report['training_quality']=partition(base,manifest,'train',contracts)
        output.mkdir(parents=True,exist_ok=False)
        def trial(rows,sessions,window,phase,index,scenario):
            identity=dict(strategy=plan['strategy'],phase=phase,fold=index,window=window,scenario=scenario)
            trial_id=digest(identity)[:20];journal.append(experiment,'trial_started',dict(trial_id=trial_id,**identity))
            ledger=None
            try:
                events,selected=fold_events(rows,sessions,admin,window)
                journal.append(experiment,'trial_inputs',dict(trial_id=trial_id,event_hash=digest(events),calendar_hash=digest(selected)))
                cs=copy.deepcopy(contracts)
                for c in cs.values():c['fee_per_side']*=scenario['fee_factor'];c['daily_carry_fee']*=scenario['fee_factor']
                ledger=Ledger(str(output/(trial_id+'.sqlite')))
                engine=ClosingEngine(ledger,experiment+'-'+trial_id,cs,selected,Policy(**plan['risk'],slippage_ticks=scenario['slippage_ticks']),report['synthetic'])
                trades=[];equity=[500.];entries={};skips=Counter()
                for e in events:
                    result=engine.apply(e);equity.append(engine.state['equity'])
                    if result['status']=='entry':entries[e['contract']]=e['available_at']
                    if result['status']=='exit':trades.append(dict(entry_at=entries.pop(e['contract']),exit_at=e['available_at'],net_pnl=result['net_pnl'],reason=result['reason'],cost_evidence_valid=result['cost_evidence_valid'],quantity=1))
                    if result['status']=='skip':skips[result['reason']]+=1
                clean=not engine.state['positions'] and not engine.state['invalid_cost_fills'];metrics=summarize(trades,equity,report['synthetic'])
                result=dict(trial_id=trial_id,**identity,status='completed_research' if clean and trades else 'inconclusive',trades=trades,metrics=metrics,skip_counts=dict(skips),unresolved_positions=len(engine.state['positions']),invalid_cost_fills=engine.state['invalid_cost_fills'],assessment=assess(metrics,synthetic=report['synthetic'],clean=clean))
            except Exception as exc:result=dict(trial_id=trial_id,**identity,status='failed',reason=str(exc),error_class=type(exc).__name__)
            finally:
                if ledger:ledger.close()
            journal.append(experiment,'trial_finished',result);report['trials'].append(result);return result
        t=trial(training,train_sessions,train_spec,'training',0,plan['scenarios'][0])
        if t['status']!='completed_research' or t['metrics']['expectancy']<=0:
            report['status']='rejected_training';return report
        journal.append(experiment,'selection_frozen',dict(strategy=plan['strategy'],selection_data='training_only',parameter_search=False))
        journal.consume_validation(experiment,manifest,contracts)
        validation,sessions,report['validation_quality']=partition(base,manifest,'validation',contracts)
        if {e['id'] for e in training}&{e['id'] for e in validation}:raise ValueError('cross_partition_duplicate_id')
        if set(train_sessions)&set(sessions):raise ValueError('cross_partition_session_identity')
        for sid,s in sessions.items():
            if sum(utc(w['start'])<=utc(s['open'])<utc(w['end']) for w in plan['validation_windows'])!=1:raise ValueError('validation_session_outside_folds')
        for index,window in enumerate(plan['validation_windows']):
            for scenario in plan['scenarios']:trial(validation,sessions,window,'validation',index,scenario)
        report['status']='completed_research_not_qualified'
        results=report['trials'][1:]
        report['all_validation_windows_positive']=all(t['status']=='completed_research' and t['metrics']['expectancy']>0 for t in results)
        report['statistical_screen_pass']=report['all_validation_windows_positive'] and all(t['assessment']['statistical_screen_pass'] for t in results)
    except Exception as exc:report.update(status='blocked_or_failed',reason=str(exc),error_class=type(exc).__name__)
    finally:
        journal.append(experiment,'finished',report);report['journal_head']=journal.verify()
        # Journal is authoritative, including failures before output creation.
        if output.is_dir():
            with (output/'report.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False)
    return report
