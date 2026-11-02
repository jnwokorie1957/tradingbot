import unittest
from research_monitor.hourly_entry_quality import complete_hours,attach_hourly,reject_quality


class HourlyEntryChecks(unittest.TestCase):
    def bars(self,hours=24):
        return [dict(t=i*60,open=100+i/60,high=101+i/60,low=99+i/60,close=100+i/60,volume=1) for i in range(hours*60)]

    def test_missing_minute_prevents_hourly_candle(self):
        self.assertEqual(len(complete_hours(self.bars(1)[:-1])),0)
        self.assertEqual(len(complete_hours(self.bars(1))),1)

    def test_forming_hour_and_future_prices_do_not_change_current_features(self):
        one=self.bars();t=20*3600+1800;s={t:dict(side=1,reference=122.,atr14=4.)}
        full=attach_hourly(s,one)
        prefix=attach_hourly(s,[b for b in one if b['t']+60<=t])
        self.assertEqual(full,prefix)
        self.assertEqual(full[t]['features']['hourly']['end'],20*3600)
        self.assertIsNone(reject_quality('completed_hour_trend',full[t],122))
        changed=[dict(b,close=9999.,high=10000.) if b['t']>=t else b for b in one]
        self.assertEqual(full,attach_hourly(s,changed))

    def test_insufficient_or_stale_hourly_context_is_rejected(self):
        for t in [19*3600,23*3600+1]:
            s=attach_hourly({t:dict(side=1,reference=130.,atr14=4.)},self.bars(22))
            self.assertEqual(reject_quality('completed_hour_trend',s[t],130),'hourly_context_unavailable')

    def test_no_chase_is_directional_and_allows_favorable_price(self):
        for side in [1,-1]:
            s=dict(side=side,reference=100.,atr14=4.)
            self.assertIsNone(reject_quality('no_chase',s,100+side))
            self.assertEqual(reject_quality('no_chase',s,100+side*1.01),'entry_extended_beyond_quarter_ATR')
            self.assertIsNone(reject_quality('no_chase',s,100-side*3))

    def test_combined_requires_both_rules_and_control_needs_neither(self):
        s=dict(side=1,reference=100.,atr14=4.,features={'hourly':dict(available=True,close=101.,ema20=99.,slope=1.)})
        self.assertEqual(reject_quality('both',s,102),'entry_extended_beyond_quarter_ATR')
        self.assertIsNone(reject_quality('control',dict(side=1,reference=100.),999))
