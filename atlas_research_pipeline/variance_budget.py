"""Isolated offline cap-only allocator wrapper; frozen allocator stays intact."""
from datetime import datetime, timezone

from atlas_exit_research import engine
from atlas_exit_research.holding_pair import HoldingBook
from research_monitor.audited_run import down, NY


ORIGINAL_ALLOCATE = engine.allocate


def capped(allocation, scale, step, minimum):
    if scale is None:
        return allocation  # Unavailable feature leaves the original allocator intact.
    assert 0 < scale <= 1 and step > 0 and minimum > 0
    result = dict(allocation, reasons=list(allocation['reasons']))
    budget = allocation['lane_budget'] * scale
    quantity = min(allocation['quantity'], max(0., down(budget / allocation['perlot'], step)))
    result.update(quantity=quantity, lane_budget=budget,
                  unscaled_lane_budget=allocation['lane_budget'],
                  unscaled_quantity=allocation['quantity'], variance_budget_scale=scale)
    if allocation['minimum_legal_risk'] > budget + 1e-8:
        result['reasons'].append('variance_budget_below_legal_minimum')
    assert quantity <= allocation['quantity'] + 1e-9
    assert quantity * allocation['perlot'] <= budget + 1e-7
    return result


class VarianceBook(HoldingBook):
    def __init__(self, *args, variance_features, enabled, **kwargs):
        super().__init__(*args, **kwargs)
        self.variance_features = variance_features
        self.variance_enabled = enabled

    def enter(self, k, name, signal, i):
        if not self.variance_enabled:
            return super().enter(k, name, signal, i)
        symbol = self.lanes[name]['symbol']
        day = datetime.fromtimestamp(float(self.market.t[symbol][i]), timezone.utc).astimezone(NY).date().isoformat()
        feature = self.variance_features[symbol].get(day, dict(status='outside_registered_development'))
        available = feature['status'] == 'feature_available'
        if available:
            assert feature['normalization_last'] < feature['previous_weekday'] < day
        scale = feature['scale'] if available else None

        def allocate(*args, **kwargs):
            row = ORIGINAL_ALLOCATE(*args, **kwargs)
            meta = args[0]
            result = capped(row, scale, meta['volume_step'], meta['volume_min'])
            return dict(result, variance_feature_status=feature['status'])

        assert engine.allocate is ORIGINAL_ALLOCATE
        before = len(self.decisions)
        engine.allocate = allocate
        try:
            return super().enter(k, name, signal, i)
        finally:
            engine.allocate = ORIGINAL_ALLOCATE
            for row in self.decisions[before:]:
                row['variance_feature_status'] = feature['status']
                row['variance_reference_day'] = feature.get('previous_weekday')
                row['variance_normalization_last'] = feature.get('normalization_last')

