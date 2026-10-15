"""Closing-half-hour continuation: offline causal adapter, independent strategy v1.

The reviewed generic engine is unchanged. The quote method below retains its
validation, fills, costs and risk gates, with ATR-from-fill stops and no target.
Calendar truth and actual data/cost eligibility still require external evidence.
"""
import hashlib,json,math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from .engine_v4 import Engine,Policy,Ledger,utc,finite,freeze,thaw,digest
from .closing_continuation import decide,VERSION

@dataclass(frozen=True)
class ClosingIdentity:
    family: str
    version: str
    calendar_hash: str
    implementation_hash: str

class ClosingEngine(Engine):
    def __init__(self,ledger,run_id,contracts,sessions,policy=Policy(),synthetic=False):
        if (policy.budget!=500 or policy.portfolio_risk>.01 or policy.daily_pause>.02
            or policy.drawdown_pause>.10 or policy.quote_max_age_seconds>5
            or policy.signal_ttl_seconds>60 or policy.max_hold_seconds!=3600):
            raise ValueError('closing_strategy_policy_cannot_relax_baseline')
        self._sessions=freeze(json.loads(json.dumps(sessions,allow_nan=False)))
        occupied=set()
        for sid,session in self._sessions.items():
            if session['contract'] not in contracts:raise ValueError('unknown_session_contract')
            if utc(session['available_at'])>utc(session['open']):raise ValueError('calendar_not_known_before_session')
            key=(session['contract'],utc(session['open']).date())
            if key in occupied:raise ValueError('duplicate_contract_session')
            occupied.add(key)
            at=(utc(session['close'])-timedelta(minutes=30)).isoformat()
            decide([],session,contracts[session['contract']]['tick'],at)
        source_hash=digest({name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                           for name in ['closing_execution.py','closing_continuation.py','engine_v4.py']})
        identity=ClosingIdentity('closing_half_hour_continuation','1.0.0',digest(thaw(self._sessions)),source_hash)
        super().__init__(ledger,run_id,contracts,policy,identity,synthetic)

    def _check_identity(self):
        super()._check_identity()
        if digest(thaw(self._sessions))!=self.hypothesis.calendar_hash:raise ValueError('calendar_identity_changed')

    def _dispatch(self,e,now):
        self.state.setdefault('closing_bars',{})
        self.state.setdefault('closing_attempts',{})
        if e['kind']=='decision':
            self._queue_administrative_exits(now)
            sid=e['session_id'];session=self._sessions[sid]
            if e['contract']!=session['contract']:raise ValueError('wrong_session_contract')
            at=utc(session['close'])-timedelta(minutes=30)
            if now!=at:return dict(status='skip',reason='outside_decision_time')
            if sid in self.state['closing_attempts']:return dict(status='skip',reason='session_already_decided')
            self.state['closing_attempts'][sid]=e['available_at']
            key=e['contract'];c=self.contracts[key]
            if c.get('root') not in ('MNQ','MES') and not (self.config['synthetic'] and c.get('root')=='TEST'):
                return dict(status='skip',reason='strategy_market_not_supported')
            if self.state['positions']:return dict(status='skip',reason='one_global_position_research_policy')
            signal=decide(self.state['closing_bars'].get(key,[]),session,c['tick'],e['available_at'])
            if signal['status']!='unqualified_signal_only':return dict(status='skip',reason=signal['status'])
            self.state['pending'][key]=dict(side=signal['side'],stop_distance=signal['stop_distance'],
                 at=e['available_at'],session_id=sid,exit_at=session['close'])
            return dict(status='signal',strategy=VERSION,side=signal['side'],stop_distance=signal['stop_distance'],target=None)
        if e['kind']=='clock':
            self._queue_administrative_exits(now)
            return dict(status='clock_observed',exit_pending=bool(self.state['exit_decisions']))
        return super()._dispatch(e,now)

    def _bar(self,e,now,c):
        start,end=utc(e['start']),utc(e['end'])
        finite(*(e[k] for k in ('open','high','low','close','volume')))
        if (e.get('quality')!='verified' or e.get('bar_kind')!='TRADES' or (end-start).total_seconds()!=300
            or end>now or e['volume']<=0 or not 0<e['low']<=min(e['open'],e['close'])<=max(e['open'],e['close'])<=e['high']):
            raise ValueError('verified_completed_five_minute_trade_bar_required')
        if any(abs(e[k]/c['tick']-round(e[k]/c['tick']))>1e-6 for k in ('open','high','low','close')):
            raise ValueError('off_tick_bar')
        bars=self.state['closing_bars'].setdefault(e['contract'],[])
        if bars and start<utc(bars[-1]['end']):raise ValueError('overlapping_or_regressing_bar')
        bars.append(dict(e))
        return dict(status='bar_recorded')

    def _queue_administrative_exits(self,now):
        super()._queue_administrative_exits(now)
        for key,p in self.state['positions'].items():
            if now>=utc(p['exit_at']):
                self.state['exit_decisions'].setdefault(key,dict(reason='session_close',at=now.isoformat()))

    def report(self):
        r=super().report()
        r.update(strategy=self.hypothesis.family,strategy_version=self.hypothesis.version,
                 qualified_for_paper=False,broker_execution_enabled=False,
                 diagnostic_only=True,cost_evidence_valid=not self.state['invalid_cost_fills'])
        return r

    def _quote(self, e, now, c):
        finite(e['bid'],e['ask'],e['bid_size'],e['ask_size'])
        age = (now-utc(e['quote_at'])).total_seconds()
        if not 0 <= age <= self.policy.quote_max_age_seconds or e['bid'] <= 0 or e['bid'] > e['ask'] or min(e['bid_size'],e['ask_size']) < 1 or e.get('quality') != 'verified':
            return dict(status='skip',reason='stale_crossed_unverified_or_empty_quote')
        tick = c.get('tick')
        if not tick or any(abs(x/tick-round(x/tick)) > 1e-6 for x in (e['bid'],e['ask'])):
            return dict(status='skip',reason='off_tick_quote')
        key, s = e['contract'], self.state
        last=s['marks'].get(key)
        if last and utc(e['quote_at'])<=utc(last['quote_at']):
            return dict(status='skip',reason='nonprogressing_quote_timestamp')
        p=s['positions'].get(key)
        if p and utc(e['quote_at'])<=utc(p['at']):
            return dict(status='skip',reason='pre_entry_quote')
        if not c.get('requires_adjustment') and any(k in e for k in ('adjustment','adjustment_verified','adjustment_at','adjustment_source')):
            return dict(status='skip',reason='unsupported_financing_adjustment')
        if c.get('requires_adjustment') and ('adjustment' not in e or e.get('adjustment_verified') is not True):
            return dict(status='skip',reason='missing_verified_financing_adjustment')
        if c.get('requires_adjustment'):
            if not e.get('adjustment_source') or not e.get('adjustment_at'):
                return dict(status='skip',reason='missing_financing_provenance')
            at=utc(e['adjustment_at'])
            if at>utc(e['quote_at']) or (last and at<utc(last['adjustment_at'])):
                return dict(status='skip',reason='invalid_financing_timestamp')
            if last and at==utc(last['adjustment_at']) and e['adjustment']!=last['adjustment']:
                return dict(status='skip',reason='changed_financing_value_at_same_timestamp')
        finite(e.get('adjustment',0))
        s['marks'][key] = dict(e)
        self._equity(now)
        p = s['positions'].get(key)
        if p:
            price = e['bid'] if p['side'] == 1 else e['ask']
            reason = None
            if p['side']*(price-p['stop']) <= 0: reason = 'stop'
            else:
                if s['paused'] or s['daily_paused']:
                    s['exit_decisions'].setdefault(key,dict(reason='risk_pause',at=now.isoformat()))
                self._queue_administrative_exits(now)
                decision=s['exit_decisions'].get(key)
                if decision:
                    if utc(e['quote_at']) <= utc(decision['at']):
                        return dict(status='exit_pending',reason=decision['reason'],decision_at=decision['at'])
                    reason=decision['reason']
            if reason:
                costs_valid = utc(c['valid_from']) <= now < utc(c['valid_until'])
                if not costs_valid:s['invalid_cost_fills']+=1
                fill = price-p['side']*c['tick']*self.policy.slippage_ticks
                days = (now.date()-utc(p['at']).date()).days
                pnl = (fill-p['entry']+e.get('adjustment',0)-p['adjustment'])*p['side']*c['multiplier']-c['fee_per_side']-days*c['daily_carry_fee']
                s['cash'] += pnl
                del s['positions'][key]
                s['exit_decisions'].pop(key,None)
                s['trades'] += 1
                self._equity(now)
                return dict(status='exit',cost_evidence_valid=costs_valid,reason=reason,fill=fill,quantity=1,net_pnl=pnl-c['fee_per_side'],equity=s['equity'])
            return dict(status='mark',equity=s['equity'])
        signal = s['pending'].get(key)
        if not signal or now <= utc(signal['at']) or utc(e['quote_at']) <= utc(signal['at']):
            return dict(status='no_executable_signal')
        if min((now-utc(signal['at'])).total_seconds(),(utc(e['quote_at'])-utc(signal['at'])).total_seconds()) < 1:
            return dict(status='no_executable_signal',reason='minimum_processing_latency')
        del s['pending'][key]  # one attempt per session, including risk rejection
        if s['positions']:return dict(status='skip',reason='one_global_position_research_policy')
        if now>=utc(signal['exit_at']):return dict(status='skip',reason='session_entry_window_closed')
        reason = self._eligibility(c,now)
        if (now-utc(signal['at'])).total_seconds() > self.policy.signal_ttl_seconds: reason = 'signal_expired'
        if s['paused'] or s['daily_paused']: reason = 'risk_pause'
        if reason: return dict(status='skip',reason=reason)
        if any(not self._margins(k,now)[2] for k in (*s['positions'],key)):
            return dict(status='skip',reason='margin_evidence_expired')
        # Existing positions must have fresh marks before admitting portfolio exposure.
        if any((now-utc(s['marks'][k]['quote_at'])).total_seconds() > self.policy.quote_max_age_seconds for k in s['positions']):
            return dict(status='skip',reason='stale_portfolio_mark')
        side = signal['side']
        fill = (e['ask'] if side == 1 else e['bid'])+side*c['tick']*self.policy.slippage_ticks
        distance = signal['stop_distance']
        signal['stop'] = fill-side*distance
        if side*((e['bid'] if side==1 else e['ask'])-signal['stop']) <= 0:
            return dict(status='skip',reason='entry_quote_already_beyond_stop')
        if distance < c['tick']:
            return dict(status='skip',reason='invalid_stop_after_gap')
        carry_reserve = (math.ceil(self.policy.max_hold_seconds/86400)+1)*c['daily_carry_fee']
        risk = (distance+c['tick']*self.policy.slippage_ticks)*c['multiplier']+2*c['fee_per_side']+carry_reserve
        open_risk = sum(p['risk'] for p in s['positions'].values())
        margins = sum(max(self._margins(k,now)[:2]) for k in s['positions'])
        if risk > min(2.50,s['equity']*.005,s['equity']*self.policy.trade_risk)+1e-9: reason = 'one_contract_trade_risk'
        elif risk+open_risk > s['equity']*self.policy.portfolio_risk+1e-9: reason = 'portfolio_risk'
        elif margins+max(self._margins(key,now)[:2])+risk+open_risk > s['equity']: reason = 'margin_and_loss_reserve'
        if reason: return dict(status='skip',reason=reason,risk=risk)
        s['cash'] -= c['fee_per_side']
        s['positions'][key] = dict(side=side,entry=fill,stop=signal['stop'],target=None,exit_at=signal['exit_at'],session_id=signal['session_id'],
                                  risk=risk,at=e['available_at'],adjustment=e.get('adjustment',0),quantity=1)
        self._equity(now)
        return dict(status='entry',fill=fill,quantity=1,risk=risk,equity=s['equity'])

