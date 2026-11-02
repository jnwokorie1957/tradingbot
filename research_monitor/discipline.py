"""Frozen exploratory entry gates; decisions use information available before entry."""
from dataclasses import dataclass, asdict
from math import isfinite


@dataclass(frozen=True)
class DisciplinePolicy:
    name: str = 'selective_v1'
    max_entries_per_session: int = 3
    max_consecutive_losses: int = 2
    cooldown_minutes: int = 30
    daily_realized_loss_limit: float = 50.
    min_stop_atr: float = .5
    max_stop_atr: float = 1.5
    max_roundtrip_cost_R: float = .10
    max_chase_atr: float = .25


class Discipline:
    def __init__(self):
        self.policy = DisciplinePolicy()
        self.session = None
        self.entries = 0
        self.loss_streak = 0
        self.realized = 0.
        self.last_exit = None
        self.loss_halt = False

    def begin_session(self, session):
        if session != self.session:
            self.session = session
            self.entries = 0
            self.loss_streak = 0
            self.realized = 0.
            self.loss_halt = False
            # Cooldown remains in wall-clock time across session boundaries.

    def reason(self, signal, entry, distance, spread, slip, now):
        p = self.policy
        if self.loss_halt:
            return 'session_loss_halt'
        if self.entries >= p.max_entries_per_session:
            return 'session_entry_limit'
        if self.last_exit is not None and now < self.last_exit + p.cooldown_minutes * 60:
            return 'exit_cooldown'
        atr = signal.get('atr14')
        if not atr or not isfinite(atr) or atr <= 0:
            return 'volatility_unavailable'
        if not signal.get('trend_aligned'):
            return 'trend_not_aligned'
        if not signal.get('strong_close'):
            return 'weak_directional_close'
        if not p.min_stop_atr <= distance / atr <= p.max_stop_atr:
            return 'stop_outside_volatility_band'
        if (spread + 2 * slip) / distance > p.max_roundtrip_cost_R:
            return 'execution_cost_too_high'
        if signal['side'] * (entry - signal['reference']) > p.max_chase_atr * atr:
            return 'entry_chasing_price'
        return None

    def entered(self):
        self.entries += 1

    def exited(self, pnl, now):
        self.realized += pnl
        self.last_exit = now
        self.loss_streak = self.loss_streak + 1 if pnl < 0 else 0
        if (self.loss_streak >= self.policy.max_consecutive_losses or
                self.realized <= -self.policy.daily_realized_loss_limit):
            self.loss_halt = True

    def specification(self):
        return asdict(self.policy)
