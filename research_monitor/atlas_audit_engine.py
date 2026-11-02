"""Frozen-rule audit observer and adverse execution scenarios. No broker transport."""
import heapq
import numpy as np
from collections import Counter
from datetime import datetime, timezone
from .audited_run import up, down, NY
from .risk_review import RiskReview
from .entry_quality_v2 import reject
from .hourly_entry_quality import reject_quality
from .confirmation_quality import reject_confirmation
from .portfolio_discipline_rules import reject_state


def replay(sessions_by_symbol, lanes, metadata, stress=False, open_risk_cap=25.,scenario=None,capture=False):
    """Lane order breaks simultaneous admission ties. Gross margin, no offsets."""
    if open_risk_cap not in (25., 75.):
        raise ValueError('Unregistered shared risk budget')
    scenario=scenario or dict(spread=1.5 if stress else 1.,fee=12. if stress else 6.,slip_ticks=2 if stress else 1,exit_delay=0.,margin_multiplier=1.)
    symbol_ids={s:i for i,s in enumerate(sorted(sessions_by_symbol))}
    trace=np.empty(sum(len(q) for sessions in sessions_by_symbol.values() for _,q,_ in sessions),dtype=[('t','f8'),('symbol','i1'),('bid','f8'),('ask','f8'),('cash','f8'),('equity','f8')]) if capture else None
    admissions=[]
    cash = peak = 500.
    dd = 0.
    fills, monthly = [], {}
    portfolio_history=[]
    positions, latest = {}, {}
    pending, busy, indices, exit_indices, last_exit, guards, events, exits = {}, {}, {}, {}, {}, {}, {}, {}
    skips = {name: Counter() for name in lanes}
    max_risk = max_margin = 0.
    max_positions = observations = overlapping_entries = 0
    active_month = None
    def stream(symbol, sessions):
        for day, quotes, offset in sessions:
            for q in quotes:
                yield (float(q['time_msc']) / 1000 - offset * 3600, symbol, day, float(q['bid']), float(q['ask']))
    for name, lane in lanes.items():
        pending[name] = None; busy[name] = -1.; indices[name] = exit_indices[name] = 0
        last_exit[name] = {1: float('-inf'), -1: float('-inf')}
        guards[name] = RiskReview('recovery_trend')
        events[name] = sorted(lane['signals'].items()); exits[name] = sorted(lane.get('exits', []))
    def economics(symbol):
        m = metadata[symbol]; tick = m['trade_tick_size']
        return tick, m['trade_tick_value_loss'] / tick, tick * scenario['slip_ticks'], scenario['fee']
    def equity():
        value = cash
        for name, p in positions.items():
            bid, ask, _ = latest[p['symbol']]
            _, mult, slip, fee = economics(p['symbol'])
            executable = bid if p['side'] == 1 else ask
            value += ((executable - p['side'] * slip - p['entry']) * p['side'] * mult - fee) * p['quantity']
        return value
    def close(name, price, t, why):
        nonlocal cash
        p = positions.pop(name); _, mult, slip, fee = economics(p['symbol'])
        fill = price - p['side'] * slip
        pnl = ((fill - p['entry']) * p['side'] * mult - fee) * p['quantity']
        cash += pnl; guards[name].exited(pnl, t); busy[name] = t
        portfolio_history.append((t,pnl))
        fills.append(dict(strategy=name, symbol=p['symbol'], entry_at=p['at'], exit_at=t, side=p['side'], quantity=p['quantity'], entry=p['entry'], exit=fill, stop=p['stop'], target=p['target'], pnl=pnl, reason=why, planned_risk=p['risk'], entry_margin=p['margin'],entry_event=p['entry_event'],exit_event=observations))
    streams = [stream(symbol, sessions) for symbol, sessions in sessions_by_symbol.items()]
    last_t = float('-inf')
    for t, symbol, day, bid, ask in heapq.merge(*streams, key=lambda x: (x[0], 0 if x[1] == 'SPX500' else 1, x[1])):
        if t < last_t: raise ValueError('Out-of-order account observations')
        last_t = t; observations += 1
        ask = bid + (ask - bid) * scenario['spread']
        latest[symbol] = (bid, ask, t)
        month = day[:7]
        if month != active_month:
            if active_month is not None: monthly[active_month]['ending_balance'] = cash
            active_month = month; monthly[month] = dict(starting_balance=cash, ending_balance=cash, trades=0)
        local = datetime.fromtimestamp(t, timezone.utc).astimezone(NY); clock = local.hour * 60 + local.minute
        for name, lane in lanes.items():
            if lane['symbol'] != symbol: continue
            guard = guards[name]; guard.session_start(day)
            while indices[name] < len(events[name]) and events[name][indices[name]][0] <= t:
                decision, signal = events[name][indices[name]]; indices[name] += 1
                if name not in positions and decision > busy[name]: pending[name] = dict(signal)
            while exit_indices[name] < len(exits[name]) and exits[name][exit_indices[name]][0] <= t:
                when, side = exits[name][exit_indices[name]]; last_exit[name][side] = when; exit_indices[name] += 1
            s = pending[name]
            if s and t >= s['entry_at']:
                reason = None
                if t - s['entry_at'] > 5: reason = 'no_quote_within_5s'
                elif not lane['start'] <= clock <= lane['end']: reason = 'entry_outside_window'
                elif name not in positions:
                    meta = metadata[symbol]; tick, mult, slip, fee = economics(symbol); side = s['side']
                    entry = (ask if side == 1 else bid) + side * slip
                    if 'stop_distance' in s: distance = up(s['stop_distance'], tick); stop = entry - side * distance
                    else: stop = down(s['stop'], tick) if side == 1 else up(s['stop'], tick); distance = side * (entry - stop)
                    executable = bid if side == 1 else ask
                    if distance < tick - 1e-8 or (executable <= stop if side == 1 else executable >= stop): reason = 'invalid_or_breached_stop'
                    elif reject(lane['hypothesis'], s, entry, distance, lane['rr'] if lane['rr'] is not None else 1.5): reason = reject(lane['hypothesis'], s, entry, distance, lane['rr'] if lane['rr'] is not None else 1.5)
                    elif lane['direction'] == 'long_only' and side != 1: reason = 'short_entry_disabled'
                    elif lane['direction'] == 'short_only' and side != -1: reason = 'long_entry_disabled'
                    elif reject_quality(lane['quality'], s, entry): reason = reject_quality(lane['quality'], s, entry)
                    elif reject_confirmation(lane['confirmation'], s): reason = reject_confirmation(lane['confirmation'], s)
                    elif reject_state(lane,s,guard,t,portfolio_history):reason=reject_state(lane,s,guard,t,portfolio_history)
                    elif guard.entry_reason(s, ask - bid, slip, distance): reason = 'recovery_trend_not_aligned'
                    else:
                        perlot = (distance + slip) * mult + fee
                        margin_perlot = entry * meta.get('trade_contract_size', 100.) * meta.get('assumed_margin_rate', .005) * scenario.get('margin_multiplier',1.)
                        used_risk = sum(p['risk'] for p in positions.values()); used_margin = sum(p['margin'] for p in positions.values())
                        available_risk = max(0., min(guard.cap(cash), open_risk_cap - used_risk, cash))
                        # Do not finance new positions with unrealized gains. Gross entry margin stays reserved.
                        available_margin = max(0., min(cash, equity()) - used_margin)
                        quantity = down(min(available_risk / perlot, available_margin / margin_perlot, meta.get('volume_max', 1000.)), meta['volume_step'])
                        if quantity < meta['volume_min'] - 1e-8:
                            reason = 'shared_open_risk_limit' if (open_risk_cap - used_risk) < min(guard.cap(cash), cash) and available_risk < perlot * meta['volume_min'] - 1e-8 else 'shared_margin_limit' if available_margin < margin_perlot * meta['volume_min'] - 1e-8 else 'minimum_lot_above_lane_risk'
                        else:
                            reward = down(lane['rr'] * distance, tick) if lane['rr'] is not None else None
                            if positions: overlapping_entries += 1
                            admissions.append(dict(strategy=name,t=t,event=observations,used_risk=used_risk,new_risk=perlot*quantity,available_margin=available_margin,new_margin=margin_perlot*quantity,lane_cap=guard.cap(cash),quantity=quantity))
                            positions[name] = dict(symbol=symbol, side=side, entry=entry, stop=stop, target=entry + side * reward if reward is not None else None, quantity=quantity, at=t, expiry=min(s.get('expiry_at', t + 3600), s.get('deadline', float('inf'))), risk=perlot * quantity, margin=margin_perlot * quantity,entry_event=observations,pending_exit=None)
                            guard.entered()
                            max_risk = max(max_risk, sum(p['risk'] for p in positions.values())); max_margin = max(max_margin, sum(p['margin'] for p in positions.values())); max_positions = max(max_positions, len(positions))
                            if max_risk > open_risk_cap + 1e-7: raise AssertionError('Shared open-risk cap exceeded')
                if reason: skips[name][reason] += 1
                pending[name] = None
            if name in positions:
                p = positions[name]; side = p['side']; executable = bid if side == 1 else ask
                reason=None;price=executable
                if p['pending_exit']:
                    if t>=p['pending_exit']['available_at']:close(name,executable,t,p['pending_exit']['reason']+'_delayed')
                else:
                    if executable <= p['stop'] if side == 1 else executable >= p['stop']:reason='stop_quote'
                    elif t >= p['expiry']:reason='time_exit_quote'
                    elif last_exit[name][side] >= p['at']:reason='indicator_exit_quote'
                    elif p['target'] is not None and (executable >= p['target'] if side == 1 else executable <= p['target']):reason='target_quote';price=p['target']
                    if reason:
                        if scenario.get('exit_delay',0)>0:p['pending_exit']=dict(available_at=t+scenario['exit_delay'],reason=reason)
                        else:close(name,price,t,reason)
        marked = equity(); peak = max(peak, marked); dd = max(dd, (peak - marked) / peak)
        if capture:trace[observations-1]=(t,symbol_ids[symbol],bid,ask,cash,marked)
        monthly[month]['ending_balance'] = cash
    for month, row in monthly.items():
        selected = [f for f in fills if datetime.fromtimestamp(f['exit_at'], timezone.utc).astimezone(NY).strftime('%Y-%m') == month]
        row.update(trades=len(selected), net_pnl=sum(f['pnl'] for f in selected), return_pct=100 * (row['ending_balance'] / row['starting_balance'] - 1))
    wins = sum(f['pnl'] > 0 for f in fills)
    breakdown = {name: dict(trades=sum(f['strategy'] == name for f in fills), net_pnl=sum(f['pnl'] for f in fills if f['strategy'] == name)) for name in lanes}
    if abs(cash - 500 - sum(f['pnl'] for f in fills)) > 1e-7: raise AssertionError('Ledger/account reconciliation failed')
    return dict(status='completed' if not positions else 'incomplete', starting_balance=500., ending_balance=cash, net_pnl=cash - 500, return_pct=100 * (cash / 500 - 1), quote_marked_drawdown_pct=dd * 100, outcomes=len(fills), win_rate=100 * wins / len(fills) if fills else None, max_open_planned_risk=max_risk, max_gross_entry_margin=max_margin, max_simultaneous_positions=max_positions, overlapping_entries=overlapping_entries, observed_quotes=observations, skips={name: dict(c) for name, c in skips.items()}, breakdown=breakdown, monthly=monthly, private_fills=fills,trace=trace,symbol_ids=symbol_ids,admissions=admissions)
