"""Independent ledger arithmetic and immutable-input audit; no financial replay."""
import argparse
import json
from pathlib import Path
import numpy as np
from .data import sha
from .run import write,stamp


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();summary=[]
    for name in ['short_horizon_mt5_v2','short_horizon_mt5_v3']:
        out=root/'outputs'/name;protocol=json.loads((out/'protocol.json').read_text());result=json.loads((out/'results.json').read_text());identity=json.loads((out/'protocol_identity.json').read_text())
        assert result['protocol_sha256']==identity['sha256']==sha(out/'protocol.json')
        assert all(sha(Path(__file__).parent/f)==v for f,v in protocol['source_sha256'].items())
        assert all(sha(root/f)==v for f,v in json.loads((out/'preserved_research_hashes.json').read_text()).items())
        source={};files=0;fills=0;decisions=0;maximum_realized_excess=0.
        for symbol,rows in protocol['inputs'].items():
            source[symbol]={r['date']:r for r in rows}
            for path in (out/'data/quotes'/symbol).glob('*.npz'):
                r=source[symbol][path.stem];original=root/r['source_file'];assert sha(original)==r['sha256']
                raw=np.load(original)['quotes'];raw=raw[(raw['bid']>0)&(raw['ask']>=raw['bid'])]
                with np.load(path) as z:
                    assert np.array_equal(raw['time_msc'],z['raw_ms']) and np.array_equal(raw['bid'],z['bid']) and np.array_equal(raw['ask'],z['ask'])
                files+=1
        for path in (out/'ledgers').rglob('*.json'):
            d=json.loads(path.read_text());fs=d['fills'];m=d['metrics'];cash=5000.;last=-float('inf')
            assert len(fs)==m['trades'];assert abs(sum(f['pnl'] for f in fs)-m['net_pnl'])<1e-6
            assert sum(f['pnl']>0 for f in fs)==m['wins']
            if fs:assert abs(100*m['wins']/len(fs)-m['win_rate'])<1e-9
            assert sum(x['status']=='EXECUTED' for x in d['decisions'])==len(fs)
            cost=COSTS=protocol['costs']['higher' if path.stem.endswith('_higher') else 'standard'];symbol=path.stem.split('_')[0];meta=json.loads((out/'data/contract_snapshot.json').read_text())[symbol];mult=meta['trade_tick_value_loss']/meta['trade_tick_size']
            delay=protocol.get('execution_delay_seconds',60)
            if path.parent.name=='latency5':delay=5
            for f in fs:
                assert f['entry_at']>last and f['entry_at']>=f['decision']+delay and f['exit_at']>=f['entry_at'];last=f['exit_at']
                assert f['planned_risk']<=min(25.,cash*.005)+1e-6 and f['planned_risk']<=cash*.01+1e-6
                assert f['margin']+f['planned_risk']<=cash+1e-6
                assert abs(f['quantity']/meta['volume_step']-round(f['quantity']/meta['volume_step']))<1e-7 and f['quantity']>=meta['volume_min']
                pnl=((f['exit']-f['entry'])*f['side']*mult-cost['fee_per_lot'])*f['quantity'];assert abs(pnl-f['pnl'])<1e-6
                cash+=pnl;assert abs(cash-f['equity_after'])<1e-6
                maximum_realized_excess=max(maximum_realized_excess,-pnl-f['planned_risk'])
            assert abs(cash-m['ending_balance'])<1e-6
            assert abs(max((f['maximum_drawdown_to_date_pct'] for f in fs),default=0.)-m['drawdown_pct'])<1e-7
            fills+=len(fs);decisions+=len(d['decisions'])
        row=dict(batch=name,audited_utc=stamp(),quote_files_verified_against_original=files,ledger_files=len(list((out/'ledgers').rglob('*.json'))),fill_records_reconciled=fills,decision_records=decisions,maximum_realized_loss_above_planned_dollars=maximum_realized_excess,arithmetic_and_risk_checks='PASS',source_identity='PASS',previous_research_hashes='PASS',independent_validation=False)
        write(out/'audit.json',row);summary.append(row)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
