"""One bounded development-only cycle; no network, terminal or live orders."""
import argparse,json,os,shutil,traceback
from pathlib import Path
from collections import Counter
from atlas_exit_research.data import Market,write,sha,stamp
from atlas_exit_research.engine import Account
from atlas_exit_research.audit import reconcile
from atlas_exit_research.control_check import inputs
from atlas_exit_research.run import describe,SPLIT
from research_monitor.atlas_capture_inputs import load
from research_monitor.risk_review import RiskReview
from research_monitor.atlas_portfolio_controller import APPROVED
from research_monitor.atlas_opportunity_study import COSTS
from .signals import generate,RULES,SOURCES


class DiscoveryBook(Account):
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw)
        # New hypotheses have their own registered signal rules, no inherited
        # old-strategy recovery filter. The approved portfolio allocator remains.
        self.guards={n:RiskReview('baseline') for n in self.lanes}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--status',action='store_true');a=p.parse_args();root=a.root.resolve();out=root/'outputs/atlas_research_pipeline_v1/cycles/001';state=root/'work/tradingbot/local-results/atlas-research-pipeline';state.mkdir(parents=True,exist_ok=True)
    if a.status:
        print((out/'progress.json').read_text() if(out/'progress.json').exists()else json.dumps({'status':'not_started'}));return
    out.mkdir(parents=True,exist_ok=False);lock=state/'cycle.lock.json';handle=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(handle,json.dumps(dict(pid=os.getpid(),started_utc=stamp(),cycle='001')).encode());os.close(handle)
    try:
        protected={str(p.relative_to(root)):sha(p) for p in [root/'outputs/atlas_exit_management_v1/baseline.json',root/'outputs/atlas_two_strategy_exits_v1/results.json',root/'outputs/atlas_pair_holding_v1/results.json',root/'work/tradingbot/research_monitor/atlas_portfolio_controller.py',root/'work/tradingbot/atlas_exit_research/engine.py']};protocol=dict(registered_utc=stamp(),cycle='001',families=RULES,primary_sources=SOURCES,adaptation='CFD price-only adaptations;no exchange volume/orderbook/liquidity claims. Stops and RR are our fixed implementations,not reported paper results.',instruments=['NAS100','SPX500'],timeframes={'late_momentum':5,'gap_reversal':1},RR={'late_momentum':2.,'gap_reversal':1.5},risk=APPROVED,costs=COSTS,development=['2025-12-15','2026-05-31'],later_data='Not financially evaluated in this cycle. All older prices already exposed; independent validation unavailable.',financial_cases=12,selection='>=30closedtrades percost, net>0,PF>=1.1,fullquoteDD<10,noincompletepaths,positive lower95percent weeklyblockbootstrap netR percost. No mandatory winrate. Retain fixedhypothesis as unvalidated forwardcandidate only if all gates pass. Never autoadd to portfolio.',trial_policy='One fixed implementation per family/asset;no parameter grid/refit after outcomes. Archive all failures. No repeat on same identity; new cycle requires new protocol and semantic duplicate review.',future_holdout='Financially scored future observations begin only after complete prospective evaluator+profile freeze. Newly acquired IBKR history stays quarantined, with contract/roll/feed/cost model separately verified before unsealing.',protected_sha256=protected,sources={f.name:sha(f) for f in Path(__file__).parent.glob('*.py')});write(out/'protocol.json',protocol);(out/'source').mkdir()
        for f in Path(__file__).parent.glob('*.py'):shutil.copy2(f,out/'source'/f.name)
        write(out/'progress.json',dict(status='running',pid=os.getpid(),phase='load',completed=0,total=12));_,meta,_,warmup,_=load(root);archive=root/'outputs/atlas_exit_management_v1';market=Market(root,archive);results=[];quality={};identities={}
        for symbol in ['NAS100','SPX500']:
            plans,q=generate(warmup[symbol],meta[symbol]['trade_tick_size']);quality[symbol]=q
            for family,raw in plans.items():
                import hashlib
                plans_dev={t:s for t,s in raw.items() if s['decision']<__import__('datetime').datetime.fromisoformat(SPLIT).replace(tzinfo=__import__('zoneinfo').ZoneInfo('America/New_York')).timestamp()};name=symbol+'_'+family;identities[name]=hashlib.sha256(json.dumps(plans_dev,sort_keys=True).encode()).hexdigest();rr=protocol['RR'][family];lane=dict(symbol=symbol,signals=plans_dev,exits=[],rr=rr,hypothesis='baseline',quality='control',confirmation='control',direction='both',start=0,end=1439,minutes=protocol['timeframes'][family])
                for cost in COSTS:
                    write(out/'progress.json',dict(status='running',pid=os.getpid(),phase='development',candidate=name,cost=cost,completed=len(results),total=12));book=DiscoveryBook(market,{name:lane},meta,COSTS[cost],{name:'original'});book.run_to(SPLIT);account=book.result();assert not account['open_positions'] and not account['incomplete_paths'];audit=reconcile(market,book.fills,meta,COSTS[cost],account);m=describe(book,end=SPLIT);regimes={}
                    for f in book.fills:
                        signal=next(s for s in plans_dev.values() if abs(s['entry_at']-next(d['entry_at'] for d in book.decisions if d['id']==f['id']))<.0001);key=signal['features']['preentry_regime'];r=regimes.setdefault(key,dict(trades=0,net_pnl=0.));r['trades']+=1;r['net_pnl']+=f['pnl']
                    key=name+'_'+cost;r=dict(candidate=name,family=family,symbol=symbol,timeframe=lane['minutes'],cost=cost,account=account,metrics=m,preentry_regimes=regimes,audit={k:v for k,v in audit.items() if k!='curve'},independent_validation=False);results.append(r);write(out/f'private_fills_{key}.json',book.fills);write(out/f'private_decisions_{key}.json',book.decisions);write(out/'results.json',results)
        write(out/'signal_identity.json',identities);write(out/'data_quality.json',quality);decisions=[]
        for candidate in sorted({r['candidate'] for r in results}):
            reasons=[]
            for r in [x for x in results if x['candidate']==candidate]:
                m=r['metrics'];cost=r['cost'];ci=m['weekly_block_bootstrap_net_R_95pct']
                if m['trades']<30:reasons.append(cost+': fewer than30 trades')
                if m['net_pnl']<=0:reasons.append(cost+': net notpositive')
                if(m['profit_factor']or 0)<1.1:reasons.append(cost+': PF below1.1')
                if r['account']['quote_drawdown_pct']>=10:reasons.append(cost+': DD>=10')
                if not ci or ci[0]<=0:reasons.append(cost+': uncertainty includesnonpositive netR')
            decisions.append(dict(candidate=candidate,status='FORWARD_ELIGIBLE_UNVALIDATED' if not reasons else 'REJECTED_OR_INSUFFICIENT',reasons=reasons,promotion=False))
        assert all(sha(root/k)==v for k,v in protected.items());write(out/'decisions.json',decisions);write(out/'completed.json',dict(completed_utc=stamp(),cases=12,all_originals_preserved=True,all_ledgers_reconciled=True,independent_validation=False,promotion=False));write(out/'progress.json',dict(status='completed',completed=12,total=12));print(json.dumps(dict(completed=12,candidates=decisions)),flush=True)
    except BaseException:
        write(out/'failure.json',dict(failed_utc=stamp(),traceback=traceback.format_exc(),rules_changed=False));write(out/'progress.json',dict(status='failed',pid=os.getpid()));raise
    finally:lock.unlink(missing_ok=True)


if __name__=='__main__':main()
