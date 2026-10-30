import unittest
from tests.test_research_workflow import ResearchWorkflowTests


class ObservationOrderTests(unittest.TestCase):
    setUp=ResearchWorkflowTests.setUp
    tearDown=ResearchWorkflowTests.tearDown
    # Inherit fixture lifecycle only; reporting tests below use synthetic receipts.
    def receipt(self,stamp,label):
        value={'label':label}
        if stamp!='missing':value['observed_at']=stamp
        self.w.journal.append(label,'research_cycle_completed',value)

    def test_out_of_order_observations_and_recovery(self):
        self.receipt('2026-10-30T17:00:00Z','newer')
        self.receipt('2026-10-30T15:00:00Z','recorded-last')
        a=self.w.report('daily','2026-10-30T18:00:00Z')
        self.assertEqual(a['last_observed_snapshot']['label'],'newer')
        self.assertEqual(a['last_recorded_snapshot']['label'],'recorded-last')
        self.receipt('2026-10-30T19:00:00Z','later')
        self.assertEqual(a,self.w.report('daily','2026-10-30T20:00:00Z'))
        self.w.journal.verify()

    def test_equal_instants_use_later_journal_sequence(self):
        self.receipt('2026-10-30T15:00:00Z','first')
        self.receipt('2026-10-30T10:00:00-05:00','second')
        self.assertEqual(self.w.report('daily','2026-10-30T18:00:00Z')['last_observed_snapshot']['label'],'second')

    def test_invalid_timestamp_no_claim_or_report(self):
        for stamp in ('missing',None,123,'bad','2026-10-30T15:00:00'):
            with self.subTest(stamp=stamp):
                # Independent fixture per invalid receipt; never rewrite history.
                from trading_pipeline.research_workflow import Workflow
                w=Workflow(self.folder/('bad-'+str(stamp).replace(':','-')+'.sqlite'))
                try:
                    payload={} if stamp=='missing' else {'observed_at':stamp}
                    w.journal.append('bad','research_cycle_completed',payload)
                    before=list(w.db.execute('SELECT * FROM claims'))
                    with self.assertRaisesRegex(ValueError,'invalid cycle observation'):w.report('daily','2026-10-30T18:00:00Z')
                    self.assertEqual(before,list(w.db.execute('SELECT * FROM claims')))
                    self.assertEqual(w.db.execute("SELECT COUNT(*) FROM records WHERE kind='research_report_completed'").fetchone()[0],0)
                finally:w.close()

    def test_chicago_boundary_excludes_next_day(self):
        self.receipt('2026-10-31T04:59:59Z','included')
        self.receipt('2026-10-31T05:00:00Z','excluded')
        r=self.w.report('daily','2026-10-30T18:00:00Z')
        self.assertEqual(r['observed_cycles'],1)
        self.assertEqual(r['last_observed_snapshot']['label'],'included')


if __name__=='__main__':unittest.main()
