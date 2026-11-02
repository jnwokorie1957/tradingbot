import unittest
from research_monitor.native_context import enrich_native


class NativeContextChecks(unittest.TestCase):
    def test_features_are_attached_at_actual_native_end_without_future_bars(self):
        for minutes in [3,5,15,30]:
            step=minutes*60;native=[dict(t=i*step,close=100.+i) for i in range(25)];cut=21*step;signals={cut:dict(side=1)}
            full=enrich_native(native,[],signals,minutes)
            prefix=enrich_native([b for b in native if b['t']+step<=cut],[],signals,minutes)
            self.assertEqual(full,prefix)
            self.assertEqual(full[cut]['features']['directional_efficiency'],1.)
