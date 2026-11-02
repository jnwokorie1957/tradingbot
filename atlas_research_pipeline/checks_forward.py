"""Synthetic causality, adverse execution, sizing and ledger checks;no prices read."""
import unittest,json,sqlite3,tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
from research_monitor.atlas_portfolio_controller import allocate
from atlas_exit_research.data import NY
from .forward_core import PairedPaperBook,LedgerAudit,availability_prefix,signal_available,windows

META={'NAS100':dict(trade_tick_size=1.,trade_tick_value_loss=1.,trade_contract_size=1.,volume_min=.1,volume_step=.1,volume_max=100.,assumed_margin_rate=.005)}
LANE={'NAS15':dict(symbol='NAS100',rr=2.,start=570,end=960,signals={},exits=[])}
AT=datetime(2026,11,3,10,tzinfo=NY).timestamp()


def prepared(cost=None,side=1,nas_minutes=90):
    cost=cost or dict(spread=1.,fee=0.,slip_ticks=0,exit_delay=0.)
    b=PairedPaperBook(LANE,META,dict(atlas5000=True,allow_multiple=True,direction_guard=True),cost,5000.,nas_minutes=nas_minutes);q=.5;entry=100.;risk=(5+cost['slip_ticks']+cost['fee'])*q
    b.latest['NAS100']=(100.,101.,AT);b.positions['p']=dict(lane='NAS15',symbol='NAS100',side=side,entry=entry,stop=entry-side*5,target=entry+side*10,quantity=q,at=AT,expiry=AT+3600,risk=risk,margin=1.,decision=AT-60,pending_exit=None)
    b._record(dict(id='p',lane='NAS15',status='EXECUTED',planned_risk=risk,lane_budget=25.,total_budget=50.,used_risk=0.,side=side,entry_quote=entry,quantity=q,observed_at=AT));return b


