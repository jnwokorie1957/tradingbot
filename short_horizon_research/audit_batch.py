"""Audit a new immutable batch without changing earlier registered audit code."""
import argparse,json
from pathlib import Path
import numpy as np
from .data import sha
from .run import write,stamp


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--version',required=True);a=p.parse_args();root=a.root.resolve();out=root/'outputs'/a.version
    if not a.version.startswith('short_horizon_mt5_v') or not a.version.removeprefix('short_horizon_mt5_v').isdigit():raise ValueError('Unexpected batch name')
    protocol=json.loads((out/'protocol.json').read_text());result=json.loads((out/'results.json').read_text());meta=json.loads((out/'data/contract_snapshot.json').read_text())
    assert result['protocol_sha256']==json.loads((out/'protocol_identity.json').read_text())['sha256']==sha(out/'protocol.json')
    assert all(sha(Path(__file__).parent/f)==v for f,v in protocol['source_sha256'].items())
    assert all(sha(root/f)==v for f,v in json.loads((out/'preserved_research_hashes.json').read_text()).items())
    quote_files=fill_count=decision_count=0;worst=None;files=list((out/'ledgers').rglob('*.json'))
    for symbol,rows in protocol['inputs'].items():
        sources={r['date']:r for r in rows}
        for path in (out/'data/quotes'/symbol).glob('*.npz'):
            r=sources[path.stem];original=root/r['source_file'];assert sha(original)==r['sha256'];raw=np.load(original)['quotes'];raw=raw[(raw['bid']>0)&(raw['ask']>=raw['bid'])]
            with np.load(path) as z:assert all(np.array_equal(raw[k],z[v]) for k,v in [('time_msc','raw_ms'),('bid','bid'),('ask','ask')])
            quote_files+=1
    for path in files:
        d=json.loads(path.read_text());fs=d['fills'];m=d['metrics'];cash=5000.;last=-float('inf');symbol=path.stem.split('_')[0];contract=meta[symbol];cost=protocol['costs']['higher' if path.stem.endswith('_higher') else 'standard'];mult=contract['trade_tick_value_loss']/contract['trade_tick_size'];delay=5 if path.parent.name=='latency5' else protocol.get('execution_delay_seconds',60)
        assert len(fs)==m['trades'];assert abs(sum(f['pnl'] for f in fs)-m['net_pnl'])<1e-6;wins=[f['pnl'] for f in fs if f['pnl']>0];losses=[f['pnl'] for f in fs if f['pnl']<0]
        assert len(wins)==m['wins'];assert not fs or abs(100*len(wins)/len(fs)-m['win_rate'])<1e-9
        if losses:assert abs(sum(wins)/-sum(losses)-m['profit_factor'])<1e-9
        assert sum(x['status']=='EXECUTED' for x in d['decisions'])==len(fs)
        for f in fs:
            assert f['entry_at']>last and f['entry_at']>=f['decision']+delay and f['exit_at']>=f['entry_at'];last=f['exit_at']
            assert f['planned_risk']<=min(25.,cash*.005)+1e-6 and f['planned_risk']<=cash*.01+1e-6 and f['margin']+f['planned_risk']<=cash+1e-6
            assert abs(f['quantity']/contract['volume_step']-round(f['quantity']/contract['volume_step']))<1e-7 and f['quantity']>=contract['volume_min']
            pnl=((f['exit']-f['entry'])*f['side']*mult-cost['fee_per_lot'])*f['quantity'];assert abs(pnl-f['pnl'])<1e-6;cash+=pnl;assert abs(cash-f['equity_after'])<1e-6
            if worst is None or -pnl-f['planned_risk']>worst['loss_above_planned']:worst=dict(config=path.stem,pnl=pnl,planned_risk=f['planned_risk'],loss_above_planned=-pnl-f['planned_risk'],entry_at=f['entry_at'],exit_at=f['exit_at'])
        assert abs(cash-m['ending_balance'])<1e-6;assert abs(max((f['maximum_drawdown_to_date_pct'] for f in fs),default=0.)-m['drawdown_pct'])<1e-7
        fill_count+=len(fs);decision_count+=len(d['decisions'])
    snapshot=out/'source_snapshot';snapshot.mkdir(exist_ok=True)
    for name,value in protocol['source_sha256'].items():
        source=Path(__file__).parent/name;assert sha(source)==value;target=snapshot/name
        if target.exists():assert sha(target)==value
        else:target.write_bytes(source.read_bytes())
    row=dict(batch=a.version,audited_utc=stamp(),quote_files_verified_against_original=quote_files,ledger_files=len(files),fill_records_reconciled=fill_count,decision_records=decision_count,arithmetic_and_planned_risk_checks='PASS',source_identity='PASS',previous_research_hashes='PASS',realized_loss_is_not_guaranteed_capped=True,worst_excess=worst,independent_validation=False)
    write(out/'audit.json',row);print(json.dumps(row,indent=2))


if __name__=='__main__':main()
