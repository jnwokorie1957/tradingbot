import unittest
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
from research_monitor.atlas_nas15_prospective import received_minutes, session_coverage
from research_monitor.audited_run import NY


class ProspectiveReceiptChecks(unittest.TestCase):
    def row(self,seq,source,bid,receipt):return (seq,'NAS100',int(source*1000),bid,bid+1.,1,int(receipt*1000))

    def test_pre_freeze_forming_minute_and_late_revisions_are_excluded(self):
        grouped=[(61.,[self.row(1,61.,100.,61.)]),(126.,[self.row(2,126.,110.,126.)]),(127.,[self.row(3,110.,999.,127.)])]
        bars,at,late=received_minutes(grouped,{'NAS100':0},0.)
        self.assertEqual(bars['NAS100'][60]['close'],100.)
        self.assertEqual(bars['NAS100'][60]['high'],100.)
        self.assertEqual(at['NAS100'][60],126.)
        self.assertEqual(late['NAS100'],1)

    def test_only_received_quotes_contribute_to_completed_ohlc(self):
        grouped=[(130.,[self.row(1,61.,100.,130.),self.row(2,80.,101.,130.),self.row(3,119.,99.,130.)])]
        bars,at,_=received_minutes(grouped,{'NAS100':0},0.,{'NAS100':.1})
        b=bars['NAS100'][60]
        self.assertEqual((b['open'],b['high'],b['low'],b['close']),(100.,101.,99.,99.))
        self.assertEqual(b['spread'],10.)
        self.assertEqual(at['NAS100'][60],130.)

    def test_future_dated_clock_is_rejected(self):
        with self.assertRaises(ValueError):received_minutes([(61.,[self.row(1,70.,100.,61.)])],{'NAS100':0},0.)

    def test_later_receipts_cannot_change_already_finalized_bar(self):
        prefix=[(61.,[self.row(1,61.,100.,61.)]),(126.,[self.row(2,126.,110.,126.)])]
        a=received_minutes(prefix,{'NAS100':0},0.)[0]['NAS100'][60]
        b=received_minutes(prefix+[(190.,[self.row(3,190.,9999.,190.)])],{'NAS100':0},0.)[0]['NAS100'][60]
        self.assertEqual(a,b)

    def test_complete_session_requires_both_symbols_and_closed_session(self):
        start=datetime(2026,11,2,9,30,tzinfo=NY).timestamp()
        bars={s:{int(start+i*60):None for i in range(n)} for s,n in [('NAS100',351),('SPX500',350)]}
        end=datetime(2026,11,2,16,15,tzinfo=NY).timestamp()
        self.assertEqual(session_coverage(bars,end)['complete_sessions'],[])
        bars['SPX500'][int(start+350*60)]=None
        self.assertEqual(session_coverage(bars,end-1)['complete_sessions'],[])
        self.assertEqual(session_coverage(bars,end)['complete_sessions'],['2026-11-02'])

    def test_finite_receipt_replay_snapshots_new_quotes_and_scores_only_postfreeze_intents(self):
        from research_monitor.atlas_nas15_prospective import evaluate
        from research_monitor.atlas_opportunity_study import COSTS
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'future';folder.mkdir();source=root/'collector.sqlite'
            db=sqlite3.connect(source)
            db.execute('CREATE TABLE quotes(symbol TEXT,raw_ms INTEGER,bid REAL,ask REAL,occurrence INTEGER,receipt_ms INTEGER)')
            for day in range(2,7):
                start=datetime(2026,11,day,9,30,tzinfo=NY).timestamp()
                for minute in list(range(351))+[390,392]:
                    t=start+minute*60
                    for symbol in ['NAS100','SPX500']:
                        db.execute('INSERT INTO quotes VALUES(?,?,?,?,?,?)',(symbol,int(t*1000),100.,100.1,1,int((t+1)*1000)))
            db.commit();db.close()
            freeze=datetime(2026,11,1,23,tzinfo=timezone.utc).timestamp()
            through=datetime(2026,11,6,16,15,tzinfo=NY).timestamp()
            protocol=dict(freeze_epoch=freeze,collector_database='collector.sqlite',offset_hours={'NAS100':0,'SPX500':0},
                          profiles=['control','h4_long'],metadata={s:dict(point=.1,trade_tick_size=.1,trade_tick_value_loss=10.,trade_contract_size=100.,volume_min=.01,volume_step=.01,volume_max=1000.,assumed_margin_rate=.005) for s in ['NAS100','SPX500']})
            (folder/'protocol.json').write_text(json.dumps(protocol));(folder/'warmup_receipts.json').write_text(json.dumps({'NAS100':[],'SPX500':[]}));(folder/'progress.json').write_text(json.dumps(dict(last_scored_sessions=[])))
            t=datetime(2026,11,2,9,45,tzinfo=NY).timestamp()
            signal=dict(side=1,stop=90.,reference=100.,decision=t,entry_at=t+60,atr14=10.,trend_aligned=True,strong_close=True,features={})
            base={'NAS15':dict(symbol='NAS100',signals={t:signal},exits=[],rr=1.5,start=540,end=900,direction='long_only',hypothesis='baseline',quality='control',confirmation='control'),
                  'SPX15':dict(symbol='SPX500',signals={},exits=[],rr=1.5,start=585,end=720,direction='long_only',hypothesis='baseline',quality='control',confirmation='control')}
            empty={'NAS100':[],'SPX500':[]}
            with patch('research_monitor.atlas_nas15_prospective.load',return_value=(base,{s:dict(m) for s,m in protocol['metadata'].items()},{},empty,[])), \
                 patch('research_monitor.atlas_nas15_prospective.build_lane',side_effect=lambda symbol,minutes,one,native,lane,breakout:lane), \
                 patch('research_monitor.atlas_nas15_prospective.make_variants',side_effect=lambda lanes,one:{'control':lanes,'h4_long':lanes}):
                evaluate(root,folder,protocol,through,False)
            progress=json.loads((folder/'progress.json').read_text());batch=root/progress['last_batch'];results=json.loads((batch/'results.json').read_text())
            self.assertEqual(len(results),4)
            for r in results:
                self.assertEqual(r['trades'],1);self.assertEqual(r['open_positions'],0);self.assertFalse(r['actual_order_fills'])
            self.assertEqual(len(progress['last_scored_sessions']),5)


if __name__=='__main__':unittest.main()
