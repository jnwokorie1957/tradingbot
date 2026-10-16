"""Explicit synthetic-only one-shot CLI for new chronological research integration."""
import argparse,json
from pathlib import Path
from .closing_walkforward_fixtures import create
from .closing_walkforward import register,run
from .journal import Journal

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    plan,manifest,contracts=create(output/'synthetic-data')
    for name,value in [('plan',plan),('manifest',manifest),('contracts',contracts)]:
        (output/'synthetic-data'/(name+'.json')).write_text(json.dumps(value,indent=2))
    journal=Journal(str(output/'journal.sqlite'))
    try:
        frozen=register(journal,'closing-walkforward-synthetic-v1',plan,manifest,contracts)
        report=run(journal,'closing-walkforward-synthetic-v1',frozen,manifest,contracts,output/'synthetic-data',output/'trials')
    finally:journal.close()
    print(json.dumps(dict(status=report['status'],trials=len(report['trials']),synthetic=True,qualified_for_paper=False)))

if __name__=='__main__':main()
