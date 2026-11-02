"""Development-only v2 research. No further optimization on reused later dates."""
import argparse
import hashlib
import heapq
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from .atlas_capture_inputs import load
from .atlas_capture_quotes_v2 import feasible_envelopes
from .atlas_live_core import PaperBook
from .atlas_metrics import metrics
from .atlas_opportunity_study import COSTS
from .atlas_portfolio_controller import APPROVED
from .atlas_nas15_regimes import PROFILES, make_variants
from .audited_run import NY
from .portfolio_inputs import load_quotes


def snapshot(b, name, cost, nas_dd):
    def trim(m):return {k:v for k,v in m.items() if not k.startswith('daily_')}
    return dict(profile=name,cost=cost,nas15=trim(metrics([f for f in b.fills if f['strategy']=='NAS15'],initial=5000.,end='2026-06-01')),
                portfolio=trim(metrics(b.fills,initial=5000.,end='2026-06-01')),
                portfolio_quote_drawdown_pct=b.dd*100,nas15_contribution_quote_drawdown_pct=nas_dd*100)


def select(rows):
    lookup={(r['profile'],r['cost']):r for r in rows};result=[]
    for name in PROFILES[1:]:
        failures=[]
        for c in ['standard','higher']:
            r,b=lookup[name,c],lookup['control',c]
            if r['nas15']['trades']<max(15,.75*b['nas15']['trades']):failures.append(c+': sample/capture')
            if r['nas15']['net_pnl']<b['nas15']['net_pnl']-1e-7:failures.append(c+': NAS profit decreases')
            if r['portfolio']['net_pnl']<b['portfolio']['net_pnl']-1e-7:failures.append(c+': portfolio profit decreases')
            if r['portfolio_quote_drawdown_pct']>b['portfolio_quote_drawdown_pct']+1e-8:failures.append(c+': portfolio drawdown increases')
            if r['nas15_contribution_quote_drawdown_pct']>b['nas15_contribution_quote_drawdown_pct']+1e-8:failures.append(c+': NAS contribution drawdown increases')
            if r['nas15']['win_rate'] is None or r['nas15']['win_rate']<=60:failures.append(c+': win rate not above60%')
        result.append(dict(profile=name,development_gate_pass=not failures,failures=failures,independently_validated=False))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root
    out=root/'outputs/atlas_nas15_regime_v2';out.mkdir(exist_ok=False)
    protected=[root/'outputs/atlas_two_strategy_5000_v1/results.json',root/'outputs/atlas_nas15_winrate_v1/results.json',root/'outputs/atlas_opportunity_v1/approved5000/results.json']
    hashes={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in protected}
    protocol=dict(registered_utc=datetime.now(timezone.utc).isoformat(),profiles=PROFILES,period=['2025-12-15','2026-05-31'],risk=APPROVED,
                  change='Only NAS15 input direction/regime hypotheses. Add short breakouts; add shorts only when strongclose65 and ER>=.30; completedUTC4hEMA20 alignment for longs; same4h alignment both directions. No parameter grid, no exit/risk changes.',
                  selection='Strict100% NAS and portfolio profit retention and no NAS-contribution or portfolio drawdown increase at both costs. At least15 NAS fills,75% baseline capture and WR>60 required. All variants are frozen for future validation; no later-history optimization.',
                  limitations='Development-only on previously exposed dates. New independent observations required; no candidate deployment.',protected_hashes=hashes)
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    (out/'worker.json').write_text(json.dumps(dict(pid=os.getpid(),phase='loading',completed=0,total=10)))
    all_lanes,meta,folders,one,_=load(root);base={n:all_lanes[n] for n in all_lanes if n in ['SPX15','NAS15']};variants=make_variants(base,one)
    sessions={s:[x for x in data if x[0]<'2026-06-01'] for s,data in load_quotes(folders).items()};working={}
    for symbol,data in sessions.items():
        union={}
        for n,lanes in variants.items():
            for name,lane in lanes.items():
                if lane['symbol']!=symbol:continue
                for t,s in lane['signals'].items():
                    at=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
                    if lane['start']<=at.hour*60+at.minute<=lane['end']:union[t,n,name]=s
        working[symbol],_=feasible_envelopes(data,union,meta[symbol],False,540,900)
    books={(n,c):PaperBook(lanes,meta,dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True,direction_guard=True),COSTS[c],5000.) for n,lanes in variants.items() for c in ['standard','higher']}
    trackers={k:dict(seen=0,cash=5000.,peak=5000.,dd=0.) for k in books}
    def stream(symbol,data):
        for day,q,offset in data:
            for x in q:yield float(x['time_msc'])/1000-offset*3600,0 if symbol=='SPX500' else 1,symbol,float(x['bid']),float(x['ask'])
    for count,(t,_,symbol,bid,ask) in enumerate(heapq.merge(*(stream(s,q) for s,q in working.items()),key=lambda x:(x[0],x[1])),1):
        for key,b in books.items():
            b.quote(symbol,t,bid,ask);tr=trackers[key]
            for f in b.fills[tr['seen']:]:
                if f['strategy']=='NAS15':tr['cash']+=f['pnl']
            tr['seen']=len(b.fills);equity=tr['cash']
            for pos in b.positions.values():
                if pos['lane']!='NAS15':continue
                bp,ap,_=b.latest[pos['symbol']];_,mult,slip,fee=b.economics(pos['symbol'])
                equity+=(((bp if pos['side']==1 else ap)-pos['side']*slip-pos['entry'])*pos['side']*mult-fee)*pos['quantity']
            tr['peak']=max(tr['peak'],equity);tr['dd']=max(tr['dd'],(tr['peak']-equity)/tr['peak'])
        if count%300000==0:
            state=dict(pid=os.getpid(),phase='development_only',observations=count,completed=0,total=10);(out/'worker.json').write_text(json.dumps(state));print(json.dumps(state),flush=True)
    rows=[]
    for (n,c),b in books.items():
        assert not b.positions
        rows.append(snapshot(b,n,c,trackers[n,c]['dd']))
        (out/f'private_fills_{n}_{c}.json').write_text(json.dumps(b.fills,indent=2))
        (out/f'private_decisions_{n}_{c}.json').write_text(json.dumps(b.decisions,indent=2))
        if n=='control':
            prior=json.loads((root/f'outputs/atlas_nas15_winrate_v1/dev_fills_control_{c}.json').read_text());assert b.fills==prior
    (out/'results.json').write_text(json.dumps(rows,indent=2));(out/'decision.json').write_text(json.dumps(select(rows),indent=2))
    for x in protected:assert hashlib.sha256(x.read_bytes()).hexdigest()==hashes[str(x.relative_to(root))]
    (out/'completed.json').write_text(json.dumps(dict(cases=10,baseline_fills_exact=True,benchmarks_preserved=True,risk_code_changed=False,independently_validated=False)))
    (out/'worker.json').write_text(json.dumps(dict(pid=os.getpid(),phase='completed',completed=10,total=10)))
    print(json.dumps(rows),flush=True)


if __name__=='__main__':main()
