"""Causal data-only checks, before any financial protocol is permitted."""
import unittest

import numpy as np

from atlas_exit_research.data import DTYPE
from .spread_preflight import assess


def quotes(spreads):
    return np.array([(float(t), 100., 100. + s) for t, s in enumerate(spreads)], dtype=DTYPE)


class SpreadChecks(unittest.TestCase):
    def test_equal_arrival_preserved(self):
        row = assess(quotes([2] * 130), 60, 1.)
        self.assertEqual(row['status'], 'unchanged_arrival')
        self.assertEqual(row['baseline_last_at'], 59.)
        self.assertEqual(row['prospective_entry_at'], 60.)

    def test_first_trigger_with_separate_reaction_quote(self):
        q = quotes([2] * 60 + [4, 4, 2, 9, 1] + [2] * 70)
        row = assess(q, 60, 1.)
        self.assertEqual(row['trigger_at'], 62.)
        self.assertEqual(row['prospective_entry_at'], 63.)
        self.assertEqual(row['reaction_spread_ticks'], 9)
        self.assertEqual(row['extra_delay_seconds'], 3.)
        self.assertEqual(assess(q[:64], 60, 1.), row)

    def test_current_quote_does_not_change_median(self):
        row = assess(quotes([2] * 60 + [100] + [2] * 70), 60, 1.)
        self.assertEqual(row['reference_median_spread_ticks'], 2.)
        self.assertEqual(row['trigger_at'], 61.)

    def test_sparse_baseline_not_imputed(self):
        q = quotes([2] * 130)[::10]
        self.assertEqual(assess(q, 60, 1.)['status'], 'baseline_coverage_unavailable')

    def test_path_gap_is_not_bridged(self):
        q = quotes([2] * 60 + [4] * 20 + [2] * 50)
        q = np.concatenate([q[:61], q[70:]])
        self.assertEqual(assess(q, 60, 1.)['status'], 'waiting_path_unavailable')

    def test_fixed_deadline_without_nearby_fallback(self):
        q = quotes([2] * 60 + [4] * 62 + [2] * 10)
        self.assertEqual(assess(q, 60, 1.)['status'], 'wait_expired_without_trigger')

    def test_late_trigger_cannot_fill_after_deadline(self):
        q = quotes([2] * 60 + [4] * 60 + [2] * 10)
        self.assertEqual(assess(q, 60, 1.)['status'], 'reaction_after_wait_deadline')

    def test_inconsistent_contract_tick_fails(self):
        with self.assertRaises(ValueError):
            assess(quotes([2.1] * 130), 60, 1.)


if __name__ == '__main__':
    unittest.main()
