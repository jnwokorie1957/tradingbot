"""Correct audit-only sparse quote omission;strictly preserve previous financial paths."""
import argparse,hashlib,heapq,json,copy
from pathlib import Path
from datetime import datetime,timezone
from .atlas_capture_inputs import load
from .atlas_capture_quotes_v2 import feasible_envelopes
from .portfolio_inputs import load_quotes
from .atlas_capture_core import PaperBook as LegacyBook
from .atlas_live_core import PaperBook as ApprovedBook
from .atlas_opportunity_study import COSTS
from .audited_run import NY


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root;base=root/'outputs/atlas_opportunity_v1';out=base/'corrected_audit_v2';out.mkdir(exist_ok=False)
    (out/'protocol.json').write_text(json.dumps(dict(registered_utc=datetime.now(timezone.utc).isoformat(),defect='Originalsparseauditretainedfirstentryquoteonlyafterfill-windowfilter. Someotherwisein-sessiondecisionswithdelayed15:01entrycouldbeauditedonlaterretainedquote,misclassifyingblockedwindowasmissingdata.',fix='Keepfirstdecisionandfirstentryquote forEVERY registeredsetup beforefill-window/affordabilitypruning. Position-pricepathsunchanged. StrictcompareallfinancialfillsandquoteDDbeforeacceptingcounts.',exposure='No strategy change,no optimization;completepricedecision auditcorrection. Existingrecords retained. Forwardreceiveddatadoesnotusehistoricalpruner.',code_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['atlas_frequency_reconcile.py','atlas_capture_quotes_v2.py','atlas_capture_core.py','atlas_live_core.py']}),indent=2));(out/'source').mkdir()
    for n in ['atlas_capture_quotes_v2.py','atlas_capture_core.py','atlas_live_core.py']:(out/'source'/n).write_bytes(Path(__file__).with_name(n).read_bytes())
    lanes,meta,folders,_,_=load(root);sessions=load_quotes(folders);cache={};rows=[]
    for kind,cost in [('frozen','standard'),('frozen','higher'),('approved5000','standard'),('approved5000','higher'),('approved5000','severe')]:
        cfg=COSTS[cost];delay=cfg['exit_delay']
        if delay not in cache:
            cache[delay]={}
            for symbol in sessions:
                union={}
                for name,l in lanes.items():
                    if l['symbol']!=symbol:continue
                    for t,s in l['signals'].items():
                        a=datetime.fromtimestamp(t,timezone.utc).astimezone(NY)
                        if l['start']<=a.hour*60+a.minute<=l['end']:union[(t,name)]=s
                cache[delay][symbol],_=feasible_envelopes(sessions[symbol],union,meta[symbol],False,540,900,exit_delay=delay)
        book=LegacyBook(lanes,meta,{},cfg,500.) if kind=='frozen' else ApprovedBook(lanes,meta,dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True,direction_guard=True),cfg,5000.)
        def stream(symbol,data):
            for day,q,offset in data:
                for x in q:yield(float(x['time_msc'])/1000-offset*3600,0 if symbol=='SPX500' else 1,symbol,float(x['bid']),float(x['ask']))
        for t,_,symbol,bid,ask in heapq.merge(*(stream(s,q) for s,q in cache[delay].items()),key=lambda x:(x[0],x[1])):book.quote(symbol,t,bid,ask)
        book.finish();prior=base if kind=='frozen' else base/'approved5000';r=next(r for r in json.loads((prior/'results.json').read_text()) if r['cost']==cost and (kind!='frozen' or r['name']=='frozen'));old=json.loads((prior/f'fills_{r["ledger"]}.json').read_text());assert len(old)==len(book.fills) and old==book.fills,(kind,cost,'financial path changed');assert abs(book.dd*100-r['quote_drawdown_pct'])<1e-7
        key=f'{len(rows)+1:02d}';(out/f'fills_{key}.json').write_text(json.dumps(book.fills,indent=2));(out/f'rejections_{key}.json').write_text(json.dumps(book.decisions,indent=2));row=dict(kind=kind,cost=cost,ledger=key,financial_result=r,exact_fills=len(old),quoteDD_matched=True);rows.append(row);(out/'results.json').write_text(json.dumps(rows,indent=2));(out/'worker.json').write_text(json.dumps(dict(status='running',completed=len(rows),total=5)));print(json.dumps(dict(kind=kind,cost=cost,exact_fills=len(old),counts_reconciled=len(book.decisions))),flush=True)
    (out/'completed.json').write_text(json.dumps(dict(cases=5,all_financial_paths_unchanged=True,audit_only_correction=True)));(out/'worker.json').write_text(json.dumps(dict(status='completed',completed=5,total=5)))


if __name__=='__main__':main()
