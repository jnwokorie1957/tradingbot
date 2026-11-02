import unittest
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch
from research_monitor.discipline import Discipline
from research_monitor.local_run import run_case
from research_monitor.telemetry import Reporter


class DisciplineChecks(unittest.TestCase):
    def setUp(self):
        self.d = Discipline()
        self.d.begin_session('2026-10-28')
        self.signal = dict(atr14=10., trend_aligned=True, strong_close=True, side=1, reference=100.)

    def reason(self, **changes):
        args = dict(signal=self.signal, entry=100., distance=10., spread=.2, slip=.1, now=10000)
        args.update(changes)
        return self.d.reason(**args)

    def test_valid_entry_then_session_cap(self):
        self.assertIsNone(self.reason())
        for _ in range(3): self.d.entered()
        self.assertEqual(self.reason(), 'session_entry_limit')

    def test_loss_halt_is_latched_until_next_session(self):
        self.d.exited(-20, 100)
        self.d.exited(-20, 200)
        self.assertEqual(self.reason(), 'session_loss_halt')
        self.d.exited(50, 300)
        self.assertEqual(self.reason(), 'session_loss_halt')
        self.d.begin_session('2026-10-29')
        self.assertIsNone(self.reason())

    def test_dollar_loss_limit_and_cooldown(self):
        self.d.exited(-10, 9999)
        self.assertEqual(self.reason(), 'exit_cooldown')
        self.d.exited(-40, 10000)
        self.assertEqual(self.reason(now=20000), 'session_loss_halt')

    def test_cost_chase_and_volatility_gates(self):
        self.assertEqual(self.reason(spread=1.), 'execution_cost_too_high')
        self.assertEqual(self.reason(entry=103.), 'entry_chasing_price')
        self.assertEqual(self.reason(distance=20.), 'stop_outside_volatility_band')
        self.signal['atr14'] = None
        self.assertEqual(self.reason(), 'volatility_unavailable')

    def test_short_chasing_and_trend(self):
        self.signal['side'] = -1
        self.assertEqual(self.reason(entry=97.), 'entry_chasing_price')
        self.signal['trend_aligned'] = False
        self.assertEqual(self.reason(), 'trend_not_aligned')

    def test_cooldown_survives_calendar_boundary(self):
        self.d.exited(-1, 9999)
        self.d.begin_session('2026-10-29')
        self.assertEqual(self.reason(), 'exit_cooldown')

    def test_runner_refuses_weak_setup_and_records_reason(self):
        at = int(datetime(2026,10,1,14,0,tzinfo=timezone.utc).timestamp())
        bars = [dict(t=at-60+i*60,open=100.,high=102.,low=98.,close=100.,spread=0.,volume=1) for i in range(8)]
        signal = dict(side=1,stop=99.,reference=100.,decision=at,entry_at=at+60,
                      atr14=1.,trend_aligned=False,strong_close=True)
        meta = dict(trade_tick_size=.01,trade_tick_value_loss=.01,volume_min=1,volume_step=1,point=.01)
        source = {('NAS100',1):bars,('NAS100',5):[]}
        with tempfile.TemporaryDirectory() as folder, patch('research_monitor.local_run.signals', return_value={at:signal}):
            reporter = Reporter(folder)
            result = run_case(source,'NAS100',5,meta,dict(lookback=20,rr=1.,filter='none',discipline='selective_v1'),
                              'Development',['2026-10-01'],reporter,0,1,1)
        self.assertEqual(result['outcomes'],0)
        self.assertEqual(result['ending_balance_before_fees'],500.)
        self.assertEqual(result['skips']['trend_not_aligned'],1)
        self.assertFalse(any(e['kind']=='entry' for e in reporter.state['events']))
        self.assertTrue(any(e['kind']=='skip' and e['reason']=='trend_not_aligned' for e in reporter.state['events']))


if __name__ == '__main__': unittest.main()
