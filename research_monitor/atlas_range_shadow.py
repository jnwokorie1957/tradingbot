"""Development-only complementary3m hypothesis under approved5000capital. Never deployed."""
import argparse,hashlib,heapq,json
from pathlib import Path
from datetime import datetime,timezone
from .atlas_capture_inputs import load,build_lane
from .atlas_live_core import PaperBook
from .atlas_capture_quotes import feasible_envelopes
from .portfolio_inputs import load_quotes
from .native_data import aggregate
from .atlas_opportunity_study import COSTS
from .atlas_metrics import metrics,local_day


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root;out=root/'outputs/atlas_opportunity_v1/range_shadow5000';out.mkdir(exist_ok=False)
    (out/'protocol.json').write_text(json.dumps(dict(registered_utc=datetime.now(timezone.utc).isoformat(),hypothesis='ShortNASDAQ3mRSI2/SMA200duringrange-regime(absprior20directionalefficiency<.30). Threshold reused from existingcontext,notfit;ATRstop/nativeRSIexitunchanged.',purpose='Complementarytimeframe/rangeregime diagnostic ondevelopmentonly. Same5000capital/0.5percentor25pertrade/1percenttotalapprovedcontroller. Never addedto3laneforwardbook;noindependentvalidation.',period=['2025-12-15','2026-05-31'],costs=['standard','higher'],source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
    lanes,meta,folders,one,_=load(root);native=aggregate(one['NAS100'],3);base=build_lane('NAS100',3,one['NAS100'],native,lanes['NAS5'],False);base['signals']={t:s for t,s in base['signals'].items() if local_day(t)<'2026-06-01' and abs(s.get('features',{}).get('directional_efficiency',2.))<.3};sessions=load_quotes({'NAS100':folders['NAS100']})['NAS100'];sessions=[s for s in sessions if s[0]<'2026-06-01'];plans={t:s for t,s in base['signals'].items() if s['side']==-1};thin,_=feasible_envelopes(sessions,plans,meta['NAS100'],False,600,900);rows=[]
    for cost in ['standard','higher']:
        b=PaperBook({'NAS3':base},meta,dict(atlas5000=True,allow_multiple=True,defer_busy_gate=True),COSTS[cost],5000.)
        for day,q,offset in thin:
            for x in q:b.quote('NAS100',float(x['time_msc'])/1000-offset*3600,float(x['bid']),float(x['ask']))
        b.finish();r=b.result();r.update(cost=cost,metrics=metrics(b.fills,initial=5000.,end='2026-06-01'),independent_validation=False,forward_deployed=False);(out/f'fills_{cost}.json').write_text(json.dumps(b.fills,indent=2));rows.append(r);(out/'results.json').write_text(json.dumps(rows,indent=2));print(json.dumps({k:r[k] for k in ['cost','trades','net_pnl','win_rate','quote_drawdown_pct']}),flush=True)


if __name__=='__main__':main()
