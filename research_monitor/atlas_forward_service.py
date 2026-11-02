"""One checkpointed MT5 quote reader with local virtual books. No broker orders."""
import argparse,copy,hashlib,json,os,sqlite3,threading,time
from collections import Counter,defaultdict
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import MetaTrader5 as mt5
from .atlas_live_core import PaperBook
from .atlas_capture_inputs import build_lane
from .portfolio_inputs import load_lanes
from .portfolio_discipline_rules import apply
from .audited_run import read_bars
from .native_data import aggregate
from .atlas_opportunity_study import COSTS
from .atlas_portfolio_controller import APPROVED


class ReadOnlyQuotes:
    """Only quote/metadata calls are implemented;no execution interface exists."""
    def connect(self):return mt5.initialize(r'C:\Program Files\MetaTrader 5\terminal64.exe',timeout=15000) and mt5.terminal_info().connected
    def quote(self,symbol):return mt5.symbol_info_tick(symbol)
    def metadata(self,symbol):
        i=mt5.symbol_info(symbol);return {k:getattr(i,k) for k in ['trade_tick_size','trade_tick_value_loss','trade_tick_value_profit','trade_contract_size','volume_min','volume_step','volume_max']}
    def ticks(self,symbol,start,end):return mt5.copy_ticks_range(symbol,datetime.fromtimestamp(start,timezone.utc),datetime.fromtimestamp(end,timezone.utc),mt5.COPY_TICKS_ALL)
    def status(self):
        t=mt5.terminal_info();return dict(connected=bool(t.connected),broker_algorithmic_trading_enabled=bool(t.trade_allowed))
    def margin_ratio(self,symbol,m,ask):
        value=mt5.order_calc_margin(mt5.ORDER_TYPE_BUY,symbol,m['volume_min'],ask)
        return value/(m['volume_min']*m['trade_contract_size']*ask) if value is not None else None
    def close(self):mt5.shutdown()


def atomic(path,data):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data,indent=2),encoding='utf-8');temp.replace(path)


def book_state(book):
    for n in book.lanes:
        book.events[n]=book.events[n][book.indices[n]:];book.indices[n]=0;book.exits[n]=book.exits[n][book.exit_indices[n]:];book.exit_indices[n]=0
    return dict(cash=book.cash,peak=book.peak,dd=book.dd,positions=book.positions,latest=book.latest,busy=book.busy,history=book.history,pending=book.pending,seen=list(book.seen),fills=book.fills,guards={n:g.__dict__ for n,g in book.guards.items()},events=book.events,exits=book.exits,last_exit=book.last_exit,max_risk=book.max_risk,max_margin=book.max_margin,max_positions=book.max_positions,max_gross=book.max_gross,risk_day=book.risk_day,day_start=book.day_start,daily_paused=book.daily_paused,drawdown_paused=book.drawdown_paused)


