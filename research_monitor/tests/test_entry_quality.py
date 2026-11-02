import unittest
from datetime import datetime,timezone
from research_monitor.entry_quality import enrich,reject

class EntryQualityChecks(unittest.TestCase):
 def test_room_gate_is_directional_and_target_distance_aware(self):
  s=dict(side=1,features=dict(prior_high=101.))
  self.assertEqual(reject('prior_session_room',s,100,1,1.5),'prior_boundary_inside_target')
  self.assertIsNone(reject('prior_session_room',s,102,1,1.5))
  s=dict(side=-1,features=dict(prior_low=99.))
  self.assertEqual(reject('prior_session_room',s,100,1,1.5),'prior_boundary_inside_target')
 def test_future_session_prices_do_not_change_prefix_features(self):
  at=int(datetime(2026,10,1,13,30,tzinfo=timezone.utc).timestamp())
  one=[dict(t=at+i*60,open=100.,high=101.,low=99.,close=100.) for i in range(390)]
  native=[dict(t=at-900*(21-i),close=100.+i) for i in range(23)]
  decision=at+900;s={decision:dict(side=1,atr14=1.)}
  before=enrich(native,one,s)
  changed=[dict(b) for b in one]
  for b in changed:
   if b['t']>decision:b.update(high=10000.,low=-10000.,close=999.)
  after=enrich(native,changed,s)
  self.assertEqual(before,after);self.assertNotIn('prior_high',before[decision]['features'])
 def test_gap_requires_complete_known_context(self):
  self.assertEqual(reject('opening_gap',dict(side=1,atr14=1.,features={}),100,1,1.5),'gap_context_unavailable')
