"""Complete observed candle aggregation and exact compact quote working sets."""
import csv,hashlib,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
from .canonical_quotes import minute_bars
from .audited_run import NY


def aggregate(one,minutes):
    buckets={};step=minutes*60
    for b in one:buckets.setdefault(b['t']//step*step,[]).append(b)
    out=[]
    for t,rows in sorted(buckets.items()):
        if len(rows)!=minutes or [b['t'] for b in rows]!=list(range(t,t+step,60)):continue
        out.append(dict(t=t,open=rows[0]['open'],high=max(b['high'] for b in rows),low=min(b['low'] for b in rows),close=rows[-1]['close'],volume=sum(b['volume'] for b in rows),spread=min(b['spread'] for b in rows)))
    return out


def build_nasdaq(data):
    if (data/'bar_manifest.json').exists():return json.loads((data/'bar_manifest.json').read_text())
    manifest=json.loads((data/'manifest.json').read_text());sizes=[1,3,5,15,30];files={};writers={};counts={n:0 for n in sizes}
    try:
        for n in sizes:
            files[n]=(data/f'NAS100_M{n}.csv').open('x',newline='');writers[n]=csv.writer(files[n]);writers[n].writerow(['time_epoch_mt5','open','high','low','close','tick_volume','spread'])
        for r in manifest:
            f=data/'quotes'/f"{r['date']}.npz"
            if not f.exists():continue
            assert hashlib.sha256(f.read_bytes()).hexdigest()==r['sha256'];q=np.load(f)['quotes'];end=int((datetime.fromisoformat(r['date']).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp());one=minute_bars(q,end,point=.01)
            for n in sizes:
                rows=one if n==1 else aggregate(one,n)
                for b in rows:writers[n].writerow([b['t'],b['open'],b['high'],b['low'],b['close'],b['volume'],b['spread']])
                counts[n]+=len(rows)
    finally:
        for f in files.values():f.close()
    result=dict(rows=counts,source_quotes=sum(r['rows'] for r in manifest),sha256={str(n):hashlib.sha256((data/f'NAS100_M{n}.csv').read_bytes()).hexdigest() for n in sizes},rule='Only complete consecutive observed minute buckets; no gap fill; same bid/ask archive supplies fills.')
    (data/'bar_manifest.json').write_text(json.dumps(result,indent=2));return result


def load_sessions(folders,first='2025-12-15',last_exclusive='2026-10-31'):
    sessions=[]
    for folder in folders:
        for r in json.loads((folder/'manifest.json').read_text()):
            if not first<=r['date']<last_exclusive:continue
            f=folder/'quotes'/f"{r['date']}.npz"
            if not f.exists():continue
            assert hashlib.sha256(f.read_bytes()).hexdigest()==r['sha256'];local=datetime.fromisoformat(r['date']).replace(hour=10,tzinfo=NY);offset=3 if local.dst() else 2
            lo=(local.replace(hour=9,minute=30).astimezone(timezone.utc).timestamp()+offset*3600)*1000;hi=(local.replace(hour=16,minute=0).astimezone(timezone.utc).timestamp()+offset*3600)*1000
            raw=np.load(f)['quotes'];raw=raw[(raw['time_msc']>=int(lo))&(raw['time_msc']<=int(hi))];q=np.empty(len(raw),dtype=[('time_msc','i8'),('bid','f8'),('ask','f8')])
            for key in q.dtype.names:q[key]=raw[key]
            sessions.append((r['date'],q,offset))
    assert all(b[0]>a[0] for a,b in zip(sessions,sessions[1:]));return sessions
