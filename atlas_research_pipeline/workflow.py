"""Finite scheduled entrypoint: status, identities and new artifacts only.

Financial discovery is a separately registered finite command. This orchestrator
does not silently create hypotheses, rerun finished cases or unseal fresh data.
"""
import argparse,json,os,subprocess
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
        # Financial results are not re-executed to generate activity.
        if not(out/'dashboard_data.json').exists():
            subprocess.run([os.sys.executable,'-m','atlas_research_pipeline.ledger','--root',str(root)],cwd=root/'work/tradingbot',check=True,capture_output=True);report['actions'].append('Built missing aggregate ledger')
        path=out/'workflow_runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ.json');write(path,report);write(out/'workflow_status.json',report);print(json.dumps(report))
    finally:lock.unlink(missing_ok=True)


if __name__=='__main__':main()
