"""One-shot synthetic adapter verification; real-data admission is not integrated."""
import argparse,json
from pathlib import Path
from .closing_execution import ClosingEngine
from .engine_v4 import Ledger,digest
from .closing_fixtures import create

def claim_run(ledger,run_id,metadata):
    """Commit immutable identity and started trial together before any admission.

    No automatic reclaim: an interrupted claim is consumed and requires a new ID.
    Legacy run/trial records also prevent reuse when upgrading an existing ledger.
    """
    if not isinstance(run_id,str) or not run_id.strip():raise ValueError('nonempty_run_id_required')
    db=ledger.db
    if db.in_transaction:raise ValueError('claim_requires_idle_ledger_transaction')
    db.executescript("""
        CREATE TABLE IF NOT EXISTS closing_run_claims(
            run_id TEXT PRIMARY KEY NOT NULL,input_hash TEXT NOT NULL,
            metadata TEXT NOT NULL,trial_id INTEGER UNIQUE NOT NULL);
        CREATE TRIGGER IF NOT EXISTS closing_claim_no_update BEFORE UPDATE ON closing_run_claims
            BEGIN SELECT RAISE(ABORT,'immutable closing claim'); END;
        CREATE TRIGGER IF NOT EXISTS closing_claim_no_delete BEFORE DELETE ON closing_run_claims
            BEGIN SELECT RAISE(ABORT,'immutable closing claim'); END;
    """)
    with db:
        db.execute('BEGIN IMMEDIATE')
        if (db.execute('SELECT 1 FROM closing_run_claims WHERE run_id=?',(run_id,)).fetchone()
            or db.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone()
            or any(json.loads(row[0]).get('run_id')==run_id for row in db.execute('SELECT metadata FROM trials'))):
            raise ValueError('run_id_already_used')
        encoded=json.dumps(metadata,sort_keys=True,allow_nan=False)
        trial=db.execute('INSERT INTO trials(metadata,result) VALUES(?,NULL)',(encoded,)).lastrowid
        db.execute('INSERT INTO closing_run_claims VALUES(?,?,?,?)',(run_id,metadata['input_hash'],encoded,trial))
    return trial

def run_once(ledger,run_id,bundle):
    metadata=dict(run_id=run_id,input_hash=digest(bundle),strategy='closing_half_hour_continuation',strategy_version='1.0.0',runner_version='2.0.0',synthetic=bundle.get('synthetic') is True)
    trial=claim_run(ledger,run_id,metadata)
    result=dict(**metadata,status='started',qualified_for_paper=False,broker_execution_enabled=False,loop_enabled=False,profit_claim=False,observations=[])
    try:
        if bundle.get('synthetic') is not True:raise ValueError('real_data_admission_not_integrated')
        engine=ClosingEngine(ledger,run_id,bundle['contracts'],bundle['sessions'],synthetic=True)
        for event in bundle['events']:
            result['observations'].append(dict(event_id=event['id'],available_at=event['available_at'],result=engine.apply(event)))
        result['engine']=engine.report()
        result['status']='inconclusive' if engine.state['positions'] or engine.state['invalid_cost_fills'] else 'completed_synthetic_verification'
    except Exception as exc:
        result.update(status='failed',error_class=type(exc).__name__,reason=str(exc))
    with ledger.db:ledger.db.execute('UPDATE trials SET result=? WHERE id=?',(json.dumps(result,allow_nan=False),trial))
    return result

def main():
    parser=argparse.ArgumentParser(description='One-shot synthetic closing strategy verification; no broker transport')
    parser.add_argument('--output',required=True);args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    bundle=create();(output/'synthetic-input.json').write_text(json.dumps(bundle,indent=2))
    ledger=Ledger(str(output/'ledger.sqlite'))
    try:result=run_once(ledger,'closing-synthetic-v1',bundle)
    finally:ledger.close()
    (output/'report.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(dict(status=result['status'],synthetic=True,qualified_for_paper=False,broker_execution_enabled=False)))

if __name__=='__main__':main()
