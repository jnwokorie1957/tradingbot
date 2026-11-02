import unittest
from datetime import datetime,timedelta
import numpy as np
from .data import NY,BARS
from .level_noise import LevelNoiseSignals


class LevelNoiseChecks(unittest.TestCase):
    def make_bars(self,minutes=1):
        rng=np.random.default_rng(71);rows=[];day=datetime(2026,1,5,9,30,tzinfo=NY);price=100.
        for i in range(32):
            at=day+timedelta(days=i)
            if at.weekday()>=5 or at.date().isoformat()=='2026-01-19':continue
            for k in range(390//minutes):
                opening=price;price+=float(rng.normal(.002,.09));rows.append((at.timestamp()+k*minutes*60,opening,max(opening,price)+.03,min(opening,price)-.03,price,10))
        return np.array(rows,dtype=BARS)

    def test_native_prefix_causality_for_both_frames(self):
        for minutes in [1,5]:
            bars=self.make_bars(minutes);cut=len(bars)-123
            short=LevelNoiseSignals(minutes,.01).generate(bars[:cut]);full=LevelNoiseSignals(minutes,.01).generate(bars)
            for family in short:
                self.assertEqual(short[family],[s for s in full[family] if s['decision']<=bars['t'][cut-1]+minutes*60])
                for s in full[family]:self.assertEqual(s['entry_at'],s['decision']+1)
            self.assertTrue(sum(map(len,full.values())))

    def test_previous_incomplete_session_does_not_become_level(self):
        b=self.make_bars();engine=LevelNoiseSignals(1,.01);engine.generate(b[:389]);engine.generate(b[390:391]);self.assertIsNone(engine.prior);self.assertEqual(len(engine.sessions),0)

    def test_noise_requires_fourteen_completed_prior_sessions(self):
        b=self.make_bars();engine=LevelNoiseSignals(1,.01);signals=engine.generate(b[:14*390]);self.assertFalse(signals['time_of_day_breakout']);engine.generate(b[14*390:14*390+1]);self.assertEqual(len(engine.sessions),14)

    def test_missing_recent_session_invalidates_older_level(self):
        b=self.make_bars();engine=LevelNoiseSignals(1,.01);engine.generate(b[:391]);self.assertIsNotNone(engine.prior)
        engine.generate(b[391:779]);engine.generate(b[780:781]);self.assertIsNone(engine.prior);self.assertEqual(len(engine.sessions),0)


if __name__=='__main__':unittest.main()
