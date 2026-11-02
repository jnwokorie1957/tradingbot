"""Read-only MT5 quote provenance and complete candle aggregation."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

NY=ZoneInfo('America/New_York')
BARS=np.dtype([('t','f8'),('open','f8'),('high','f8'),('low','f8'),('close','f8'),('volume','i8')])


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def archives(root):
    folders={'NAS100':[root/'outputs/nas100_quote_data_v1'],
             'SPX500':[root/'outputs/spx15_canonical_quote_data_v1',root/'outputs/spx15_direction_later_v1/data']}
    result={}
    for symbol,paths in folders.items():
        rows=[]
        for folder in paths:
            for r in json.loads((folder/'manifest.json').read_text()):
                if '2025-12-12'<=r['date']<'2026-10-31':rows.append(dict(r,source_file=str((folder/'quotes'/f'{r["date"]}.npz').relative_to(root))))
        rows.sort(key=lambda r:r['date'])
        assert len({r['date'] for r in rows})==len(rows)
        result[symbol]=rows
    return result


def quotes(root,out,symbol,row,clock):
    cache=out/'data/quotes'/symbol/f'{row["date"]}.npz'
    if not cache.exists():
        original=root/row['source_file'];assert sha(original)==row['sha256']
        raw=np.load(original)['quotes'];valid=(raw['bid']>0)&(raw['ask']>=raw['bid']);raw=raw[valid]
        cache.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(cache,raw_ms=raw['time_msc'],bid=raw['bid'],ask=raw['ask'])
    with np.load(cache) as z:
        offset=3 if clock=='fixed3' or bool(datetime.fromisoformat(row['date']).replace(hour=12,tzinfo=NY).dst()) else 2
        t=z['raw_ms'].astype(float)/1000-offset*3600;bid=z['bid'];ask=z['ask']
    assert np.all(np.diff(t)>=0)
    return t,bid,ask


def candles(t,bid,minutes):
    if not len(t):return np.empty(0,dtype=BARS)
    bucket=np.floor(t/60).astype('i8')*60;starts=np.r_[0,np.flatnonzero(np.diff(bucket))+1];ends=np.r_[starts[1:],len(t)]
    one=np.empty(len(starts),dtype=BARS);one['t']=bucket[starts];one['open']=bid[starts];one['close']=bid[ends-1]
    one['high']=np.maximum.reduceat(bid,starts);one['low']=np.minimum.reduceat(bid,starts);one['volume']=ends-starts
    if minutes==1:return one
    step=minutes*60;key=(one['t']//step).astype('i8');s=np.r_[0,np.flatnonzero(np.diff(key))+1];e=np.r_[s[1:],len(one)];rows=[]
    for lo,hi in zip(s,e):
        b=one[lo:hi];begin=int(b['t'][0]//step)*step
        if len(b)!=minutes or not np.array_equal(b['t'],np.arange(begin,begin+step,60)):continue
        rows.append((begin,b['open'][0],max(b['high']),min(b['low']),b['close'][-1],sum(b['volume'])))
    return np.array(rows,dtype=BARS)
