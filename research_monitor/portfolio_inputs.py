"""Reconstruct the frozen three-lane inputs without any broker calls."""
import json
from .audited_run import read_bars
from .frequency_signals import signals
from .native_context import enrich_native
from .entry_quality_v2 import enrich
from .hourly_entry_quality import attach_hourly
from .nasdaq_native_signals import rsi_signals
from .preopen_sessions import load_sessions
from .replay_window import select_window


def load_lanes(root):
    folders={'NAS100':[root/'outputs/nas100_quote_data_v1'], 'SPX500':[root/'outputs/spx15_canonical_quote_data_v1',root/'outputs/spx15_direction_later_v1/data']}
    meta={'NAS100':json.loads((folders['NAS100'][0]/'metadata.json').read_text()),'SPX500':json.loads((root/'work/mt5_symbol_metadata.json').read_text())['SPX500']}
    for m in meta.values():m.update(assumed_margin_rate=.005,volume_max=1000.)
    lanes={}
    for symbol in ['SPX500','NAS100']:
        one=sum([read_bars(f/f'{symbol}_M1.csv','ny_dst_inferred') for f in folders[symbol]],[])
        native=sum([read_bars(f/f'{symbol}_M15.csv','ny_dst_inferred') for f in folders[symbol]],[])
        start,end,confirmation=(585,720,'both') if symbol=='SPX500' else (540,900,'control')
        base=signals(native,symbol,15,20,'none',end,'breakout',start)
        base=enrich(native,one,base,'beyond_prior_session') if symbol=='SPX500' else enrich_native(native,one,base,15)
        plans=attach_hourly(base,one);_,plans=select_window([],plans,'2025-12-15','2026-10-31')
        lanes['SPX15' if symbol=='SPX500' else 'NAS15']=dict(symbol=symbol,signals=plans,exits=[],rr=1.5,hypothesis='beyond_prior_session',quality='both',confirmation=confirmation,direction='long_only',start=start,end=end)
        if symbol=='NAS100':
            native=read_bars(folders[symbol][0]/'NAS100_M5.csv','ny_dst_inferred');plans,exits=rsi_signals(native,5);plans=attach_hourly(enrich_native(native,one,plans,5),one);_,plans=select_window([],plans,'2025-12-15','2026-10-31')
            lanes['NAS5']=dict(symbol=symbol,signals=plans,exits=exits,rr=None,hypothesis='baseline',quality='control',confirmation='control',direction='short_only',start=600,end=900)
    return lanes,meta,folders


def load_quotes(folders):return {symbol:load_sessions(paths) for symbol,paths in folders.items()}
