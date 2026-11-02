import unittest
from .power_lease import should_hold


class LeaseChecks(unittest.TestCase):
    def test_battery_and_unknown_power_never_hold(self):
        for value in [0,255]:self.assertFalse(should_hold(value,True,False,False))

    def test_request_is_limited_to_live_unexpired_worker_on_AC(self):
        self.assertTrue(should_hold(1,True,False,False));self.assertFalse(should_hold(1,False,False,False));self.assertFalse(should_hold(1,True,True,False));self.assertFalse(should_hold(1,True,False,True))


if __name__=='__main__':unittest.main()