def restore(book,data):
    for key,value in data.items():
        if key=='guards':
            for n,v in value.items():book.guards[n].__dict__.update(v)
        elif key=='seen':book.seen=set(value)
        elif key=='last_exit':book.last_exit={n:{int(k):v for k,v in d.items()} for n,d in value.items()}
        elif key in ('events','exits'):
            setattr(book,key,{n:[tuple(x) for x in values] for n,values in value.items()})
        else:setattr(book,key,value)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,default=8878);p.add_argument('--candidate',choices=['approved5000'],default='approved5000');p.add_argument('--candidate-capital',type=float,default=5000.);p.add_argument('--cohort',default='atlas-forward-v1');args=p.parse_args();root=args.root;port=args.port
    assert args.candidate_capital==5000.,'User-approved new forward equity must be5000USD'
    if not args.cohort.startswith('atlas-forward-v') or not args.cohort.removeprefix('atlas-forward-v').isdigit():raise ValueError('Invalid cohort identity')
    folder=root/'work/tradingbot/local-results'/args.cohort;folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'worker.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    db=sqlite3.connect(folder/'observations.sqlite');db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE IF NOT EXISTS quotes(symbol TEXT,raw_ms INTEGER,bid REAL,ask REAL,occurrence INTEGER,receipt_ms INTEGER,PRIMARY KEY(symbol,raw_ms,bid,ask,occurrence))');db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,book TEXT,kind TEXT,receipt_ms INTEGER,payload TEXT)');db.execute('CREATE TABLE IF NOT EXISTS minutes(symbol TEXT,t INTEGER,payload TEXT,PRIMARY KEY(symbol,t))');db.commit()
    start=time.time();config_path=folder/'freeze.json';names=['atlas_forward_service.py','atlas_portfolio_controller.py','atlas_capture_core.py','atlas_live_core.py','atlas_capture_inputs.py','portfolio_inputs.py','portfolio_discipline_rules.py','frequency_signals.py','atlas_raw_rsi.py','native_data.py','entry_quality.py','entry_quality_v2.py','hourly_entry_quality.py','confirmation_quality.py','risk_review.py','audited_run.py','atlas_opportunity_study.py'];paths=[Path(__file__).with_name(n) for n in names]+[Path(__file__).parent.parent/'trading_pipeline/engine_v4.py']
    hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}
    if config_path.exists():
        config=json.loads(config_path.read_text());assert config['source_hashes']==hashes,'Frozen forward code changed;new cohort required,do not silently retune';assert config['candidate']==args.candidate and config['candidate_capital']==args.candidate_capital,'Sizing changed;freeze a new cohort rather than rewrite prior results'
    else:
        config=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),cohort_start_utc=start,objective='25-40percentannualnet,portfolioDDbelow10',paper_only=True,live_execution_available=False,initial=5000.,candidate=args.candidate,candidate_capital=args.candidate_capital,approved_settings=APPROVED,books='Original500USDbenchmark and approved5000USDsharedportfolio,eachstandard/higher. No lower-cap researchcase is activated.',risk='5000book:min(0.5percentequity,25USD)all-inpertrade,1percentequitycombined,2percentdailypause,10percentDDpause,no dailytradecountquota. Broker margin plus gross planned-lossreserves checked. Same-symbolconflicts/duplicatesveto;correlatedindexrisksumsgross,no nettingcredit.',clock='Calibrate0/2/3hourraw-UTCoffsetfrom10distinctfreshreceipts;do not assume US DST. Require5secondfreshness,neverbackdatepaperfills.',execution='One-secondpolling;paperordersusefirstreceivedfreshquoteafterentrydeadline,adverse1/2ticks,6/12roundtripperlotproxy. Stops/targets evaluated on receivedquotes,not guaranteedfills or liquidity. Receipt gaps/skippedrawticks retained for subsequentadverse-path audits.',validation='Genuinelynewreceiptsafterfreezeonly. Warmuppricesneverfinanciallyscored. No optimization oncohort. 70-75percentWRstretchnotmandatory. Needatleast100portfoliooutcomes andmultiplemarketblocks before repeatability assessment;annualgoalrequiresfullunseenyear. Worker availability is local-computer dependent.',source_hashes=hashes)
        atomic(config_path,config)
        (folder/'source').mkdir(exist_ok=True)
        for f in paths:(folder/'source'/f.name).write_bytes(f.read_bytes())
    lanes,meta,folders=load_lanes(root);lanes=apply(lanes,'nas15_eff_after2');one={s:sum([read_bars(f/f'{s}_M1.csv','ny_dst_inferred') for f in ps],[]) for s,ps in folders.items()};old_end={s:(bars[-1]['t']+60) for s,bars in one.items()};new_minutes={s:{} for s in one}
    for symbol,t,payload in db.execute('SELECT symbol,t,payload FROM minutes ORDER BY t'):new_minutes[symbol][t]=json.loads(payload)
    # Prior cohorts may seed indicators only. Their prices are never new financial observations.
    for prior in sorted(folder.parent.glob('atlas-forward-v*/observations.sqlite')):
        if prior.parent==folder:continue
        previous_db=sqlite3.connect(f'file:{prior.as_posix()}?mode=ro',uri=True)
        for symbol,t,payload in previous_db.execute('SELECT symbol,t,payload FROM minutes ORDER BY t'):
            if t<config['cohort_start_utc']:new_minutes[symbol].setdefault(t,json.loads(payload))
        previous_db.close()
    def sink(name):
        def record(kind,row):db.execute('INSERT INTO events(book,kind,receipt_ms,payload) VALUES(?,?,?,?)',(name,kind,int(time.time()*1000),json.dumps(row)))
        return record
    books={}
    config.update(approved_settings=APPROVED,books='Original500USD/25USDtotal benchmark preserved;new5000USDbook usesmin(0.5percentequity,25USD)pertrade,1percentequitycombined,2percentdailypause,10percentDDpause,noquotas',risk='New5000book has NO25USDaggregateceiling and NO10USDrecovery-sizingcap. Existingrecoveryentryconfirmationsretained. Grosscorrelatedindexrisk sumsallpositions,no nettingcredit.',initial=5000.);atomic(config_path,config)
    for variant in ['benchmark','candidate']:
        for cost in ['standard','higher']:
            active=copy.deepcopy(lanes)
            for l in active.values():l['signals']={};l['exits']=[]
            policy={} if variant=='benchmark' else dict(atlas5000=True,defer_busy_gate=True,allow_multiple=True,direction_guard=True)
            name=variant+'_'+cost;books[name]=PaperBook(active,meta,policy,COSTS[cost],500. if variant=='benchmark' else args.candidate_capital,sink(name))
    checkpoint_path=folder/'checkpoint.json';saved=json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {};seen_signals=set(saved.get('seen_signals',[]));last_indicator=saved.get('last_indicator',{});raw_cursor=saved.get('raw_cursor',{});completed_until=saved.get('completed_until',{s:0 for s in one})
    for name,data in saved.get('books',{}).items():restore(books[name],data)
    public=dict(status='starting',paper_only=True,broker_execution_calls=0,worker_pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),freeze_utc=config['frozen_utc'],port=port,books={},quote_receipts=0,last_poll_utc=None,clock={},candles={},recent_events=[],limitations='Historicalfees/contract/clockunverified;forwardcommissionproxy. No independentprofitabilityclaimbeforeoutcomes. ComputerandMT5mustremainavailable.')
    public['quote_receipts']=db.execute('SELECT COUNT(*) FROM quotes').fetchone()[0];public['candidate_status']='approved5000_active';public['approved_settings']=APPROVED
    mutex=threading.Lock();out=root/'outputs/atlas_opportunity_v1'
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split('?')[0]=='/status.json':
                status_file=folder/'status.json';data=status_file.read_bytes() if status_file.exists() else b'{"status":"starting","paper_only":true}'
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
            elif self.path in ('/','/report.html'):
                f=out/'report.html'
                if not f.exists():data=b'<!doctype html><title>Trade Dashboard</title><h1>Trade Dashboard</h1><p>Paper observation is starting. Results are being prepared.</p>'
                else:data=f.read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
            else:self.send_error(404)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();gateway=ReadOnlyQuotes();connected=False;calibration={s:dict(offset=None,samples=[],last_raw=0) for s in one};minute_buckets={s:{} for s in one};last_save=last_build=last_metadata=0.;first_complete_minute=time.time()//60*60+60;last_quotes={}
    try:
        while not (folder/'stop.request').exists():
            receipt=time.time();receipt_ms=int(receipt*1000)
            if not connected:
                connected=gateway.connect()
                if not connected:public.update(status='waiting_existing_MT5_connection',last_poll_utc=datetime.now(timezone.utc).isoformat());atomic(folder/'status.json',public);time.sleep(5);continue
            if receipt-last_metadata>=60:
                public.update(gateway.status());public['symbol_metadata']={}
                for symbol in one:
                    current=gateway.metadata(symbol);critical=['trade_tick_size','trade_tick_value_loss','trade_contract_size']
                    if any(abs(current[k]-meta[symbol][k])>1e-8 for k in critical):
                        for b in books.values():b.policy['entry_halt_reason']='contract_unit_change_requires_review'
                    else:
                        meta[symbol].update(current);tick=gateway.quote(symbol);rate=gateway.margin_ratio(symbol,current,tick.ask)
                        if rate is not None:meta[symbol]['assumed_margin_rate']=rate
                    public['symbol_metadata'][symbol]=dict(meta[symbol],commission_status='Estimated6/12roundtripperlot;account-specificfeesunverified')
                last_metadata=receipt
            fresh=[];received_paths={s:[] for s in one}
            for symbol in one:
                tick=gateway.quote(symbol)
                if tick is None:continue
                raw=int(tick.time_msc);c=calibration[symbol];candidate=min([0,2,3],key=lambda k:abs(raw/1000-k*3600-receipt));age=receipt-(raw/1000-candidate*3600)
                if -1<=age<=5 and raw!=c['last_raw']:
                    c['last_raw']=raw;c['samples'].append(candidate);c['samples']=c['samples'][-10:]
                    if len(c['samples'])==10 and len(set(c['samples']))==1:c['offset']=candidate
                if c['offset'] is None:continue
                normalized=raw/1000-c['offset']*3600;age=receipt-normalized
                if not -1<=age<=5:c['samples']=[];c['offset']=None;continue
                previous=float(raw_cursor.get(symbol,raw/1000-2))
                if raw/1000-previous>300:db.execute('INSERT INTO events(book,kind,receipt_ms,payload) VALUES(?,?,?,?)',('collector','data_gap',receipt_ms,json.dumps(dict(symbol=symbol,unfetched_seconds=raw/1000-previous-300))))
                start_raw=max(previous-2,raw/1000-300);ticks=gateway.ticks(symbol,start_raw,raw/1000+.001)
                if ticks is not None:
                    counts=Counter()
                    for q in ticks:
                        if q['bid']<=0 or q['ask']<q['bid']:continue
                        key=(int(q['time_msc']),float(q['bid']),float(q['ask']));counts[key]+=1
                        cur=db.execute('INSERT OR IGNORE INTO quotes VALUES(?,?,?,?,?,?)',(symbol,*key,counts[key],receipt_ms))
                        if cur.rowcount==0:continue
                        public['quote_receipts']+=1;utc=key[0]/1000-c['offset']*3600;received_paths[symbol].append((utc,key[1],key[2]));m=int(utc//60)*60
                        if utc<config['cohort_start_utc'] or m<first_complete_minute or m<completed_until[symbol]:continue
                        spread=(key[2]-key[1])/meta[symbol].get('point',meta[symbol]['trade_tick_size']);b=minute_buckets[symbol].setdefault(m,dict(t=m,open=key[1],high=key[1],low=key[1],close=key[1],volume=0,spread=spread));b['high']=max(b['high'],key[1]);b['low']=min(b['low'],key[1]);b['close']=key[1];b['volume']+=1;b['spread']=min(b['spread'],spread)
                    raw_cursor[symbol]=raw/1000
                for m in sorted(list(minute_buckets[symbol])):
                    if m+65>receipt:continue
                    b=minute_buckets[symbol].pop(m);new_minutes[symbol][m]=b;db.execute('INSERT OR IGNORE INTO minutes VALUES(?,?,?)',(symbol,m,json.dumps(b)));completed_until[symbol]=max(completed_until[symbol],m+60)
                last_quotes[symbol]=dict(source_utc=datetime.fromtimestamp(normalized,timezone.utc).isoformat(),receipt_utc=datetime.fromtimestamp(receipt,timezone.utc).isoformat(),age_seconds=age,bid=float(tick.bid),ask=float(tick.ask));fresh.append((symbol,normalized,float(tick.bid),float(tick.ask),raw))
            newest_bar=max(completed_until.values(),default=0)//300*300
            if newest_bar>last_build:
                # Complete bars are computed before the60second entry delay;never fill historical intents.
                for symbol in one:
                    combined=one[symbol]+[b for t,b in sorted(new_minutes[symbol].items()) if t>=old_end[symbol]]
                    for name,base in lanes.items():
                        if base['symbol']!=symbol:continue
                        minutes=5 if name=='NAS5' else 15;native=aggregate(combined,minutes);built=build_lane(symbol,minutes,combined,native,base,minutes==15)
                        for decision,s in built['signals'].items():
                            key=f'{name}|{decision}'
                            if decision<config['cohort_start_utc'] or key in seen_signals:continue
                            seen_signals.add(key)
                            for book in books.values():book.enqueue(name,s)
                        for when,side in built['exits']:
                            if when<=last_indicator.get(name,config['cohort_start_utc']):continue
                            for book in books.values():book.exits[name].append((when,side))
                        last_indicator[name]=max([when for when,_ in built['exits'] if when>=config['cohort_start_utc']]+[last_indicator.get(name,config['cohort_start_utc'])])
                        public['candles'][name]=[b for b in native if b['t']>=config['cohort_start_utc']][-60:]
                last_build=newest_bar
            # One observed quote per poll: virtual fills are receipt-time events,never retrospective tick fills.
            for symbol,source_at,bid,ask,raw in fresh:
                if raw==saved.get('last_processed_raw',{}).get(symbol):continue
                execution_tick=gateway.quote(symbol);execution_receipt=time.time();execution_source=execution_tick.time_msc/1000-calibration[symbol]['offset']*3600
                if not -1<=execution_receipt-execution_source<=5:continue
                for book in books.values():
                    book.received_path(symbol,execution_receipt,float(execution_tick.bid),float(execution_tick.ask),received_paths[symbol])
                    book.quote(symbol,execution_receipt,float(execution_tick.bid),float(execution_tick.ask),fresh=True,source_time=execution_source)
                saved.setdefault('last_processed_raw',{})[symbol]=int(execution_tick.time_msc)
            with mutex:
                public.update(status='observing_paper_forward' if all(c['offset'] is not None for c in calibration.values()) else 'calibrating_or_waiting_fresh_quotes',last_poll_utc=datetime.now(timezone.utc).isoformat(),clock={s:dict(offset_hours=c['offset'],fresh_samples=len(c['samples'])) for s,c in calibration.items()},last_quotes=last_quotes,completed_minutes={s:len(v) for s,v in new_minutes.items()},books={n:dict(b.result(),positions=list(b.positions.values()),recent_fills=b.fills[-15:],pending=sum(len(p) for p in b.pending.values())) for n,b in books.items()})
            if receipt-last_save>=10:
                if any(hashlib.sha256(f.read_bytes()).hexdigest()!=hashes[f.name] for f in paths):raise RuntimeError('Frozen code identity changed;checkpoint preserved,new research cohort required')
                db.commit();atomic(checkpoint_path,dict(books={n:book_state(b) for n,b in books.items()},seen_signals=list(seen_signals),last_indicator=last_indicator,raw_cursor=raw_cursor,completed_until=completed_until,last_processed_raw=saved.get('last_processed_raw',{})));atomic(folder/'status.json',public)
                for book in books.values():book.decisions=[]
                last_save=receipt
            time.sleep(1)
    except Exception as exc:
        public.update(status='failed',error_type=type(exc).__name__,error=str(exc));atomic(folder/'status.json',public);raise
    finally:
        db.commit();atomic(checkpoint_path,dict(books={n:book_state(b) for n,b in books.items()},seen_signals=list(seen_signals),last_indicator=last_indicator,raw_cursor=raw_cursor,completed_until=completed_until,last_processed_raw=saved.get('last_processed_raw',{})));gateway.close();server.shutdown();db.close();public['status']='stopped' if (folder/'stop.request').exists() else public['status'];atomic(folder/'status.json',public);lock.unlink(missing_ok=True)


if __name__=='__main__':main()
