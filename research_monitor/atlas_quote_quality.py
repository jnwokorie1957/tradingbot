"""Post-audit diagnostics,without modifying financial runs or strategy decisions."""
import argparse,json
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root;out=root/'outputs/atlas_risk_audit_v1';rows=json.loads((out/'results.json').read_text());result=[]
    for r in rows:
        if r['kind']!='portfolio' or r['scenario'] not in ['standard','higher']:continue
        trace=np.load(out/f'private_quote_trace_{r["ledger"]}.npz')['trace'];fills=json.loads((out/f'private_fills_{r["ledger"]}.json').read_text());ids={s:i for i,s in enumerate(sorted({f['symbol'] for f in fills}))};max_stale=0.
        for s,ident in ids.items():
            ix=np.maximum.accumulate(np.where(trace['symbol']==ident,np.arange(len(trace)),-1))
            for f in fills:
                if f['symbol']!=s:continue
                a,b=f['entry_event']-1,f['exit_event']-1
                if b>a:max_stale=max(max_stale,float(np.max(trace['t'][a:b]-trace['t'][ix[a:b]])))
        violations=[f for f in fills if -f['pnl']>f['planned_risk']+1e-7]
        result.append(dict(system=r['system'],scenario=r['scenario'],max_held_position_quote_age_seconds=max_stale,actual_losses_beyond_planned_risk=len(violations),largest_actual_trade_loss=max([-f['pnl'] for f in fills if f['pnl']<0],default=0.),excess_loss_beyond_planned_total=sum(-f['pnl']-f['planned_risk'] for f in violations),interpretation='Plannedstoprisk isnot ahard realized-loss cap. Quote-age is latestobservablemark whilepositionsheld;not orderlatency or executabledepthverification.'))
    (out/'quote_quality.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':main()
