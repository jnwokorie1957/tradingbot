import hashlib,json,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

NY=ZoneInfo('America/New_York')
DTYPE=np.dtype([('t','f8'),('bid','f8'),('ask','f8')])


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
    for attempt in range(30):
        try:tmp.replace(path);return
        except PermissionError:
            if attempt==29:raise
            time.sleep(.1)


def prepare(root,out):
    folders={'NAS100':['outputs/nas100_quote_data_v1'],'SPX500':['outputs/spx15_canonical_quote_data_v1','outputs/spx15_direction_later_v1/data']};manifest={}
    for symbol,paths in folders.items():
        rows=[]
        for name in paths:
            folder=root/name
            for r in json.loads((folder/'manifest.json').read_text()):
                if '2025-12-12'<=r['date']<'2026-10-31' and r.get('status')=='captured':rows.append(dict(r,file=str((folder/'quotes'/f'{r["date"]}.npz').relative_to(root))))
        rows.sort(key=lambda x:x['date']);assert len({x['date'] for x in rows})==len(rows)
        target=out/'data'/f'{symbol}_quotes.npy';chunks=[]
        if not target.exists():
            for r in rows:
                src=root/r['file'];assert sha(src)==r['sha256'];raw=np.load(src)['quotes'];assert np.all((raw['bid']>0)&(raw['ask']>=raw['bid']))
                q=np.empty(len(raw),dtype=DTYPE);offset=3 if datetime.fromisoformat(r['date']).replace(hour=12,tzinfo=NY).dst() else 2
                q['t']=raw['time_msc']/1000-offset*3600;q['bid']=raw['bid'];q['ask']=raw['ask'];chunks.append(q)
            target.parent.mkdir(parents=True,exist_ok=True);q=np.concatenate(chunks);assert np.all(np.diff(q['t'])>=0);np.save(target,q);del q,chunks
        manifest[symbol]=dict(sources=rows,cache=str(target.relative_to(root)),sha256=sha(target),clock='Existing benchmark NY-DST-linked +2/+3 inference; historical policy unverified')
    write(out/'data_identity.json',manifest);return manifest


class Market:
    def __init__(self,root,out,symbols=('SPX500','NAS100')):
        self.symbols=tuple(symbols);self.q={s:np.load(out/'data'/f'{s}_quotes.npy',mmap_mode='r') for s in symbols};self.t={s:np.ascontiguousarray(q['t']) for s,q in self.q.items()}
        if len(symbols)==1:
            s=symbols[0];self.times=self.t[s];self.indices={s:np.arange(len(self.times),dtype='i8')}
        else:
            all_times=np.concatenate([self.t[s] for s in symbols]);order=np.argsort(all_times,kind='stable');self.times=all_times[order];inverse=np.empty_like(order);inverse[order]=np.arange(len(order));self.indices={};start=0
            for s in symbols:self.indices[s]=inverse[start:start+len(self.t[s])];start+=len(self.t[s])
            del all_times,order,inverse
        first=datetime(2025,12,10,tzinfo=NY);dates=[first+timedelta(days=i) for i in range(330)];self.midnights=np.array([x.timestamp() for x in dates]);self.dates=[x.date().isoformat() for x in dates]
        self.day_index=np.searchsorted(self.midnights,self.times,side='right')-1

    def asset_index(self,symbol,k):return int(np.searchsorted(self.indices[symbol],k,side='right')-1)
    def event(self,symbol,i):return int(self.indices[symbol][i])
    def quote(self,symbol,k):
        i=self.asset_index(symbol,k)
        if i<0:raise ValueError('No observed quote for asset at this event')
        return self.q[symbol][i]


def reconstruct(market,fills,meta,cost,initial):
    """Independent event-ordered quote equity from an immutable executed ledger."""
    spans=[];locations=[]
    for f in fills:
        s=f['symbol'];i=int(np.searchsorted(market.t[s],f['entry_at']));j=int(np.searchsorted(market.t[s],f['exit_at']));assert i<len(market.t[s]) and j<len(market.t[s]);assert abs(market.t[s][i]-f['entry_at'])<1e-5 and abs(market.t[s][j]-f['exit_at'])<1e-5
        a,b=market.event(s,i),market.event(s,j);spans.append((a,b+1));locations.append((f,a,b))
    merged=[]
    for a,b in sorted(spans):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    ix=np.concatenate([np.arange(a,b) for a,b in merged]) if merged else np.array([],dtype=int)
    flows=np.zeros(len(ix));floating=np.zeros(len(ix));by_lane={}
    for f,a,b in locations:
        s=f['symbol'];m=meta[s];mult=m['trade_tick_value_loss']/m['trade_tick_size'];slip=m['trade_tick_size']*cost['slip_ticks'];q=f['quantity'];side=f['side'];fee=cost['fee'];pnl=((f['exit']-f['entry'])*side*mult-fee)*q
        assert abs(pnl-f['pnl'])<1e-7
        lo=int(np.searchsorted(ix,a));hi=int(np.searchsorted(ix,b));flows[hi]+=pnl
        lane=by_lane.setdefault(f['strategy'],[np.zeros(len(ix)),np.zeros(len(ix))]);lane[0][hi]+=pnl
        if hi>lo:
            own=np.searchsorted(market.indices[s],ix[lo:hi],side='right')-1;raw=market.q[s][own];ask=raw['bid']+(raw['ask']-raw['bid'])*cost['spread'];price=raw['bid'] if side==1 else ask
            value=((price-side*slip-f['entry'])*side*mult-fee)*q;floating[lo:hi]+=value;lane[1][lo:hi]+=value
    def summary(flow,unreal):
        equity=initial+np.cumsum(flow)+unreal;peak=np.maximum.accumulate(np.r_[initial,equity])[1:];dd=(peak-equity)/peak
        sample=np.unique(np.r_[np.arange(0,len(ix),max(1,len(ix)//600)),int(np.argmax(dd))]) if len(ix) else np.array([],int)
        return dict(quote_drawdown_pct=100*float(dd.max()) if len(ix) else 0.,maximum_drawdown_dollars=float((peak-equity).max()) if len(ix) else 0.,curve=[dict(t=float(market.times[ix[k]]),equity=float(equity[k])) for k in sample])
    return summary(flows,floating),{n:summary(*v) for n,v in by_lane.items()}
