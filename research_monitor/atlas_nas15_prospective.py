"""Frozen-rule prospective receipt-clock replay; no MT5 API or order transport."""
import argparse
import hashlib
import itertools
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .atlas_capture_inputs import load, build_lane
from .atlas_live_core import PaperBook
from .atlas_metrics import metrics
from .atlas_nas15_regimes import PROFILES, make_variants
from .atlas_opportunity_study import COSTS
from .atlas_portfolio_controller import APPROVED
from .audited_run import NY
from .native_data import aggregate

FOLDER='atlas_nas15_prospective_v1'
FUTURE_PROFILES=('control','h4_long')


def atomic(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def read_only(path):
    db=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True);db.execute('PRAGMA query_only=ON');return db


def groups(db,start_ms,end_ms):
    rows=db.execute('SELECT rowid,symbol,raw_ms,bid,ask,occurrence,receipt_ms FROM quotes WHERE receipt_ms>=? AND receipt_ms<=? ORDER BY receipt_ms,rowid',(start_ms,end_ms))
    for receipt,rows in itertools.groupby(rows,key=lambda r:r[6]):yield receipt/1000,list(rows)


def received_minutes(grouped,offsets,freeze,points=None):
    """Source OHLC uses only received ticks; completed minutes never revise."""
    first=int(freeze//60)*60+60
    points=points or {s:1. for s in offsets}
    buckets={s:{} for s in offsets};completed={s:first for s in offsets}
    minutes={s:{} for s in offsets};availability={s:{} for s in offsets}
    late=Counter()
    for receipt,rows in grouped:
        for _,symbol,raw,bid,ask,occurrence,_ in rows:
            source=raw/1000-offsets[symbol]*3600
            if source>receipt+1:raise ValueError('Frozen clock mismatch: future-dated source quote')
            m=int(source//60)*60
            if m<first:continue
            if m<completed[symbol]:late[symbol]+=1;continue
            p=buckets[symbol].setdefault(m,dict(t=m,open=bid,high=bid,low=bid,close=bid,volume=0,spread=(ask-bid)/points[symbol],first_source=source,last_source=source))
            p['high']=max(p['high'],bid);p['low']=min(p['low'],bid);p['volume']+=1;p['spread']=min(p['spread'],(ask-bid)/points[symbol])
            if source<p['first_source']:p['first_source']=source;p['open']=bid
            if source>=p['last_source']:p['last_source']=source;p['close']=bid
        for symbol in offsets:
            for m in sorted(list(buckets[symbol])):
                if m+65>receipt:continue
                b=buckets[symbol].pop(m);b.pop('first_source');b.pop('last_source')
                minutes[symbol][m]=b;availability[symbol][m]=receipt;completed[symbol]=max(completed[symbol],m+60)
    return minutes,availability,dict(late)


def session_coverage(minutes,through):
    counts={s:Counter() for s in minutes}
    for symbol,bars in minutes.items():
        for t in bars:
            d=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
            if d.weekday()<5 and 570<=d.hour*60+d.minute<960:counts[symbol][d.date().isoformat()]+=1
    days=sorted(set().union(*(set(c) for c in counts.values())))
    qualified=[]
    for day in days:
        end=datetime.fromisoformat(day).replace(hour=16,minute=15,tzinfo=NY).timestamp()
        if end<=through and all(counts[s][day]>=351 for s in counts):qualified.append(day)
    return dict(complete_sessions=qualified,minute_counts={s:dict(c) for s,c in counts.items()},criterion='Both instruments at least351/390 observed RTH minutes; after16:15NewYork. Coverage threshold is a data gate, not a trade quota.')


def cutoff_now():
    at=datetime.now(timezone.utc).astimezone(NY)
    day=at.date()
    if at.hour*60+at.minute<975:day-=timedelta(days=1)
    while day.weekday()>=5:day-=timedelta(days=1)
    return datetime.combine(day,datetime.min.time(),tzinfo=NY).replace(hour=16,minute=15).timestamp()


def freeze(root,folder):
    folder.mkdir(exist_ok=False)
    state=root/'work/tradingbot/local-results/atlas-forward-v2'
    status=json.loads((state/'status.json').read_text())
    now=datetime.now(timezone.utc);stamp=now.timestamp()
    if status['status']!='observing_paper_forward' or (now-datetime.fromisoformat(status['last_poll_utc'])).total_seconds()>60:
        raise ValueError('A fresh existing collector is required before freezing future observations')
    assert status['paper_only'] and status['broker_execution_calls']==0
    original=json.loads((state/'freeze.json').read_text())
    hashes={}
    names=set(original['source_hashes'])|{'atlas_nas15_prospective.py','atlas_nas15_regimes.py','native_context.py','atlas_capture_quotes_v2.py','atlas_metrics.py'}
    for name in sorted(names):
        p=root/'work/tradingbot'/('trading_pipeline' if name=='engine_v4.py' else 'research_monitor')/name
        hashes[str(p.relative_to(root))]=digest(p)
        if name in original['source_hashes']:assert digest(p)==original['source_hashes'][name]
    offsets={s:c['offset_hours'] for s,c in status['clock'].items()}
    assert set(offsets)=={'NAS100','SPX500'} and all(x is not None for x in offsets.values())
    db=read_only(state/'observations.sqlite')
    warmup={s:[] for s in offsets}
    for symbol,t,payload in db.execute('SELECT symbol,t,payload FROM minutes WHERE t+65<=? ORDER BY t',(stamp,)):
        warmup[symbol].append(json.loads(payload))
    db.close();atomic(folder/'warmup_receipts.json',warmup)
    data_files=[]
    for name in ['nas100_quote_data_v1','spx15_canonical_quote_data_v1','spx15_direction_later_v1/data']:
        data_folder=root/'outputs'/name
        data_files.extend(data_folder.glob('*.csv'))
        data_files.extend(p for p in [data_folder/'manifest.json',data_folder/'metadata.json'] if p.exists())
    data_files.append(root/'work/mt5_symbol_metadata.json')
    data_hashes={str(p.relative_to(root)):digest(p) for p in data_files}
    evidence=root/'outputs/atlas_nas15_regime_v2/results.json'
    protocol=dict(frozen_utc=now.isoformat(),freeze_epoch=stamp,profiles=FUTURE_PROFILES,risk=APPROVED,
                  costs={c:COSTS[c] for c in ['standard','higher']},offset_hours=offsets,
                  metadata=status['symbol_metadata'],collector_database=str((state/'observations.sqlite').relative_to(root)),
                  collector_freeze_sha256=digest(state/'freeze.json'),source_sha256=hashes,
                  warmup_sha256=digest(folder/'warmup_receipts.json'),historical_warmup_input_sha256=data_hashes,
                  development_evidence_sha256=digest(evidence),development_evidence=str(evidence.relative_to(root)),
                  candidate='CompletedUTC4hEMA20 alignment for NAS15 longs. Chosen from development profit/drawdown improvement at both costs; observed development win rate50%, not above60. No future-price selection.',
                  evaluation='Finite receipt-clock forward replay of all preregistered variants on genuinely new post-freeze observations. This is not actual order routing or a live shadow fill. Actual collector first-receipt times define virtual availability/execution, even when this evaluator runs later.',
                  bars='Construct post-freeze complete minutes only from quotes received by that collector receipt; finalize after65seconds; never revise with late quotes. Prior bars/receipts supply indicators only. Native15m signals enqueue only once their source minute bars have become available.',
                  fills='Source-ordered received paths manage virtual positions; last fresh source quote in each collector receipt batch admits delayed intents. Five-second freshness, sixty-second entry delay, same1.5R/natural-stop/risk logic. No fills are claimed at evaluator wall time. Broker liquidity/acceptance unverified.',
                  future_gate='No loss of NAS or portfolio modeled net and no increase of NAS contribution or portfolio drawdown at both costs, WR>60%, at least30 NAS closed trades across at least5 complete sessions,75% baseline capture. Report small samples as descriptive only. No refitting; a selected winner still requires another new market block for confirmation.',
                  cadence='Evaluate only after5 newly completed adequately observed RTH sessions beyond the last batch. Overlapping earlier observations are one cumulative cohort, never independent repeats.',
                  paper_only=True,deployment=False)
    atomic(folder/'protocol.json',protocol)
    atomic(folder/'protocol_identity.json',dict(sha256=digest(folder/'protocol.json')))
    atomic(folder/'progress.json',dict(status='waiting_new_completed_sessions',last_scored_sessions=[],last_batch=None))
    print(json.dumps(dict(frozen_utc=protocol['frozen_utc'],profiles=FUTURE_PROFILES,financial_observations_scored=0,source='existing read-only collector;no second MT5 connection')))


def verify(root,folder):
    p=folder/'protocol.json'
    assert digest(p)==json.loads((folder/'protocol_identity.json').read_text())['sha256']
    protocol=json.loads(p.read_text())
    assert digest(folder/'warmup_receipts.json')==protocol['warmup_sha256']
    assert digest(root/protocol['development_evidence'])==protocol['development_evidence_sha256']
    for name,h in protocol['source_sha256'].items():assert digest(root/name)==h,name
    for name,h in protocol['historical_warmup_input_sha256'].items():assert digest(root/name)==h,name
    collector_folder=(root/protocol['collector_database']).parent
    assert digest(collector_folder/'freeze.json')==protocol['collector_freeze_sha256']
    current=json.loads((collector_folder/'status.json').read_text())
    for symbol,metadata in protocol['metadata'].items():
        present=current['symbol_metadata'][symbol]
        for field in ['trade_tick_size','trade_tick_value_loss','trade_contract_size','volume_min','volume_step']:
            assert abs(present[field]-metadata[field])<1e-8,'Contract metadata changed; future cohort requires review'
    assert protocol['risk']==APPROVED and protocol['paper_only']
    return protocol


def evaluate(root,folder,protocol,through,status_only):
    database=root/protocol['collector_database'];source=read_only(database)
    start_ms=int(protocol['freeze_epoch']*1000);end_ms=int(through*1000)
    progress=json.loads((folder/'progress.json').read_text())
    # Cheap availability scan; financial processing needs finalized observed minutes below.
    observed={s:{} for s in protocol['offset_hours']}
    for symbol,rawminute in source.execute('SELECT symbol,raw_ms/60000 FROM quotes WHERE receipt_ms>=? AND receipt_ms<=? GROUP BY symbol,raw_ms/60000',(start_ms,end_ms)):
        t=int(rawminute)*60-protocol['offset_hours'][symbol]*3600
        if t>=protocol['freeze_epoch']:observed[symbol][t]=None
    preliminary=session_coverage(observed,through)
    new=[d for d in preliminary['complete_sessions'] if d not in progress['last_scored_sessions']]
    availability=dict(status='waiting_new_completed_sessions',through_utc=datetime.fromtimestamp(through,timezone.utc).isoformat(),complete_sessions=preliminary['complete_sessions'],new_complete_sessions=len(new),minimum_new_sessions=5,scored_before=progress['last_scored_sessions'])
    atomic(folder/'availability.json',availability)
    if status_only or len(new)<5:
        source.close();print(json.dumps(availability));return
    batch=folder/'batches'/datetime.fromtimestamp(through,timezone.utc).strftime('%Y%m%dT%H%M%SZ');batch.mkdir(parents=True,exist_ok=False)
    snapshot=batch/'received_quotes.sqlite';dest=sqlite3.connect(snapshot)
    dest.execute('CREATE TABLE quotes(seq INTEGER PRIMARY KEY,symbol TEXT,raw_ms INTEGER,bid REAL,ask REAL,occurrence INTEGER,receipt_ms INTEGER)')
    cursor=source.execute('SELECT rowid,symbol,raw_ms,bid,ask,occurrence,receipt_ms FROM quotes WHERE receipt_ms>=? AND receipt_ms<=? ORDER BY rowid',(start_ms,end_ms))
    count=0
    while True:
        block=cursor.fetchmany(10000)
        if not block:break
        dest.executemany('INSERT INTO quotes VALUES(?,?,?,?,?,?,?)',block);count+=len(block)
    source.close();dest.commit();dest.close();db=read_only(snapshot)
    points={s:m.get('point',m['trade_tick_size']) for s,m in protocol['metadata'].items()}
    minutes,available,late=received_minutes(groups(db,start_ms,end_ms),protocol['offset_hours'],protocol['freeze_epoch'],points)
    coverage=session_coverage(minutes,through)
    if len([d for d in coverage['complete_sessions'] if d not in progress['last_scored_sessions']])<5:
        db.close();atomic(batch/'coverage_failure.json',coverage);raise ValueError('Finalized complete-minute coverage failed; no financial result accepted')
    all_lanes,meta,_,old_one,_=load(root)
    one={};base={n:all_lanes[n] for n in all_lanes if n in ['SPX15','NAS15']}
    warmup=json.loads((folder/'warmup_receipts.json').read_text())
    for symbol in protocol['offset_hours']:
        combined={b['t']:b for b in old_one[symbol]}
        combined.update({b['t']:b for b in warmup[symbol]});combined.update(minutes[symbol])
        one[symbol]=[b for _,b in sorted(combined.items())]
        meta[symbol].update(protocol['metadata'][symbol])
    for name,lane in base.items():
        symbol=lane['symbol'];base[name]=build_lane(symbol,15,one[symbol],aggregate(one[symbol],15),lane,True)
    variants={n:lanes for n,lanes in make_variants(base,one).items() if n in protocol['profiles']}
    books={(n,c):PaperBook({k:dict(v,signals={}) for k,v in lanes.items()},meta,dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True,direction_guard=True),COSTS[c],5000.) for n,lanes in variants.items() for c in ['standard','higher']}
    plans={};indices={}
    for name,lanes in variants.items():
        plans[name]=[];indices[name]=0
        for lane_name,lane in lanes.items():
            symbol=lane['symbol']
            for t,s in lane['signals'].items():
                if t<protocol['freeze_epoch'] or t>through:continue
                seen=max(available[symbol].get(m,protocol['freeze_epoch']) for m in range(int(t)-900,int(t),60))
                plans[name].append((seen,t,lane_name,s))
        plans[name].sort(key=lambda x:(x[0],x[1],0 if x[2]=='SPX15' else 1))
    nas_track={k:dict(seen=0,cash=5000.,peak=5000.,dd=0.) for k in books}
    for receipt,rows in groups(db,start_ms,end_ms):
        for name in variants:
            while indices[name]<len(plans[name]) and plans[name][indices[name]][0]<=receipt:
                _,_,lane,s=plans[name][indices[name]];indices[name]+=1
                for cost in ['standard','higher']:books[name,cost].enqueue(lane,s)
        for symbol in ['SPX500','NAS100']:
            path=[(r[2]/1000-protocol['offset_hours'][symbol]*3600,r[3],r[4]) for r in rows if r[1]==symbol]
            if not path:continue
            path.sort(key=lambda x:x[0]);source_at,bid,ask=path[-1];fresh=-1<=receipt-source_at<=5
            for key,b in books.items():
                b.received_path(symbol,receipt,bid,ask,path)
                b.quote(symbol,receipt,bid,ask,fresh=fresh,source_time=source_at)
                tr=nas_track[key]
                for f in b.fills[tr['seen']:]:
                    if f['strategy']=='NAS15':tr['cash']+=f['pnl']
                tr['seen']=len(b.fills);eq=tr['cash']
                for pos in b.positions.values():
                    if pos['lane']!='NAS15':continue
                    bp,ap,_=b.latest[pos['symbol']];_,mult,slip,fee=b.economics(pos['symbol'])
                    eq+=(((bp if pos['side']==1 else ap)-pos['side']*slip-pos['entry'])*pos['side']*mult-fee)*pos['quantity']
                tr['peak']=max(tr['peak'],eq);tr['dd']=max(tr['dd'],(tr['peak']-eq)/tr['peak'])
    db.close();results=[]
    first=datetime.fromtimestamp(protocol['freeze_epoch'],timezone.utc).astimezone(NY).date().isoformat();end=(datetime.fromtimestamp(through,timezone.utc).astimezone(NY).date()+timedelta(days=1)).isoformat()
    for (name,cost),b in books.items():
        b.finish()
        assert not b.positions,'Incomplete observed liquidation paths; no closed-account result accepted'
        r=b.result();r.update(profile=name,cost=cost,portfolio=metrics(b.fills,initial=5000.,first=first,end=end),nas15=metrics([f for f in b.fills if f['strategy']=='NAS15'],initial=5000.,first=first,end=end),nas15_contribution_quote_drawdown_pct=nas_track[name,cost]['dd']*100,
                             available_complete_sessions=coverage['complete_sessions'],scope='cumulative post-freeze prospective receipt-clock replay;overlapping batches are not independent repeats',actual_order_fills=False)
        results.append(r);atomic(batch/f'private_fills_{name}_{cost}.json',b.fills);atomic(batch/f'private_decisions_{name}_{cost}.json',b.decisions)
    atomic(batch/'results.json',results)
    atomic(batch/'completed.json',dict(protocol_sha256=digest(folder/'protocol.json'),quotes=count,quote_snapshot_sha256=digest(snapshot),late_quotes_not_revising_bars=late,covered_sessions=coverage['complete_sessions'],new_sessions=new,open_positions={f'{r["profile"]}/{r["cost"]}':r['open_positions'] for r in results},historical_warmup_not_financially_scored=True))
    atomic(folder/'progress.json',dict(status='waiting_new_completed_sessions',last_scored_sessions=coverage['complete_sessions'],last_batch=str(batch.relative_to(root))))
    print(json.dumps(dict(batch=str(batch),variants=len(results),new_complete_sessions=len(new),actual_order_fills=False)))


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--freeze',action='store_true');p.add_argument('--status',action='store_true');p.add_argument('--through-utc')
    args=p.parse_args();folder=args.root/'outputs'/FOLDER
    if args.freeze:freeze(args.root,folder);return
    protocol=verify(args.root,folder)
    through=datetime.fromisoformat(args.through_utc.replace('Z','+00:00')).timestamp() if args.through_utc else cutoff_now()
    if through>datetime.now(timezone.utc).timestamp():raise ValueError('Future cutoff is not observable')
    evaluate(args.root,folder,protocol,through,args.status)


if __name__=='__main__':main()
