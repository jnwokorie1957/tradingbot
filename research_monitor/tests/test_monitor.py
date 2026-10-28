import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from html.parser import HTMLParser
from datetime import datetime,timezone
from research_monitor.telemetry import Reporter
from research_monitor.server import make_handler,STATIC
from research_monitor.local_run import run_case,signals
from research_monitor.parallel_run import LANES

class MonitorChecks(unittest.TestCase):
    def test_four_lanes_have_separate_strategy_and_storage_identities(self):
        self.assertEqual(len(LANES),4);self.assertEqual(len({x['id'] for x in LANES}),4)
        self.assertEqual(len({(x['symbol'],x['minutes'],x['family']) for x in LANES}),4)
    def test_parallel_endpoint_returns_only_allowlisted_lane_snapshots(self):
        with tempfile.TemporaryDirectory() as d:
            for lane in LANES:
                r=Reporter(Path(d)/'lanes'/lane['id']);r.begin(lane['id'],lane['symbol'],str(lane['minutes'])+'m',lane['family'])
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(d));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                value=json.load(urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/lanes'))
                self.assertEqual({x['lane_id'] for x in value['lanes']},{x['id'] for x in LANES})
                self.assertTrue(all(x['status']=='running' for x in value['lanes']))
            finally:server.shutdown();server.server_close();thread.join()
    def test_feature_filters_are_causal_and_direction_is_explicit(self):
        begin=int(datetime(2026,10,1,12,0,tzinfo=timezone.utc).timestamp())
        bars=[dict(t=begin+i*900,open=100+i*.2,high=100+i*.2+.02,low=100+i*.2-.8,close=100+i*.2,volume=1) for i in range(30)]
        base=signals(bars,'SPX500',15,10,'none')
        prefix=signals(bars[:14],'SPX500',15,10,'none')
        self.assertTrue(base);self.assertEqual(prefix,{k:v for k,v in base.items() if k<=bars[13]['t']+900})
        self.assertEqual(signals(bars,'SPX500',15,10,'short_only'),{})
        strong=signals(bars,'SPX500',15,10,'close65')
        self.assertTrue(set(strong).issubset(base))
        for row in strong.values():self.assertEqual(row['side'],1)
    def test_unknown_filter_cannot_silently_change_rules(self):
        begin=int(datetime(2026,10,1,14,0,tzinfo=timezone.utc).timestamp())
        bar=dict(t=begin,open=100,high=101,low=99,close=100,volume=1)
        with self.assertRaises(ValueError):signals([bar],'SPX500',15,10,'unregistered')
    def test_windows_reader_lock_is_retried_without_losing_snapshot(self):
        import os
        original=os.replace;calls=[]
        def transient(a,b):
            calls.append(1)
            if len(calls)<=2:raise PermissionError('Concurrent reader')
            return original(a,b)
        with tempfile.TemporaryDirectory() as d,patch('research_monitor.telemetry.os.replace',side_effect=transient):
            r=Reporter(d);r.begin('a','NAS100','5m','Pullback')
            self.assertEqual(json.loads((Path(d)/'state.json').read_text())['id'],'a')
            self.assertEqual(len(calls),3)
    def test_snapshot_is_atomic_and_finite(self):
        with tempfile.TemporaryDirectory() as d:
            r=Reporter(d,0);r.begin('one','NAS100','5m','Pullback')
            for i in range(305):r.candle(i,1,2,.5,1.5)
            r.update(balance=501,equity=502);r.finish()
            value=json.loads((Path(d)/'state.json').read_text())
            self.assertEqual(value['status'],'completed');self.assertEqual(len(value['candles']),300)
            self.assertEqual(value['candle_count'],305);self.assertFalse(list(Path(d).glob('*.tmp')))
    def test_partial_candle_does_not_increment_count(self):
        with tempfile.TemporaryDirectory() as d:
            r=Reporter(d);r.begin('a','NAS100','5m','Pullback');r.candle(0,1,2,.5,1.2);r.candle(0,1,3,.5,2.2)
            self.assertEqual(r.state['candle_count'],1);self.assertEqual(r.state['candles'][0]['high'],3)
    def test_new_id_resets_state(self):
        with tempfile.TemporaryDirectory() as d:
            r=Reporter(d);r.begin('one','NAS100','5m','Pullback');r.event('entry',time=0,price=10)
            r.begin('two','SPX500','15m','Breakout');self.assertEqual(r.state['events'],[])
            self.assertEqual(r.state['balance'],500);self.assertEqual(r.state['id'],'two')
    def test_server_denies_private_files_and_writes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'secret.txt').write_text('private')
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(d));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                root=f'http://127.0.0.1:{server.server_port}'
                self.assertEqual(json.load(urllib.request.urlopen(root+'/api/state'))['status'],'idle')
                for path in ['/secret.txt','/../secret.txt','/api/../secret.txt']:
                    with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(root+path)
                    self.assertEqual(e.exception.code,404)
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(root+'/api/state',data=b'{}',method='POST'))
                self.assertEqual(e.exception.code,501)
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(root+'/',headers={'Host':'outside.example'}))
                self.assertEqual(e.exception.code,403)
            finally:server.shutdown();server.server_close();thread.join()
    def test_visible_words_and_title(self):
        class Text(HTMLParser):
            def __init__(self):super().__init__();self.text=[]
            def handle_data(self,data):self.text.append(data)
        p=Text();p.feed((STATIC/'index.html').read_text(encoding='utf-8-sig'));value=' '.join(p.text).lower()
        self.assertIn('trade dashboard',value)
        for word in ['demo','test']:self.assertNotIn(word,value)
    def case(self,decision,high=100,low=100):
        start=decision-60
        rows=[dict(t=start+i*60,open=100,high=high if i==2 else 100,low=low if i==2 else 100,close=100,spread=0,volume=1) for i in range(10)]
        source={('NAS100',1):rows,('NAS100',5):[]}
        meta=dict(trade_tick_size=.1,trade_tick_value_loss=.1,volume_min=1,volume_step=1,point=.1)
        sig={decision:dict(side=1,stop=99,reference=100,decision=decision,entry_at=decision+60)}
        with tempfile.TemporaryDirectory() as d:
            r=Reporter(d,0)
            with patch('research_monitor.local_run.signals',return_value=sig):
                result=run_case(source,'NAS100',5,meta,dict(lookback=10,rr=1.,filter='none'),'Development',['2026-10-01'],r,0,1,1)
            return result,r.state
    def test_entry_has_real_causal_delay_and_adverse_ordering(self):
        at=int(datetime(2026,10,1,14,0,tzinfo=timezone.utc).timestamp())
        result,state=self.case(at,102,98)
        entries=[e for e in state['events'] if e['kind']=='entry'];plans=[e for e in state['events'] if e['kind']=='plan']
        self.assertEqual(len(entries),1);self.assertGreater(entries[0]['time'],plans[0]['time'])
        self.assertEqual(result['outcomes'],1);self.assertLess(result['sum_R'],0)
        self.assertEqual(result['status'],'completed');self.assertFalse(result['qualified'])
    def test_decision_at_noon_cannot_fill_after_window(self):
        at=int(datetime(2026,10,1,16,0,tzinfo=timezone.utc).timestamp())
        result,state=self.case(at,102,98)
        self.assertEqual(result['outcomes'],0);self.assertEqual(result['skips']['entry_outside_window'],1)
        self.assertFalse(any(e['kind']=='entry' for e in state['events']))

if __name__=='__main__':unittest.main()
