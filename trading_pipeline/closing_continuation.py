"""Card2 signal kernel v1.0.0. No fills or qualification; not wired into Engine v3.

Calendar data must identify actual previous regular sessions, including holidays.
This validates timezone/clock geometry, not the external calendar's truth.
"""
import math,statistics
from datetime import time
from zoneinfo import ZoneInfo
from .engine_v3 import utc,finite

NY=ZoneInfo('America/New_York')
VERSION='closing-half-hour-continuation-1.0.0'

def decide(bars,session,tick,decision_at):
 finite(tick)
 if tick<=0:raise ValueError('invalid_tick')
 if session.get('calendar_verified') is not True or not session.get('source_reference'):raise ValueError('verified_calendar_required')
 opened,closed,prior_close=(utc(session[k]) for k in ('open','close','previous_close'))
 local_open,local_close=opened.astimezone(NY),closed.astimezone(NY)
 if local_open.time()!=time(9,30) or local_close.time()!=time(16) or local_open.date()!=local_close.date():raise ValueError('short_or_invalid_regular_session')
 if prior_close>=opened or prior_close.astimezone(NY).time()!=time(16):raise ValueError('invalid_previous_regular_close')
 at=utc(decision_at)
 if at.astimezone(NY).time()!=time(15,30) or at.date()!=closed.date():return {'status':'outside_decision_time'}
 known=[b for b in bars if utc(b['end'])<=at and utc(b['available_at'])<=at]
 if any(utc(b['end'])<=utc(a['end']) for a,b in zip(known,known[1:])):raise ValueError('nonchronological_or_duplicate_bars')
 previous=[b for b in known if utc(b['end'])==prior_close]
 if len(previous)!=1:return {'status':'missing_previous_regular_close'}
 current=[b for b in known if opened<=utc(b['start']) and utc(b['end'])<=at]
 if len(current)<21 or utc(current[-1]['end'])!=at:return {'status':'insufficient_completed_warmup'}
 selected=current[-21:]
 for b in [previous[0]]+selected:
  finite(*(b[k] for k in ('open','high','low','close','volume')))
  if (utc(b['end'])-utc(b['start'])).total_seconds()!=300 or b['volume']<=0 or not 0<b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:raise ValueError('invalid_five_minute_bar')
  if b.get('contract')!=session['contract']:raise ValueError('cross_contract_signal_forbidden')
  if any(abs(b[k]/tick-round(b[k]/tick))>1e-6 for k in ('open','high','low','close')):raise ValueError('off_tick_bar')
 if any(utc(a['end'])!=utc(b['start']) for a,b in zip(selected,selected[1:])):return {'status':'warmup_gap'}
 atr=statistics.mean(max(b['high']-b['low'],abs(b['high']-a['close']),abs(b['low']-a['close'])) for a,b in zip(selected,selected[1:]))
 direction=1 if selected[-1]['close']>previous[0]['close'] else -1 if selected[-1]['close']<previous[0]['close'] else 0
 if not direction:return {'status':'zero_return_skip'}
 distance=math.ceil(atr/tick-1e-9)*tick
 if distance<=0:return {'status':'zero_atr_skip'}
 return dict(status='unqualified_signal_only',strategy=VERSION,contract=session['contract'],decision_at=decision_at,side=direction,stop_distance=distance,target=None,exit_at=session['close'],entry_expiry_seconds=60,minimum_processing_latency_seconds=1,reentry=False,broker_execution_enabled=False,execution_eligible=False)
