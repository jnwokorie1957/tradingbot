"""Chronological research harness; holdout rows are never evaluated here."""
import json
import uuid
from datetime import datetime,timezone
from dataclasses import asdict
from simulator import Engine, Hypothesis, Policy, digest, utc


def preregister(ledger, experiment_id, dataset_id, contracts, hypotheses, train_size,
                validation_size, holdout_start, policy=Policy(), synthetic=False):
    """Immutable identity and plan; real holdout must start after registration.

    External dataset identity/provenance still requires review. This cannot prove
    that a caller has never inspected data outside this ledger.
    """
    if not experiment_id or not dataset_id or train_size<1 or validation_size<1 or not hypotheses:
        raise ValueError('valid experiment and dataset identities required')
    cutoff=utc(holdout_start).isoformat()
    plan=dict(dataset_id=dataset_id,contracts_hash=digest(contracts),hypotheses=[asdict(h) for h in hypotheses],
              train_size=train_size,validation_size=validation_size,holdout_start=cutoff,
              policy=asdict(policy),synthetic=synthetic)
    encoded=json.dumps(plan,sort_keys=True,allow_nan=False)
    ledger.db.executescript('''
        CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, registered_at TEXT, plan TEXT);
        CREATE TABLE IF NOT EXISTS dataset_holdouts(id TEXT PRIMARY KEY, cutoff TEXT);
        CREATE TABLE IF NOT EXISTS experiment_uses(id TEXT PRIMARY KEY, development_hash TEXT, started_at TEXT);
        CREATE TRIGGER IF NOT EXISTS no_experiment_update BEFORE UPDATE ON experiments BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS no_experiment_delete BEFORE DELETE ON experiments BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS no_holdout_update BEFORE UPDATE ON dataset_holdouts BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS no_holdout_delete BEFORE DELETE ON dataset_holdouts BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS no_use_update BEFORE UPDATE ON experiment_uses BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS no_use_delete BEFORE DELETE ON experiment_uses BEGIN SELECT RAISE(ABORT,'immutable'); END;
    ''')
    now=datetime.now(timezone.utc)
    existing=ledger.db.execute('SELECT plan FROM experiments WHERE id=?',(experiment_id,)).fetchone()
    if existing:
        if existing[0]!=encoded: raise ValueError('preregistered plan is immutable')
        return experiment_id
    if not synthetic and utc(cutoff)<=now:
        raise ValueError('real holdout must be future at registration')
    with ledger.db:
        old=ledger.db.execute('SELECT cutoff FROM dataset_holdouts WHERE id=?',(dataset_id,)).fetchone()
        if old and old[0]!=cutoff: raise ValueError('dataset holdout identity cannot change')
        ledger.db.execute('INSERT OR IGNORE INTO dataset_holdouts VALUES(?,?)',(dataset_id,cutoff))
        ledger.db.execute('INSERT INTO experiments VALUES(?,?,?)',(experiment_id,now.isoformat(),encoded))
    return experiment_id


def walk_forward(ledger, contracts, events, hypotheses, train_size, validation_size,
                 holdout_start, policy=Policy(), synthetic=False, experiment_id=None):
    """Expanding training, disjoint validation. Select only on training net equity.

    Boundaries are observation timestamps, never shuffled rows. Open positions at
    a boundary invalidate a trial instead of inventing a closing fill. Every
    attempted trial is written before evaluation; exceptions and failures remain.
    The supplied holdout boundary must be preregistered before data exploration.
    """
    cutoff = utc(holdout_start)
    if train_size < 1 or validation_size < 1 or not hypotheses:
        raise ValueError('positive folds and hypotheses required')
    if not experiment_id:
        raise ValueError('durable preregistration required')
    try:
        registration=ledger.db.execute('SELECT plan FROM experiments WHERE id=?',(experiment_id,)).fetchone()
    except Exception as exc:
        raise ValueError('durable preregistration required') from exc
    if not registration: raise ValueError('unknown experiment registration')
    plan=json.loads(registration[0])
    expected=dict(plan,contracts_hash=digest(contracts),hypotheses=[asdict(h) for h in hypotheses],
                  train_size=train_size,validation_size=validation_size,holdout_start=cutoff.isoformat(),
                  policy=asdict(policy),synthetic=synthetic)
    if plan!=expected: raise ValueError('evaluation differs from preregistered plan')
    development = [e for e in events if utc(e['available_at']) < cutoff]
    times = sorted({utc(e['available_at']) for e in development})
    ids=[e['id'] for e in development]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate event identity in development data')
    if [utc(e['available_at']) for e in development] != sorted(utc(e['available_at']) for e in development):
        raise ValueError('chronological input required')
    campaign = experiment_id
    with ledger.db:
        if ledger.db.execute('SELECT 1 FROM experiment_uses WHERE id=?',(experiment_id,)).fetchone():
            raise ValueError('experiment already consumed; retain prior trial outcomes')
        ledger.db.execute('INSERT INTO experiment_uses VALUES(?,?,?)',
                          (experiment_id,digest(development),datetime.now(timezone.utc).isoformat()))
    results = []
    validation_ids=set()

    def trial(rows, hypothesis, phase, fold):
        metadata = dict(campaign=campaign,phase=phase,fold=fold,hypothesis=asdict(hypothesis),
                        policy=asdict(policy),data_hash=digest(rows),synthetic=synthetic,
                        holdout_start=holdout_start)
        with ledger.db:
            trial_id = ledger.db.execute('INSERT INTO trials(metadata,result) VALUES(?,NULL)', (json.dumps(metadata),)).lastrowid
        try:
            engine = Engine(ledger,f'{campaign}-{trial_id}',contracts,policy,hypothesis,synthetic)
            for row in rows: engine.apply(row)
            result = engine.report()
            result['status'] = 'inconclusive' if result['unresolved_positions'] or engine.state['trades'] == 0 else 'completed_exploratory'
        except Exception as exc:
            result = dict(status='failed',error=f'{type(exc).__name__}: {exc}')
        with ledger.db:
            ledger.db.execute('UPDATE trials SET result=? WHERE id=? AND result IS NULL', (json.dumps(result),trial_id))
        results.append(dict(trial_id=trial_id,metadata=metadata,result=result))
        return result

    for end in range(train_size, len(times)-validation_size+1, validation_size):
        fold = (end-train_size)//validation_size
        train_end, valid_end = times[end], times[end+validation_size-1]
        training = [e for e in development if utc(e['available_at']) < train_end]
        validation = [e for e in development if train_end <= utc(e['available_at']) <= valid_end]
        current_ids={e['id'] for e in validation}
        if validation_ids & current_ids or {e['id'] for e in training} & current_ids:
            raise ValueError('overlapping validation event sets')
        validation_ids.update(current_ids)
        candidates = [(h,trial(training,h,'train',fold)) for h in hypotheses]
        eligible = [(h,r) for h,r in candidates if r['status'] == 'completed_exploratory']
        if eligible:
            selected = max(eligible,key=lambda pair:pair[1]['state']['equity'])[0]
            trial(validation,selected,'validation',fold)
    return dict(campaign=campaign,trials=results,holdout=dict(start=holdout_start,status='untouched'),
                validated_edge=False,scaling_authorized=False,synthetic=synthetic,
                warning='Short exploratory trials and synthetic runs cannot establish profitability.')
