"""Invented fixtures for chronological integration, never market performance."""
import copy,hashlib,json
from pathlib import Path
from .closing_fixtures import create as session_fixture
from .closing_admission import RISK,SCENARIOS

def create(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    contracts=session_fixture()['contracts'];contracts['TEST']['evidence_available_at']='2026-01-01T00:00:00Z'
    def day(day,previous):
        b=session_fixture();mapping={'2026-01-06':day,'2026-01-05':previous}
        def shift(v):
            if isinstance(v,dict):return {k:shift(x) for k,x in v.items()}
            if isinstance(v,list):return [shift(x) for x in v]
            if isinstance(v,str):
                for old,new in mapping.items():v=v.replace(old,new)
            return v
        b=shift(b);sid='s-'+day
        rows=[e for e in b['events'] if e['kind'] in ('bar','quote')]
        for e in rows:e['id']=sid+'-'+e['id']
        rows[-1].update(bid=110,ask=110.25)
        return rows,{sid:b['sessions']['session']}
    train,ts=day('2026-01-06','2026-01-05');v1,s1=day('2026-01-08','2026-01-07');v2,s2=day('2026-01-12','2026-01-09')
    def write(name,value,lines=False):
        p=folder/name;p.write_text(''.join(json.dumps(e)+'\n' for e in value) if lines else json.dumps(value),encoding='utf-8')
        return dict(path=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    files={'train':write('train.jsonl',train,True)|dict(start='2026-01-05T00:00:00Z',end='2026-01-06T22:00:00Z'),
           'validation':write('validation.jsonl',v1+v2,True)|dict(start='2026-01-07T00:00:00Z',end='2026-01-12T22:00:00Z')}
    calendars={'train':write('train-sessions.json',ts),'validation':write('validation-sessions.json',s1|s2)}
    admin=write('administrative.json',[])|dict(start='2026-01-01T00:00:00Z',end='2026-01-13T00:00:00Z',complete=True,review_reference='SYNTHETIC COVERAGE',source_reference='SYNTHETIC NO MARGIN CHANGES')
    manifest=dict(dataset_id='SYNTHETIC-CLOSING-WALKFORWARD',synthetic=True,partition='development',source_kind='synthetic',verified=True,review_reference='SYNTHETIC SOFTWARE TEST',timestamp_semantics_verified=True,quote_path_verified=True,effective_costs_verified=True,static_costs_unchanged_verified=True,source_reference='INVENTED SOFTWARE FIXTURES',prior_exposure='synthetic',bar_seconds=300,files=files,calendars=calendars,administrative=admin,final_holdout=dict(start='2026-01-14T00:00:00Z',access='locked',commitment_sha256='0'*64,path='HOLDOUT_DO_NOT_OPEN'))
    plan=dict(strategy='closing_half_hour_continuation/1.0.0',risk=copy.deepcopy(RISK),scenarios=copy.deepcopy(SCENARIOS),validation_windows=[dict(start='2026-01-07T00:00:00Z',end='2026-01-08T22:00:00Z'),dict(start='2026-01-09T00:00:00Z',end='2026-01-12T22:00:00Z')])
    return plan,manifest,contracts
