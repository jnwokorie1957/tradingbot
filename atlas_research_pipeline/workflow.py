"""Finite scheduled entrypoint: status, identities and new artifacts only.

Financial discovery is a separately registered finite command. This orchestrator
does not silently create hypotheses, rerun finished cases or unseal fresh data.
"""
import argparse,json,os,subprocess,hashlib
from pathlib import Path
from datetime import datetime,timezone
from atlas_exit_research.data import write,sha,stamp


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--trigger',choices=['manual','heartbeat'],default='manual');a=p.parse_args();root=a.root.resolve();out=root/'outputs/atlas_research_pipeline_v1';state=root/'work/tradingbot/local-results/atlas-research-pipeline';state.mkdir(parents=True,exist_ok=True);lock=state/'workflow.lock.json'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:print(json.dumps(dict(status='blocked_unverified_existing_workflow_lock',action='Inspect actual process creation identity before any recovery;do not remove/restart blindly')));return
    os.write(fd,json.dumps(dict(pid=os.getpid(),started_utc=stamp(),trigger=a.trigger)).encode());os.close(fd)
    try:
        cycle=out/'cycles/001';progress=json.loads((cycle/'progress.json').read_text())if(cycle/'progress.json').exists()else{'status':'not_started'};freeze=root/'work/tradingbot/local-results/atlas-forward-v2/freeze.json';frozen=json.loads(freeze.read_text());checks={n:sha(root/'work/tradingbot'/('trading_pipeline'if n=='engine_v4.py'else'research_monitor')/n)==v for n,v in frozen['source_hashes'].items()};assert all(checks.values()),'Frozen financial source changed'
        report=dict(at_utc=stamp(),trigger=a.trigger,orchestrator_pid=os.getpid(),cycle=progress,original_financial_sources_match=True,paper_only=True,broker_execution_calls=0,financial_job_started=False,prospective_financial_results_available=False,actions=[])
        if progress.get('status')=='not_started':report['next_action']='Execute the already registered cycle once;do not change rules or create duplicate workers'
        elif progress.get('status')=='running':report['next_action']='Inspect actual worker PID and creation identity;wait if genuine activeworker'
        elif progress.get('status')=='failed':report['next_action']='Preserve failure;diagnose before any exact-checkpoint recovery'
        else:report['next_action']='No completed financial rerun. Review new primary literature for distinct bounded hypotheses,unseen-data route,and prospective evaluator readiness. Register rules/source/data identities before a newcycle;keep cumulative trial history.'
        delay=root/'outputs/atlas_pair_execution_delay_v1';prospective=root/'outputs/atlas_pair_prospective_v1'
        second=out/'cycles/002';bottleneck=root/'outputs/atlas_pair_bottleneck_audit_v1'
        report['cycle002']=json.loads((second/'progress.json').read_text())if(second/'progress.json').exists()else None
        third=out/'cycles/003'
        report['cycle003']=json.loads((third/'progress.json').read_text())if(third/'progress.json').exists()else None
        precision=out/'feasibility/quote_precision_v1';spread=out/'feasibility/spread_wait_v1'
        if(precision/'completed.json').exists():
            report['quote_precision']=json.loads((precision/'completed.json').read_text())
            report['next_action']='Preserve completed cases and failed spread-feasibility probe. Reconcile historical SPX quote precision/tick-value applicability before new execution-sensitive SPX scoring; continue bounded nonfinancial provenance or distinct research design. Do not infer replacement specs, refit the failed probe, restart observation or use ICT.'
        report['execution_delay']=json.loads((delay/'completed.json').read_text())if(delay/'completed.json').exists()else None
        if(prospective/'protocol.json').exists():
            command=[os.sys.executable,'-m','atlas_research_pipeline.pair_forward','--root',str(root)]
            r=subprocess.run(command+['--status'],cwd=root/'work/tradingbot',capture_output=True,text=True)
            if r.returncode:
                report['pair_prospective']=dict(status='identity_or_availability_failure_requires_review',exit_code=r.returncode,error=r.stderr+r.stdout);report['actions'].append('Preserved prospective failure;no financial replay or automatic recovery')
            else:
                report['pair_prospective']=json.loads(r.stdout);phase=json.loads((prospective/'progress.json').read_text())
                if report['pair_prospective']['new_complete_sessions']>=5 and phase['status']not in ['evaluation_failed_requires_review','evidence_failure_requires_review']:
                    report['financial_job_started']=True;r=subprocess.run(command,cwd=root/'work/tradingbot',capture_output=True,text=True);report['finite_evaluation']=dict(started_and_completed=True,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr);report['prospective_financial_results_available']=r.returncode==0
                    report['actions'].append('Ran fixed prospective cohort once after five new covered sessions'if r.returncode==0 else'Prospective failure preserved;requires review,not automatic restart')
        artifact_files=[p for p in [delay/'completed.json',prospective/'protocol.json',prospective/'progress.json',second/'progress.json',second/'completed.json',third/'progress.json',third/'completed.json',bottleneck/'completed.json',spread/'failure.json',precision/'completed.json']if p.exists()];surface=dict(files={str(p.relative_to(root)):sha(p)for p in artifact_files},coverage=report.get('pair_prospective',{}).get('coverage'),health={k:report.get('pair_prospective',{}).get('collector_health',{}).get(k)for k in ['matches_frozen_creation','fresh_status']});report['surface_identity']=hashlib.sha256(json.dumps(surface,sort_keys=True).encode()).hexdigest();previous=json.loads((out/'workflow_status.json').read_text())if(out/'workflow_status.json').exists()else{}
        # Financial results are not re-executed to generate activity.
        if not(out/'dashboard_data.json').exists()or previous.get('surface_identity')!=report['surface_identity']:
            subprocess.run([os.sys.executable,'-m','atlas_research_pipeline.ledger','--root',str(root)],cwd=root/'work/tradingbot',check=True,capture_output=True);report['actions'].append('Built missing aggregate ledger')
        path=out/'workflow_runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ.json');write(path,report);write(out/'workflow_status.json',report);print(json.dumps(report))
        if previous.get('surface_identity')!=report['surface_identity']:subprocess.run([os.sys.executable,'-m','atlas_research_pipeline.dashboard','--root',str(root)],cwd=root/'work/tradingbot',check=True,capture_output=True)
    finally:lock.unlink(missing_ok=True)


if __name__=='__main__':main()
