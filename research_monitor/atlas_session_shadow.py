"""One predeclared session-boundary counterfactual;no active forward change."""
import argparse,hashlib,heapq,json,os
from pathlib import Path
from datetime import datetime,timezone
from .atlas_capture_inputs import load
from .portfolio_inputs import load_quotes
from .atlas_capture_quotes import feasible_envelopes
from .atlas_live_core import PaperBook
from .atlas_portfolio_controller import APPROVED
from .atlas_opportunity_study import COSTS,frequencies
from .atlas_metrics import metrics
from .audited_run import NY


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root;out=root/'outputs/atlas_opportunity_v1/session_shadow5000';out.mkdir(exist_ok=False)
    (out/'protocol.json').write_text(json.dumps(dict(registered_utc=datetime.now(timezone.utc).isoformat(),settings=APPROVED,source='Oneboundedhypothesisfromrejectionledger,not profit-selectedthresholds',scope='PreviouslyexposedDec15-Oct30;UNVALIDATED. No changes toactiveforwardcohort.',rules='SPX15producerallowsnooncompletedbar,but60seconddelaymakes12:01fillfailcurrent12:00fillgate. Allowonlyone-minuteSPXfillgrace;native15mbarsaddnonewsignalbetween12:00-12:01. Same1.5R,naturalstop,expiry,allotherfilters and5000controller. Do not generalizeall-daywindowloosening.',costs=COSTS,code_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['atlas_live_core.py','atlas_portfolio_controller.py','atlas_capture_inputs.py','atlas_capture_quotes.py']}),indent=2));state=dict(pid=os.getpid(),status='running',completed=0,total=3);(out/'worker.json').write_text(json.dumps(state));lanes,meta,folders,_,_=load(root);lanes['SPX15']['end']=721;sessions=load_quotes(folders);cache={};rows=[]
    for cost in ['standard','higher','severe']:
        cfg=COSTS[cost];delay=cfg['exit_delay']
        if delay not in cache:
            cache[delay]={}
            for symbol in sessions:
                union={}
                for name,l in lanes.items():
                    if l['symbol']!=symbol:continue
                    for t,s in l['signals'].items():
                        at=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
                        if l['start']<=at.hour*60+at.minute<=l['end']:union[(t,name)]=s
                cache[delay][symbol],_=feasible_envelopes(sessions[symbol],union,meta[symbol],False,540,900,exit_delay=delay)
        book=PaperBook(lanes,meta,dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True,direction_guard=True),cfg,5000.)
        def stream(symbol,sessions):
            for day,q,offset in sessions:
                for x in q:yield(float(x['time_msc'])/1000-offset*3600,0 if symbol=='SPX500' else 1,symbol,float(x['bid']),float(x['ask']))
        for t,_,symbol,bid,ask in heapq.merge(*(stream(s,q) for s,q in cache[delay].items()),key=lambda x:(x[0],x[1])):book.quote(symbol,t,bid,ask)
        book.finish();r=book.result();assert not book.positions;r.update(cost=cost,metrics=metrics(book.fills,initial=5000.),per_strategy={n:metrics([f for f in book.fills if f['strategy']==n],initial=5000.) for n in lanes},frequency=frequencies(book),independent_validation=False)
        key=f'{len(rows)+1:02d}';r['ledger']=key;(out/f'fills_{key}.json').write_text(json.dumps(book.fills,indent=2));(out/f'rejections_{key}.json').write_text(json.dumps(book.decisions,indent=2));rows.append(r);(out/'results.json').write_text(json.dumps(rows,indent=2));state.update(completed=len(rows),cost=cost);(out/'worker.json').write_text(json.dumps(state));print(json.dumps({k:r[k] for k in ['cost','net_pnl','trades','win_rate','quote_drawdown_pct','max_open_risk']}),flush=True)
    (out/'completed.json').write_text(json.dumps(dict(cases=3,policy_enforced=True,independently_validated=False,benchmark_modified=False)));state['status']='completed';(out/'worker.json').write_text(json.dumps(state))


if __name__=='__main__':main()
