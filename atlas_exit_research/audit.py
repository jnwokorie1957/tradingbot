"""Independent, read-only completed-comparison arithmetic and quote DD audit."""
import argparse,json
from pathlib import Path
from .data import Market,reconstruct,write,sha,stamp
from .control_check import inputs
from research_monitor.atlas_opportunity_study import COSTS


def reconcile(market,fills,meta,cost,reported):
    pieces=[];maximum=0.;quantity_error=0.
    for f in fills:
        m=meta[f['symbol']];mult=m['trade_tick_value_loss']/m['trade_tick_size'];computed=sum(((l['price']-f['entry'])*f['side']*mult-cost['fee'])*l['quantity'] for l in f['legs']);maximum=max(maximum,abs(computed-f['pnl']));quantity_error=max(quantity_error,abs(sum(l['quantity'] for l in f['legs'])-f['quantity']))
        for l in f['legs']:pieces.append(dict(f,quantity=l['quantity'],exit_at=l['at'],exit=l['price'],pnl=l['pnl']))
    assert maximum<1e-7 and quantity_error<1e-9
    curve,contributions=reconstruct(market,pieces,meta,cost,5000.);net=sum(f['pnl'] for f in fills);assert abs(net-reported['net_pnl'])<1e-6;assert len(fills)==reported['trades'];assert abs(curve['quote_drawdown_pct']-reported['quote_drawdown_pct'])<1e-7
    return dict(arithmetic_pass=True,quote_drawdown_pass=True,max_trade_formula_error=maximum,max_leg_quantity_error=quantity_error,net_pnl=net,trades=len(fills),win_rate=100*sum(f['pnl']>0 for f in fills)/len(fills) if fills else None,quote_drawdown_pct=curve['quote_drawdown_pct'],curve=curve['curve'],contribution_quote_drawdown={n:x['quote_drawdown_pct'] for n,x in contributions.items()})


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root.resolve();out=root/'outputs/atlas_exit_management_v1';run=out/'comparison';assert (run/'completed.json').exists();target=run/'independent_audit.json';assert not target.exists();_,meta=inputs(root);rows=json.loads((run/'results.json').read_text());audits={}
    for symbol,names in [('SPX500',['SPX15']),('NAS100',['NAS15','NAS5'])]:
        market=Market(root,out,(symbol,))
        for r in rows:
            if r['scope']!='full' or r['lane']not in names or r.get('equivalent_to'):continue
            file=run/'ledgers'/f'{r["id"]}.json';fills=json.loads(file.read_text());audits[r['id']]=dict(reconcile(market,fills,meta,COSTS[r['cost']],r['account']),ledger_sha256=sha(file));write(out/'audit_progress.json',dict(status='running',completed=len(audits),total=69))
        del market
    market=Market(root,out)
    for r in json.loads((run/'portfolio.json').read_text()):
        file=run/f'portfolio_fills_{r["cost"]}.json';fills=json.loads(file.read_text());audits['portfolio_'+r['cost']]=dict(reconcile(market,fills,meta,COSTS[r['cost']],r['account']),ledger_sha256=sha(file))
    write(target,dict(completed_utc=stamp(),records=audits,all_pass=True,scope='Independent ledger formulas and full quote-equity reconstruction. This verifies calculations under estimated inputs,not broker execution or predictive validity.'));write(out/'audit_progress.json',dict(status='completed',completed=len(audits),total=69));print(json.dumps(dict(completed=len(audits),all_pass=True)))


if __name__=='__main__':main()
