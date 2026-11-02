"""All raw family setups plus frozen session/confirmation rules;no fitting."""
import json
from collections import Counter
from datetime import datetime,timezone
from .portfolio_inputs import load_lanes
from .portfolio_discipline_rules import apply
from .audited_run import read_bars,NY
from .frequency_signals import signals
from .atlas_raw_rsi import rsi_signals
from .entry_quality_v2 import enrich
from .native_context import enrich_native
from .hourly_entry_quality import attach_hourly
from .native_data import aggregate
from .replay_window import select_window
from .atlas_metrics import weekdays


def build_lane(symbol,minutes,one,native,base,breakout=True):
    if breakout:
        raw=signals(native,symbol,minutes,20,'none',1439,'breakout',0)
        raw=enrich(native,one,raw,'beyond_prior_session') if symbol=='SPX500' else enrich_native(native,one,raw,minutes);exits=[]
    else:raw,exits=rsi_signals(native,minutes);raw=enrich_native(native,one,raw,minutes)
    raw=attach_hourly(raw,one);_,raw=select_window([],raw,'2025-12-15','2100-01-01');return dict(base,signals=raw,exits=exits)


def load(root):
    lanes,meta,folders=load_lanes(root);lanes=apply(lanes,'nas15_eff_after2');out={};coverage=[];warmup={}
    for symbol,paths in folders.items():
        one=sum([read_bars(p/f'{symbol}_M1.csv','ny_dst_inferred') for p in paths],[]);warmup[symbol]=one
        for name,lane in lanes.items():
            if lane['symbol']!=symbol:continue
            minutes=5 if name=='NAS5' else 15;native=aggregate(one,minutes);built=build_lane(symbol,minutes,one,native,lane,minutes==15)
            # The wide-universe version must preserve every registered existing setup exactly.
            selected={t:s for t,s in built['signals'].items() if lane['start']<=((lambda a:a.hour*60+a.minute)(datetime.fromtimestamp(t,timezone.utc).astimezone(NY)))<=lane['end'] and t in lane['signals']}
            assert selected==lane['signals'],(name,'rawuniverse changed frozen signal features')
            built['signals']={t:s for t,s in built['signals'].items() if datetime.fromtimestamp(t,timezone.utc).astimezone(NY).date().isoformat()<'2026-10-31'};out[name]=built
            counts=Counter()
            for b in native:
                at=datetime.fromtimestamp(b['t']+minutes*60,timezone.utc).astimezone(NY)
                if lane['start']<=at.hour*60+at.minute<=lane['end']:counts[str(at.date())]+=1
            for day in weekdays():coverage.append(dict(lane=name,date=day,scheduled_weekday_slots=(lane['end']-lane['start'])//minutes+1,observed_complete_bars=counts[day],unobserved_slots=max(0,(lane['end']-lane['start'])//minutes+1-counts[day]),qualification='Missing slots include venue closures and data gaps;unobservable setups are not inferred.'))
    return out,meta,folders,warmup,coverage
