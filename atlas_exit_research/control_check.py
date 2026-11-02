"""Require exact archived $5,000 control parity before exit research."""
import argparse,json
from pathlib import Path
from .data import Market,write,stamp,sha
from .engine import Account
from research_monitor.atlas_capture_inputs import load
from research_monitor.native_data import aggregate
from research_monitor.atlas_opportunity_study import COSTS


def inputs(root):
    lanes,meta,folders,warmup,_=load(root)
    for name,lane in lanes.items():lane.update(minutes=5 if name=='NAS5' else 15,native=aggregate(warmup[lane['symbol']],5 if name=='NAS5' else 15))
    return lanes,meta


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--version',default='control_parity_v2');a=p.parse_args();root=a.root.resolve();out=root/'outputs/atlas_exit_management_v1';folder=out/a.version;folder.mkdir(exist_ok=False)
    write(folder/'protocol.json',dict(registered_utc=stamp(),purpose='Engine parity against unchanged three-strategy approved5000 ledgers; not a strategy search',sources={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')}))
    market=Market(root,out);lanes,meta=inputs(root);results=[];archived=root/'outputs/atlas_opportunity_v1/approved5000';refs=json.loads((archived/'results.json').read_text())
    for cost in COSTS:
        write(out/'progress.json',dict(status='running',phase='control_parity',cost=cost,completed=len(results),total=3));book=Account(market,lanes,meta,COSTS[cost],{n:'original' for n in lanes});book.run_to('2026-10-31');r=book.result();ref=next(x for x in refs if x['cost']==cost);expected=json.loads((archived/f'fills_{ref["ledger"]}.json').read_text());write(folder/f'fills_{cost}.json',book.fills);write(folder/f'decisions_{cost}.json',book.decisions)
        checks=dict(trade_count=len(book.fills)==len(expected),net=abs(r['net_pnl']-ref['net_pnl'])<1e-6,quote_drawdown=abs(r['quote_drawdown_pct']-ref['quote_drawdown_pct'])<1e-7,open_positions=not book.positions)
        errors=[]
        for actual,wanted in zip(book.fills,expected):
            for key,value in wanted.items():
                if key not in actual:errors.append(dict(id=wanted.get('id'),key=key,reason='missing'));continue
                if isinstance(value,(int,float)) and not isinstance(value,bool):ok=abs(actual[key]-value)<1e-7
                else:ok=actual[key]==value
                if not ok:errors.append(dict(id=wanted.get('id'),key=key,actual=actual[key],expected=value))
        checks['exact_financial_fills']=not errors;row=dict(cost=cost,result=r,checks=checks,first_errors=errors[:10]);results.append(row);write(folder/'results.json',results);print(json.dumps(row),flush=True)
        assert all(checks.values()),'Control parity failed; no exit experiment permitted before diagnosis'
    write(folder/'completed.json',dict(completed_utc=stamp(),cases=3,exact_financial_parity=True))


if __name__=='__main__':main()
