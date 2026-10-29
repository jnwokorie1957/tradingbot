import copy
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from trading_pipeline.research_workflow import Workflow, assessment, trade_diagnostics, POLICY

SPEC=dict(source='https://example.org/research',entry='completed bar',exit='next quote',
          stop='structural stop',target='none; timed exit',regime='unknown',evidence='unverified',track='Tradingbot')

def evidence():
    return dict(kind='out_of_sample',unseen=True,causal_quotes=True,costs_verified=True,
        margins_verified=True,calendar_verified=True,risk_controls_pass=True,stress_pass=True,
        all_windows_positive=True,independent_review='test-only reviewer attestation',
        dataset_hash='a'*64,protocol_hash='b'*64,result_hash='c'*64,trades=300,trade_days=30,
        win_rate=.61,profit_factor=1.6,net_expectancy=.1,expectancy_ci_lower=.01,drawdown=.05)

def paper(version='1'):
    return dict(strategy='s',version=version,protocol_hash='b'*64,validation_result_hash='c'*64,result_hash='d'*64,
                kind='local_forward',reviewed=True,trades=30,review_reference='test-only review',
                risk_controls_pass=True,net_expectancy=.01)

def comparison(incumbent=None):
    return dict(incumbent=incumbent,preregistration='test-only precommit',review_reference='test-only review',
        same_conditions=True,meaningful_improvement=True,protocol_hash='b'*64,challenger_result_hash='c'*64,forward_result_hash='d'*64)

class ResearchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.folder=Path('local-results/test-workflow')/uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        self.path=self.folder/'journal.sqlite'
        self.w=Workflow(self.path);self.w.register('s','1',SPEC)
    def tearDown(self):self.w.close()
    def test_empty_leaderboard_no_champion(self):
        self.assertEqual(self.w.snapshot()['leaderboard'],[])
        self.assertIsNone(self.w.snapshot()['champion'])
    def test_synthetic_never_candidate(self):
        e=evidence();e['kind']='synthetic'
        with self.assertRaises(ValueError):self.w.transition('s','1','CANDIDATE','fixture',e)
    def test_all_required_evidence_fails_closed(self):
        for field in evidence():
            e=evidence();del e[field]
            self.assertTrue(assessment(e),field)
    def test_threshold_boundaries_and_nan(self):
        for field,value in [('trades',299),('trades',True),('win_rate',.6),('win_rate',1.1),
                            ('profit_factor',1.5),('drawdown',.1),('net_expectancy',float('nan')),
                            ('expectancy_ci_lower',0),('result_hash','x'*64)]:
            e=evidence();e[field]=value;self.assertTrue(assessment(e),(field,value))
    def test_no_direct_champion(self):
        with self.assertRaises(ValueError):self.w.transition('s','1','CHAMPION','bypass',evidence())
    def test_promotion_requires_actual_forward_kind(self):
        self.w.transition('s','1','CANDIDATE','reviewed',evidence())
        p=paper();p['kind']='synthetic'
        with self.assertRaises(ValueError):self.w.promote('s','1',evidence(),comparison(),p)
    def test_atomic_champion_swap_and_stale_comparison(self):
        self.w.transition('s','1','CANDIDATE','reviewed',evidence())
        self.w.promote('s','1',evidence(),comparison(),paper())
        self.w.register('s','2',SPEC);self.w.transition('s','2','CANDIDATE','reviewed',evidence())
        with self.assertRaises(ValueError):self.w.promote('s','2',evidence(),comparison(),paper('2'))
        self.assertEqual(self.w.snapshot()['champion']['version'],'1')
        self.w.promote('s','2',evidence(),comparison(['s','1']),paper('2'))
        self.assertEqual(self.w.snapshot()['champion']['version'],'2')
        # Reviewed rollback follows the same evidence gate and retains both versions.
        self.w.promote('s','1',evidence(),comparison(['s','2']),paper())
        self.assertEqual(self.w.snapshot()['champion']['version'],'1')
    def test_retirement_preserves_version(self):
        self.w.transition('s','1','RETIRED','failed validation')
        with self.assertRaises(ValueError):self.w.transition('s','1','RESEARCH','retry')
        with self.assertRaises(sqlite3.IntegrityError):self.w.register('s','1',SPEC)
        self.assertEqual(self.w.snapshot()['registry'][0]['state'],'RETIRED')
    def test_forward_bindings_fail_closed_without_state_or_journal_change(self):
        self.w.transition('s','1','CANDIDATE','reviewed',evidence())
        before=self.w.db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
        for field in ('strategy','version','protocol_hash','validation_result_hash','result_hash'):
            for value in (None,'wrong'):
                p=paper()
                if value is None: del p[field]
                else:p[field]=value
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                    self.w.promote('s','1',evidence(),comparison(),p)
        for value in (None,'e'*64):
            c=comparison();c['forward_result_hash']=value
            with self.assertRaises(ValueError):self.w.promote('s','1',evidence(),c,paper())
        self.assertIsNone(self.w.snapshot()['champion'])
        self.assertEqual(before,self.w.db.execute('SELECT COUNT(*) FROM records').fetchone()[0])
    def test_stale_validation_receipt_rejected_even_with_matching_payload_bindings(self):
        old=evidence();new=evidence();new['result_hash']='e'*64
        self.w.transition('s','1','CANDIDATE','first',old)
        self.w.transition('s','1','CANDIDATE','new receipt',new)
        with self.assertRaises(ValueError):self.w.promote('s','1',old,comparison(),paper())
        self.assertIsNone(self.w.snapshot()['champion'])
        p=paper();p['validation_result_hash']='e'*64
        c=comparison();c['challenger_result_hash']='e'*64
        self.w.promote('s','1',new,c,p)
        self.assertEqual(self.w.snapshot()['champion']['version'],'1')
    def test_cycle_claim_survives_restart(self):
        self.w.cycle('2026-10-27T15:00:00Z',[],['no admitted quotes'])
        self.w.close();self.w=Workflow(self.path)
        with self.assertRaises(sqlite3.IntegrityError):self.w.cycle('2026-10-27T15:10:00Z',[],[])
        self.w.journal.verify()
    def test_interrupted_cycle_not_retried(self):
        self.w.journal.claim('research-cycle:'+str(1793113200//7200),'preclaimed')
        with self.assertRaises(sqlite3.IntegrityError):self.w.cycle('2026-10-27T15:00:00Z',[],[])
    def test_overlapping_cycle_across_time_buckets_blocked(self):
        with self.w.db:self.w.db.execute("INSERT INTO research_cycle_lock VALUES(1,'interrupted-other-cycle')")
        with self.assertRaises(sqlite3.IntegrityError):self.w.cycle('2026-10-27T17:00:00Z',[],[])
        self.assertEqual(self.w.db.execute('SELECT cycle FROM research_cycle_lock').fetchone()[0],'interrupted-other-cycle')
    def test_timezone_required(self):
        with self.assertRaises(ValueError):self.w.cycle('2026-10-27T15:00:00',[],[])
    def test_reporting_timezone(self):
        r=self.w.cycle('2026-10-27T01:00:00Z',[],[])
        self.assertEqual(r['reporting_date'],'2026-10-26')
        self.assertFalse(r['simulation_running'])
    def test_protocols_not_pooled(self):
        self.w.transition('s','1','CANDIDATE','reviewed',evidence())
        self.w.register('other','1',SPEC);e=evidence();e['protocol_hash']='d'*64
        self.w.transition('other','1','CANDIDATE','reviewed',e)
        r=self.w.snapshot();self.assertEqual(r['leaderboard'],[])
        self.assertEqual(len(r['leaderboards_by_protocol']),2)
    def test_trade_review_is_immutable_and_loss_does_not_change_strategy(self):
        r=dict(strategy='s',version='1',kind='synthetic',setup='fixture',entry=10,exit=9,
            stop=9,target=None,net_pnl=-1,exit_at='2026-10-27T15:00:00Z',rule_followed=True,
            expected_behavior='loss possible',observed_behavior='stop hit',hypothesis=None,similar_trade_ids=[])
        self.w.review_trade('fixture-1',r)
        with self.assertRaises(sqlite3.IntegrityError):self.w.review_trade('fixture-1',r)
        self.assertEqual(self.w.snapshot()['registry'][0]['state'],'RESEARCH')
        self.assertEqual(self.w.snapshot()['review_metrics']['local_forward']['trades'],0)
        self.assertEqual(self.w.snapshot()['review_metrics']['synthetic']['trades'],1)
    def test_missing_or_invented_trade_comparison_rejected(self):
        with self.assertRaises(ValueError):self.w.review_trade('bad',{})
    def test_metrics_zero_losses_unknown_sharpe(self):
        self.assertIsNone(trade_diagnostics([])['win_rate'])
        r=trade_diagnostics([dict(net_pnl=1,exit_at='2026-10-27T15:00:00Z')])
        self.assertIsNone(r['profit_factor']);self.assertIsNone(r['sharpe'])
    def test_stricter_risk_policy_retained(self):
        self.assertEqual(POLICY['trade_fraction'],.005);self.assertEqual(POLICY['trade_dollar_cap'],2.5)
        self.assertFalse(POLICY['live_execution_enabled']);self.assertFalse(POLICY['broker_orders_enabled'])
    def test_daily_report_idempotent_and_dated(self):
        self.w.cycle('2026-10-27T15:00:00Z',[],['quotes missing'])
        a=self.w.report('daily','2026-10-27T15:01:00Z')
        b=self.w.report('daily','2026-10-27T16:01:00Z')
        self.assertEqual(a,b);self.assertEqual(a['observed_cycles'],1)
    def test_weekly_previous_completed_week_not_current_results(self):
        self.w.cycle('2026-10-27T15:00:00Z',[],[])
        a=self.w.report('weekly','2026-10-27T15:01:00Z')
        self.assertEqual(a['period_start'],'2026-10-19')
        self.assertEqual(a['period_end'],'2026-10-25')
        self.assertTrue(a['evidence_gap']);self.assertIsNone(a['last_observed_snapshot'])

if __name__=='__main__':unittest.main()