class ForwardChecks(unittest.TestCase):
    def test_late_earlier_feature_cannot_leak_into_signal(self):
        minutes={t:{}for t in range(60,1260,60)};available={t:t+65 for t in minutes};available[60]=3000;times,prefix=availability_prefix(minutes,available,0)
        self.assertEqual(signal_available(1260,times,prefix,available,0),3000)
        del available[1200]
        self.assertIsNone(signal_available(1260,times,prefix,available,0))
    def test_missing_day_is_visible_not_silently_dropped(self):
        start=datetime(2026,11,3,tzinfo=NY).timestamp();through=datetime(2026,11,4,16,15,tzinfo=NY).timestamp();a=datetime(2026,11,3,9,30,tzinfo=NY).timestamp();mins={s:{t:None for t in range(int(a),int(a)+390*60,60)}for s in ['NAS100','SPX500']};r=windows(start,through,mins)
        self.assertEqual(r['covered_sessions'],['2026-11-03']);self.assertEqual(r['uncovered_sessions'],['2026-11-04'])
    def test_reference_calendar_early_close_and_holiday(self):
        start=datetime(2026,11,26,tzinfo=NY).timestamp();through=datetime(2026,11,27,16,15,tzinfo=NY).timestamp();r=windows(start,through,{'NAS100':{},'SPX500':{}})
        self.assertEqual(len(r['sessions']),1);self.assertEqual(r['sessions'][0]['expected'],210);self.assertEqual(r['sessions'][0]['required'],208)
    def test_gap_loss_is_not_clipped_and_ledger_reconciles(self):
        b=prepared();a=LedgerAudit(META,b.cost);a.point(b,'NAS100',100,101);path=[(AT+10,94.,95.),(AT+15,90.,91.),(AT+20,92.,93.)];a.path_bound({'NAS100':path},AT+20);b.observed_path('NAS100',AT+20,92,93,path);b.quote('NAS100',AT+20,92,93,source_time=AT+20);a.point(b,'NAS100',92,93)
        self.assertEqual(b.fills[0]['pnl'],-5.);self.assertGreater(abs(b.fills[0]['pnl']),b.fills[0]['planned_risk']);self.assertAlmostEqual(a.cash,b.cash);self.assertGreaterEqual(a.result()['conservative_observed_path_drawdown_bound_pct'],a.result()['receipt_marked_drawdown_pct'])
    def test_severe_delay_cannot_close_at_trigger_receipt(self):
        b=prepared(dict(spread=2.,fee=18.,slip_ticks=4,exit_delay=1.));path=[(AT+10,94.,95.),(AT+15,90.,91.),(AT+20,92.,93.)];b.observed_path('NAS100',AT+20,92,93,path);b.quote('NAS100',AT+20,92,93,source_time=AT+20)
        self.assertFalse(b.fills)
        b.observed_path('NAS100',AT+20.5,96,97,[(AT+20.5,96,97)]);self.assertFalse(b.fills)
        b.observed_path('NAS100',AT+21,97,98,[(AT+21,97,98)]);self.assertEqual(b.fills[0]['exit_at'],AT+21);self.assertEqual(b.fills[0]['exit'],86.);self.assertEqual(b.fills[0]['pnl'],-16.)
    def test_short_target_profit_capped_and_audited(self):
        b=prepared(side=-1);a=LedgerAudit(META,b.cost);a.point(b,'NAS100',100,101);path=[(AT+10,85.,86.),(AT+20,84.,85.)];b.observed_path('NAS100',AT+20,84,85,path);b.quote('NAS100',AT+20,84,85,source_time=AT+20);a.point(b,'NAS100',84,85)
        self.assertEqual(b.fills[0]['exit'],90.);self.assertEqual(b.fills[0]['pnl'],5.);self.assertAlmostEqual(a.cash,b.cash)
    def test_expiry_is_actual_receipt_plus_holding_and_capped(self):
        b=prepared();self.assertEqual(b.positions['p']['expiry'],AT+5400);b.positions['p']['at']=datetime(2026,11,3,15,40,tzinfo=NY).timestamp();b._record(b.decisions[-1]);self.assertEqual(b.positions['p']['expiry'],datetime(2026,11,3,16,tzinfo=NY).timestamp())
    def test_stale_quote_cannot_fill(self):
        b=prepared()
        with self.assertRaises(ValueError):b.quote('NAS100',AT+100,94,95,fresh=False,source_time=AT)
        self.assertFalse(b.fills)
    def test_approved_all_in_sizing_and_shared_risk_unchanged(self):
        meta=META['NAS100'];p=allocate(meta,100,5,1,6,5000,5000,{},'NAS100',1,5000,5000);self.assertLessEqual(p['perlot']*p['quantity'],25);self.assertEqual(p['total_budget'],50)
        positions={'one':dict(symbol='NAS100',side=1,risk=25.,margin=5.)};p=allocate(meta,100,5,1,6,5000,4990,positions,'NAS100',1,5000,5000);self.assertLessEqual(25+p['perlot']*p['quantity'],49.9+1e-8);p=allocate(meta,100,5,1,6,5000,4990,positions,'NAS100',-1,5000,5000);self.assertIn('conflicting_same_symbol_exposure',p['reasons'])
    def test_complete_synthetic_receipt_replay_six_books_and_audits(self):
        from . import pair_forward as f
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);folder=root/'prospective';folder.mkdir();(folder/'protocol.json').write_text('{}');(folder/'progress.json').write_text(json.dumps(dict(last_scored_sessions=[])));(folder/'warmup_receipts.json').write_text(json.dumps(dict(NAS100=[],SPX500=[])));path=root/'quotes.sqlite';db=sqlite3.connect(path);db.execute('CREATE TABLE quotes(symbol TEXT,raw_ms INTEGER,bid REAL,ask REAL,occurrence INTEGER,receipt_ms INTEGER)');days=[3,4,5,6,9]
            for day in days:
                a=int(datetime(2026,11,day,9,30,tzinfo=NY).timestamp())
                for t in range(a,a+406*60,60):
                    for symbol in ['NAS100','SPX500']:db.execute('INSERT INTO quotes VALUES(?,?,?,?,?,?)',(symbol,(t+10800)*1000,100.,100.1,0,int((t+.2)*1000)))
            db.commit();db.close();meta=dict(META,SPX500=dict(META['NAS100']));base={n:dict(symbol=s,start=570,end=960,hypothesis='none',quality='none',confirmation='none',direction='long_only',rr=1.5,signals={},exits=[])for n,s in [('SPX15','SPX500'),('NAS15','NAS100')]};first=datetime(2026,11,3,tzinfo=NY).timestamp();through=datetime(2026,11,9,16,15,tzinfo=NY).timestamp();p=dict(freeze_epoch=first-3600,financial_start_epoch=first,offset_hours=dict(NAS100=3,SPX500=3),metadata=meta,collector_database='quotes.sqlite')
            def lane(symbol,minutes,one,native,b,breakout):
                signals={}
                for day in days:
                    t=datetime(2026,11,day,9,45,tzinfo=NY).timestamp();signals[t]=dict(decision=t,entry_at=t+60,side=1,stop=95.,trend_aligned=True)
                return dict(b,signals=signals)
            with ExitStack()as stack:
                stack.enter_context(patch.object(f,'load',return_value=(base,meta,{},dict(NAS100=[],SPX500=[]),[])));stack.enter_context(patch.object(f,'build_lane',side_effect=lane))
                for name in ['reject','reject_quality','reject_confirmation','reject_state']:stack.enter_context(patch('research_monitor.atlas_live_core.'+name,return_value=None))
                f.replay(root,folder,p,through)
            batch=next((folder/'batches').iterdir());records=json.loads((batch/'results.json').read_text());self.assertEqual(len(records),6)
            for r in records:
                self.assertEqual(r['portfolio']['trades'],10);self.assertEqual(r['account']['open_positions'],0);self.assertLess(r['audit']['maximum_equity_difference'],1e-6);self.assertLess(r['nas_audit']['maximum_equity_difference'],1e-6)
            self.assertEqual(json.loads((batch/'completed.json').read_text())['qualified_paths'],True)


if __name__=='__main__':unittest.main()
