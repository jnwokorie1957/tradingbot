"""Offline, one-shot futures simulation. No brokerage transport exists here."""
from __future__ import annotations
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k:freeze(v) for k,v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {k:thaw(v) for k,v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


def utc(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None or t.utcoffset() != timedelta(0):
        raise ValueError('explicit UTC required')
    return t


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def finite(*values):
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
        raise ValueError('finite numeric values required')


@dataclass(frozen=True)
class Policy:
    budget: float = 500.0
    trade_risk: float = .005
    portfolio_risk: float = .01
    daily_pause: float = .02
    drawdown_pause: float = .10
    slippage_ticks: int = 1
    quote_max_age_seconds: int = 5
    signal_ttl_seconds: int = 60
    max_hold_seconds: int = 3600
    max_bar_gap_seconds: int = 7200

    def __post_init__(self):
        finite(*asdict(self).values())
        if self.budget <= 0 or any(not 0 < x < 1 for x in (self.trade_risk, self.portfolio_risk, self.daily_pause, self.drawdown_pause)):
            raise ValueError('invalid risk policy')
        if self.slippage_ticks < 1 or int(self.slippage_ticks) != self.slippage_ticks:
            raise ValueError('at least one integer slippage tick required')
        if min(self.quote_max_age_seconds, self.signal_ttl_seconds, self.max_hold_seconds, self.max_bar_gap_seconds) <= 0:
            raise ValueError('positive time limits required')


@dataclass(frozen=True)
class Hypothesis:
    family: str = 'breakout'
    version: str = '1.0.0'
    lookback: int = 20
    reward_risk: float = 2.0

    def __post_init__(self):
        if self.family not in ('breakout', 'pullback') or self.version != '1.0.0':
            raise ValueError('unknown versioned hypothesis')
        finite(self.lookback, self.reward_risk)
        if type(self.lookback) is not int or self.lookback < 2 or self.reward_risk <= 0:
            raise ValueError('invalid hypothesis')


class Ledger:
    """Commit event and resulting state together; immutable event IDs per run."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, config TEXT NOT NULL, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(run TEXT, id TEXT, hash TEXT, input TEXT, output TEXT,
            PRIMARY KEY(run,id));
        CREATE TABLE IF NOT EXISTS trials(id INTEGER PRIMARY KEY, metadata TEXT NOT NULL, result TEXT);
        CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END;
        CREATE TRIGGER IF NOT EXISTS no_trial_delete BEFORE DELETE ON trials BEGIN SELECT RAISE(ABORT,'retain failed trials'); END;
        ''')

    def close(self):
        self.db.close()


class Engine:
    def __init__(self, ledger, run_id, contracts, policy=Policy(), hypothesis=Hypothesis(), synthetic=False):
        self.ledger, self.run_id = ledger, run_id
        # JSON round-trip breaks every caller-owned nested reference before freezing.
        self._contracts = freeze(json.loads(json.dumps(contracts,allow_nan=False)))
        self.policy, self.hypothesis = policy, hypothesis
        config = dict(engine_version=5,contracts=thaw(self._contracts), policy=asdict(policy), hypothesis=asdict(hypothesis), synthetic=synthetic)
        encoded = json.dumps(config, sort_keys=True, allow_nan=False)
        self._config_json = encoded
        row = ledger.db.execute('SELECT config,state FROM runs WHERE id=?', (run_id,)).fetchone()
        if row:
            if row[0] != encoded:
                raise ValueError('run configuration cannot change on resume')
            self.state = json.loads(row[1])
        else:
            self.state = dict(cash=policy.budget, equity=policy.budget, peak=policy.budget,
                              day=None, day_start=policy.budget, daily_paused=False, paused=False,
                              last_time=None, bars={}, pending={}, positions={}, marks={}, trades=0,
                              margin_updates={}, exit_decisions={}, invalid_cost_fills=0)
            with ledger.db:
                ledger.db.execute('INSERT INTO runs VALUES(?,?,?)', (run_id, encoded, json.dumps(self.state)))

    @property
    def contracts(self):
        return self._contracts

    @property
    def config(self):
        return json.loads(self._config_json)

    def _check_identity(self):
        expected = self.config
        if (thaw(self.contracts) != expected['contracts'] or asdict(self.policy) != expected['policy']
                or asdict(self.hypothesis) != expected['hypothesis']):
            raise ValueError('engine configuration identity changed')
        stored = self.ledger.db.execute('SELECT config FROM runs WHERE id=?',(self.run_id,)).fetchone()
        if not stored or stored[0] != self._config_json:
            raise ValueError('ledger configuration identity changed')

    def apply(self, event):
        self._check_identity()
        event = json.loads(json.dumps(event,allow_nan=False))
        event_hash = digest(event)
        old = self.ledger.db.execute('SELECT hash,output FROM events WHERE run=? AND id=?', (self.run_id,event['id'])).fetchone()
        if old:
            if old[0] != event_hash:
                raise ValueError('event ID reused with changed data')
            return json.loads(old[1])
        backup = json.dumps(self.state)
        try:
            now = utc(event['available_at'])
            if self.state['last_time'] and now < utc(self.state['last_time']):
                raise ValueError('out-of-order observation')
            # Midnight baseline uses previous observation equity; first new-day gap counts today.
            day = now.date().isoformat()
            if day != self.state['day']:
                self.state.update(day=day, day_start=self.state['equity'], daily_paused=False)
            self.state['last_time'] = event['available_at']
            out = self._dispatch(event, now)
            with self.ledger.db:
                self.ledger.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',
                    (self.run_id,event['id'],event_hash,json.dumps(event),json.dumps(out)))
                self.ledger.db.execute('UPDATE runs SET state=? WHERE id=?', (json.dumps(self.state),self.run_id))
            return out
        except Exception:
            self.state = json.loads(backup)
            raise

    def _dispatch(self, e, now):
        c = self.contracts[e['contract']]
        if e['kind'] == 'margin_update':
            out=self._margin_update(e,now)
            self._queue_administrative_exits(now)
            return out
        self._queue_administrative_exits(now)
        if e['kind'] == 'bar':
            return self._bar(e, now, c)
        if e['kind'] == 'quote':
            initial,maintenance,_=self._margins(e['contract'],now)
            c=dict(c,initial_margin=initial,maintenance_margin=maintenance)
            return self._quote(e, now, c)
        if e['kind'] == 'roll':
            self._validate_successor(e,now)
            if e['contract'] in self.state['positions']:
                raise ValueError('roll requires old contract flat; no fabricated roll fill')
            self.state['pending'].pop(e['contract'], None)
            self.state['bars'].pop(e['contract'], None)
            return dict(status='roll_boundary', new_contract=e['new_contract'])
        raise ValueError('unsupported event')

    def _queue_administrative_exits(self,now):
        # Decisions use observation time; never execute against a quote predating them.
        s=self.state
        for key,p in s['positions'].items():
            c=self.contracts[key];reason=None
            if sum(self._margins(k,now)[1] for k in s['positions']) > s['equity']: reason='maintenance_margin_breach'
            elif any(not self._margins(k,now)[2] for k in s['positions']): reason='margin_evidence_expired'
            elif now >= utc(c['exit_before']): reason='expiry_or_roll_cutoff'
            elif (now-utc(p['at'])).total_seconds() >= self.policy.max_hold_seconds: reason='time_exit'
            elif self._eligibility(c,now): reason='evidence_expired'
            if reason:s['exit_decisions'].setdefault(key,dict(reason=reason,at=now.isoformat()))

    def _validate_successor(self,e,now):
        new=e.get('new_contract')
        if not isinstance(new,str) or new not in self.contracts or new==e['contract']:
            raise ValueError('roll requires a known distinct successor')
        old,c=self.contracts[e['contract']],self.contracts[new]
        if any(not isinstance(old.get(k),str) or not old[k].strip() for k in ('root','exchange','currency')):
            raise ValueError('roll requires explicit product identity')
        finite(old.get('multiplier'),old.get('tick'))
        if min(old['multiplier'],old['tick'])<=0:
            raise ValueError('invalid roll product specification')
        for field in ('root','exchange','currency','multiplier','tick'):
            if old.get(field) is None or c.get(field)!=old[field] or old[field]=='':
                raise ValueError('roll successor must match product specification')
        if old.get('spec_verified') is not True or c.get('spec_verified') is not True:
            raise ValueError('roll requires verified product specifications')
        if (type(old.get('contract_id')) is not int or type(c.get('contract_id')) is not int
                or min(old['contract_id'],c['contract_id'])<=0 or old['contract_id']==c['contract_id']):
            raise ValueError('roll requires distinct expiry-specific contract IDs')
        try:
            months=[datetime.strptime(x['contract_month'],'%Y%m') for x in (old,c)]
            expiries=[datetime.strptime(x['last_trading_date'],'%Y%m%d').date() for x in (old,c)]
            if any(len(x['contract_month'])!=6 or len(x['last_trading_date'])!=8 for x in (old,c)):
                raise ValueError('invalid expiry format')
            if not (months[1]>months[0] and expiries[1]>expiries[0] and expiries[1]>now.date()
                    and utc(c['exit_before'])>now):
                raise ValueError('successor expiry must be later and usable')
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError('invalid roll successor expiry metadata') from exc
        if new in self.state['positions']:
            raise ValueError('roll successor must also be flat')

    def _bar(self, e, now, c):
        start, end = utc(e['start']), utc(e['end'])
        finite(e['open'],e['high'],e['low'],e['close'],e['volume'])
        if not start < end <= now or e['volume'] <= 0 or not e['low'] <= min(e['open'],e['close']) <= max(e['open'],e['close']) <= e['high']:
            raise ValueError('incomplete or invalid OHLCV bar')
        bars = self.state['bars'].setdefault(e['contract'], [])
        if bars and start < utc(bars[-1]['end']):
            raise ValueError('overlapping/duplicate bar')
        if bars and (start - utc(bars[-1]['end'])).total_seconds() > self.policy.max_bar_gap_seconds:
            bars.clear()
            self.state['pending'].pop(e['contract'], None)
        n = self.hypothesis.lookback
        prior = bars[-n:]
        side = 0
        if len(prior) == n and e['volume'] > 0:
            if self.hypothesis.family == 'breakout':
                side = 1 if e['close'] > max(b['high'] for b in prior) else -1 if e['close'] < min(b['low'] for b in prior) else 0
            else:
                mean = sum(b['close'] for b in prior)/n
                up = prior[-1]['close'] > prior[0]['close']
                down = prior[-1]['close'] < prior[0]['close']
                side = 1 if up and e['low'] <= mean < e['close'] else -1 if down and e['high'] >= mean > e['close'] else 0
        bars.append({k:e[k] for k in ('start','end','open','high','low','close','volume')})
        del bars[:-n]
        # A new completed bar cancels any older unfilled signal.
        self.state['pending'].pop(e['contract'], None)
        if side and e['contract'] not in self.state['positions']:
            stop = e['low'] if side == 1 else e['high']
            self.state['pending'][e['contract']] = dict(side=side,stop=stop,at=e['available_at'])
        return dict(status='signal' if side else 'no_signal',side=side)

    def _margin_update(self,e,now):
        effective,until=utc(e['effective_at']),utc(e['valid_until'])
        finite(e['initial_margin'],e['maintenance_margin'])
        if (e.get('verified') is not True or not isinstance(e.get('source'),str) or not e['source'].strip() or e.get('currency')!='USD'
                or min(e['initial_margin'],e['maintenance_margin'])<=0 or until<=max(effective,now)):
            raise ValueError('invalid margin evidence')
        updates=self.state['margin_updates'].setdefault(e['contract'],[])
        same=[u for u in updates if utc(u['effective_at'])==effective]
        supersedes=e.get('supersedes')
        # Same-effective corrections must explicitly name the current head.
        # Different effective dates may arrive in any observation order.
        if same:
            if not isinstance(supersedes,str) or supersedes!=same[-1]['id']:
                raise ValueError('same-effective correction must supersede latest announcement')
        elif supersedes is not None:
            raise ValueError('supersedes must identify the same-effective announcement')
        updates.append(dict(e,observation_sequence=len(updates)+1))
        return dict(status='margin_update_recorded',effective_at=e['effective_at'],
                    available_at=e['available_at'],retroactive_repricing=False)

    def _margins(self,key,now):
        c=self.contracts[key]
        active=[u for u in self.state['margin_updates'].get(key,[])
                if utc(u['effective_at'])<=now and utc(u['available_at'])<=now]
        if active:
            u=max(active,key=lambda u:(utc(u['effective_at']),u['observation_sequence']))
            return u['initial_margin'],u['maintenance_margin'],now<utc(u['valid_until'])
        return c.get('initial_margin'),c.get('maintenance_margin'),True

    def _eligibility(self, c, now):
        if c.get('root')=='QNDX':
            return 'qndx_quarterly_fee_accounting_not_supported'
        needed = ('spec_verified','permission_verified','costs_verified','data_verified')
        if not all(c.get(k) is True for k in needed):
            return 'unverified_contract_permission_cost_or_data'
        if not c.get('evidence_source') or not c.get('valid_from') or not c.get('valid_until'):
            return 'missing_evidence_interval'
        if not utc(c['valid_from']) <= now < utc(c['valid_until']):
            return 'stale_or_future_evidence'
        if c.get('currency') != 'USD':
            return 'unmodeled_fx'
        for key in ('multiplier','tick','initial_margin','maintenance_margin','fee_per_side','daily_carry_fee'):
            value = c.get(key)
            if value is None:
                return 'missing_'+key
            finite(value)
            if value < 0 or (key in ('multiplier','tick','initial_margin','maintenance_margin') and value == 0):
                return 'invalid_'+key
        if utc(c['exit_before']) <= now:
            return 'expiry_or_roll_cutoff'
        return None

    def _equity(self, now):
        s = self.state
        unrealized = 0
        for key,p in s['positions'].items():
            c, q = self.contracts[key], s['marks'][key]
            price = q['bid'] if p['side'] == 1 else q['ask']
            slip = c['tick'] * self.policy.slippage_ticks
            adjustment = q.get('adjustment',0)-p['adjustment']
            days = (now.date()-utc(p['at']).date()).days
            unrealized += ((price-p['entry']+adjustment)*p['side']-slip)*c['multiplier'] - c['fee_per_side'] - days*c['daily_carry_fee']
        s['equity'] = s['cash']+unrealized
        s['peak'] = max(s['peak'],s['equity'])
        s['paused'] |= s['equity'] <= s['peak']*(1-self.policy.drawdown_pause)
        s['daily_paused'] |= s['equity'] <= s['day_start']*(1-self.policy.daily_pause)

    def _quote(self, e, now, c):
        finite(e['bid'],e['ask'],e['bid_size'],e['ask_size'])
        age = (now-utc(e['quote_at'])).total_seconds()
        if not 0 <= age <= self.policy.quote_max_age_seconds or e['bid'] > e['ask'] or min(e['bid_size'],e['ask_size']) < 1 or e.get('quality') != 'verified':
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
            elif p['side']*(price-p['target']) >= 0: reason = 'target'
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
        del s['pending'][key]  # first later valid quote consumes intent even if risk-rejected
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
        distance = side*(fill-signal['stop'])
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
        s['positions'][key] = dict(side=side,entry=fill,stop=signal['stop'],target=fill+side*distance*self.hypothesis.reward_risk,
                                  risk=risk,at=e['available_at'],adjustment=e.get('adjustment',0),quantity=1)
        self._equity(now)
        return dict(status='entry',fill=fill,quantity=1,risk=risk,equity=s['equity'])

    def report(self):
        self._check_identity()
        return dict(run_id=self.run_id,synthetic=self.config['synthetic'],state=self.state,
                    valid_for_profit_claim=False,review_required=True,loop_enabled=False,
                    unresolved_positions=len(self.state['positions']),config_hash=digest(self.config))
