import unittest
import numpy as np
from .checks import Checks
from .data import BARS
from .extension import ExtensionSignals


class ExtensionChecks(unittest.TestCase):
    def test_prefix_causality_and_delay(self):
        rng=np.random.default_rng(8);b=np.zeros(600,dtype=BARS);b['t']=1767621600+np.arange(600)*60;x=100+np.cumsum(rng.normal(0,.15,600));b['open']=x;b['close']=x+rng.normal(0,.1,600);b['high']=np.maximum(b['open'],b['close'])+.1;b['low']=np.minimum(b['open'],b['close'])-.1
        prefix=ExtensionSignals(1,.01).generate(b[:400]);all_=ExtensionSignals(1,.01).generate(b)
        for f in prefix:
            self.assertEqual(prefix[f],[s for s in all_[f] if s['decision']<=b['t'][399]+60])
            for p in all_[f]:self.assertEqual(p['entry_at']-p['decision'],1)


if __name__=='__main__':unittest.main()
