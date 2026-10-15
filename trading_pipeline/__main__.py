import argparse,json
from pathlib import Path
from .fixtures import create
from .journal import Journal
from .runner import register,run

def main():
 parser=argparse.ArgumentParser(description='Offline research only; no broker transport')
 sub=parser.add_subparsers(dest='command',required=True)
 demo=sub.add_parser('synthetic-check');demo.add_argument('--output',required=True)
 reg=sub.add_parser('register');reg.add_argument('--dataset',required=True);reg.add_argument('--journal',required=True);reg.add_argument('--experiment',required=True);reg.add_argument('--output',required=True)
 execute=sub.add_parser('run');execute.add_argument('--dataset',required=True);execute.add_argument('--journal',required=True);execute.add_argument('--experiment',required=True);execute.add_argument('--plan',required=True);execute.add_argument('--output',required=True)
 args=parser.parse_args()
 if args.command=='synthetic-check':
  out=Path(args.output);out.mkdir(parents=True,exist_ok=False);base=out/'synthetic-input';plan,manifest,contracts=create(base)
  journal=Journal(out/'journal.sqlite')
  try:
   frozen=register(journal,'SYNTHETIC-CHECK',plan,manifest,contracts)
   result=run(journal,'SYNTHETIC-CHECK',frozen,manifest,contracts,base,out/'results')
  finally:journal.close()
 else:
  base=Path(args.dataset);manifest=json.loads((base/'manifest.json').read_text());contracts=json.loads((base/'contracts.json').read_text());journal=Journal(args.journal)
  try:
   if args.command=='register':
    plan=json.loads((base/'plan.json').read_text());result=register(journal,args.experiment,plan,manifest,contracts)
    with Path(args.output).open('x') as f:json.dump(result,f,indent=2)
   else:
    plan=json.loads(Path(args.plan).read_text());result=run(journal,args.experiment,plan,manifest,contracts,base,args.output)
  finally:journal.close()
 print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
