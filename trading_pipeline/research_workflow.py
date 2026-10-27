"""Research governance extension. No broker transport or automatic execution.

Uses the existing Journal; durable claims never expire or silently retry.
Evidence references are reviewer attestations, not automatic proof of authenticity.
"""
import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .journal import Journal, canonical, digest

STATES = {'RESEARCH', 'CANDIDATE', 'CHAMPION', 'QUARANTINED', 'RETIRED'}
KINDS = {'historical_backtest', 'out_of_sample', 'synthetic', 'local_forward', 'ibkr_paper'}
POLICY = dict(starting_equity=500,aspirational_equity=10000,trade_fraction=.005,
              trade_dollar_cap=2.5,portfolio_fraction=.01,daily_pause=.02,
              drawdown_pause=.10,live_execution_enabled=False,broker_orders_enabled=False)

def finite(value):
    return type(value) in (int,float) and math.isfinite(value)

def instant(value):
    result = datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result.astimezone(timezone.utc)

def assessment(e):
    """Stricter provisional screen, never an execution permission."""
    reasons=[]
    if e.get('kind') != 'out_of_sample': reasons.append('real_unseen_oos_required')
    for field in ('unseen','causal_quotes','costs_verified','margins_verified',
                  'calendar_verified','risk_controls_pass','stress_pass','all_windows_positive'):
        if e.get(field) is not True: reasons.append(field)
    for field in ('independent_review','dataset_hash','protocol_hash','result_hash'):
        if not isinstance(e.get(field),str) or not e[field].strip(): reasons.append(field)
    for field in ('dataset_hash','protocol_hash','result_hash'):
        h=e.get(field)
        if not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h): reasons.append('invalid_'+field)
    for field,limit,strict in (('trades',300,False),('trade_days',30,False),
            ('win_rate',.60,True),('profit_factor',1.5,True),('net_expectancy',0,True),
            ('expectancy_ci_lower',0,True)):
        v=e.get(field)
        if not finite(v) or (v<=limit if strict else v<limit): reasons.append(field)
    if type(e.get('trades')) is not int or type(e.get('trade_days')) is not int:
        reasons.append('integer_counts_required')
    if finite(e.get('win_rate')) and not 0<=e['win_rate']<=1: reasons.append('invalid_win_rate')
    dd=e.get('drawdown')
    if not finite(dd) or not 0<=dd<.1: reasons.append('drawdown')
    return reasons

def trade_diagnostics(trades):
    """Descriptive net diagnostics only; no invented annual Sharpe from trade samples."""
    values=[t['net_pnl'] for t in trades]
    if any(not finite(v) for v in values): raise ValueError('invalid pnl')
    wins=[v for v in values if v>0]; losses=[v for v in values if v<0]
    streak=maximum=0;regimes=defaultdict(list)
    for t in sorted(trades,key=lambda t:instant(t['exit_at'])):
        streak=streak+1 if t['net_pnl']<0 else 0;maximum=max(streak,maximum)
        regimes[t.get('regime','unknown')].append(t['net_pnl'])
    return dict(trades=len(values),win_rate=len(wins)/len(values) if values else None,
        net_expectancy=statistics.mean(values) if values else None,
        average_profit=statistics.mean(wins) if wins else None,
        average_loss=statistics.mean(losses) if losses else None,
        profit_factor=sum(wins)/-sum(losses) if losses else None,
        realized_payoff_ratio=statistics.mean(wins)/-statistics.mean(losses) if wins and losses else None,
        consecutive_losses=maximum,sharpe=None,
        sharpe_reason='Requires a complete dated equity-return series and declared annualization convention',
        regimes={k:dict(trades=len(v),net_expectancy=statistics.mean(v)) for k,v in regimes.items()})

class Workflow:
    def __init__(self,path):
        self.journal=Journal(str(path));self.db=self.journal.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS research_versions(strategy TEXT,version TEXT,spec TEXT,
          PRIMARY KEY(strategy,version));
        CREATE TABLE IF NOT EXISTS research_state(strategy TEXT,version TEXT,state TEXT,
          PRIMARY KEY(strategy,version),FOREIGN KEY(strategy,version) REFERENCES research_versions);
        CREATE UNIQUE INDEX IF NOT EXISTS one_research_champion ON research_state(state) WHERE state='CHAMPION';
        CREATE TABLE IF NOT EXISTS research_trade_reviews(trade_id TEXT PRIMARY KEY,review TEXT);
        CREATE TABLE IF NOT EXISTS research_cycle_lock(singleton INTEGER PRIMARY KEY CHECK(singleton=1),cycle TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS research_versions_immutable BEFORE UPDATE ON research_versions
          BEGIN SELECT RAISE(ABORT,'immutable version'); END;
        CREATE TRIGGER IF NOT EXISTS research_versions_no_delete BEFORE DELETE ON research_versions
          BEGIN SELECT RAISE(ABORT,'immutable version'); END;
        CREATE TRIGGER IF NOT EXISTS research_reviews_immutable BEFORE UPDATE ON research_trade_reviews
          BEGIN SELECT RAISE(ABORT,'immutable review'); END;
        CREATE TRIGGER IF NOT EXISTS research_reviews_no_delete BEFORE DELETE ON research_trade_reviews
          BEGIN SELECT RAISE(ABORT,'immutable review'); END;
        ''')
    def close(self): self.journal.close()
    def register(self,strategy,version,spec):
        required=('source','entry','exit','stop','target','regime','evidence','track')
        if any(not isinstance(spec.get(k),str) or not spec[k].strip() for k in required):
            raise ValueError('complete specification required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('INSERT INTO research_versions VALUES(?,?,?)',(strategy,version,canonical(spec)))
            self.db.execute('INSERT INTO research_state VALUES(?,?,?)',(strategy,version,'RESEARCH'))
            self.journal._append(strategy,'research_registered',dict(version=version,spec=spec))
    def transition(self,strategy,version,state,reason,evidence=None):
        if state not in STATES or not reason.strip(): raise ValueError('state/reason required')
        if state=='CHAMPION': raise ValueError('use reviewed comparison promotion')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT state FROM research_state WHERE strategy=? AND version=?',(strategy,version)).fetchone()
            if not old: raise ValueError('unknown strategy version')
            if old[0]=='RETIRED' and state!='RETIRED': raise ValueError('register a new version; retired records stay retired')
            if state=='CANDIDATE' and (not evidence or assessment(evidence)):
                raise ValueError('candidate validation incomplete')
            self.db.execute('UPDATE research_state SET state=? WHERE strategy=? AND version=?',(state,strategy,version))
            self.journal._append(strategy,'research_transition',dict(version=version,old=old[0],new=state,reason=reason,evidence=evidence))
    def promote(self,strategy,version,evidence,comparison,paper):
        if assessment(evidence): raise ValueError('validation incomplete')
        if paper.get('kind') not in ('local_forward','ibkr_paper') or paper.get('reviewed') is not True:
            raise ValueError('reviewed forward evidence required')
        if type(paper.get('trades')) is not int or paper['trades']<30 or not paper.get('review_reference'):
            raise ValueError('at least 30 independently reviewed forward trades required')
        if paper.get('risk_controls_pass') is not True or not finite(paper.get('net_expectancy')) or paper['net_expectancy']<=0:
            raise ValueError('forward risk/net evidence required')
        if not comparison.get('preregistration') or not comparison.get('review_reference'):
            raise ValueError('comparison preregistration and independent review required')
        if comparison.get('same_conditions') is not True or comparison.get('meaningful_improvement') is not True:
            raise ValueError('controlled meaningful improvement required')
        if comparison.get('protocol_hash')!=evidence['protocol_hash'] or comparison.get('challenger_result_hash')!=evidence['result_hash']:
            raise ValueError('comparison evidence binding mismatch')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row=self.db.execute('SELECT state FROM research_state WHERE strategy=? AND version=?',(strategy,version)).fetchone()
            if not row or row[0]!='CANDIDATE': raise ValueError('candidate state required')
            old=self.db.execute("SELECT strategy,version FROM research_state WHERE state='CHAMPION'").fetchone()
            if comparison.get('incumbent') != (list(old) if old else None): raise ValueError('stale incumbent comparison')
            if old:self.db.execute("UPDATE research_state SET state='CANDIDATE' WHERE strategy=? AND version=?",old)
            self.db.execute("UPDATE research_state SET state='CHAMPION' WHERE strategy=? AND version=?",(strategy,version))
            self.journal._append(strategy,'champion_promotion',dict(version=version,previous=old,
                evidence=evidence,comparison=comparison,paper=paper,execution_enabled=False))
    def review_trade(self,trade_id,review):
        for k in ('strategy','version','kind','setup','entry','exit','stop','target','net_pnl',
                  'exit_at','rule_followed','expected_behavior','observed_behavior','hypothesis','similar_trade_ids'):
            if k not in review: raise ValueError('missing '+k)
        if review['kind'] not in KINDS or not finite(review['net_pnl']): raise ValueError('invalid trade evidence')
        instant(review['exit_at'])
        if review['rule_followed'] is not None and type(review['rule_followed']) is not bool: raise ValueError('invalid compliance result')
        if not isinstance(review['similar_trade_ids'],list): raise ValueError('similar trade IDs required')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if not self.db.execute('SELECT 1 FROM research_versions WHERE strategy=? AND version=?',
                                   (review['strategy'],review['version'])).fetchone(): raise ValueError('unknown version')
            for other in review['similar_trade_ids']:
                if not self.db.execute('SELECT 1 FROM research_trade_reviews WHERE trade_id=?',(other,)).fetchone():
                    raise ValueError('unknown comparison trade')
            self.db.execute('INSERT INTO research_trade_reviews VALUES(?,?)',(trade_id,canonical(review)))
            self.journal._append(review['strategy'],'trade_review',dict(trade_id=trade_id,review=review,
                automatic_strategy_change=False,independent_test_required=True))
    def snapshot(self):
        rows=[dict(strategy=s,version=v,state=state) for s,v,state in self.db.execute(
              'SELECT strategy,version,state FROM research_state ORDER BY strategy,version')]
        # Rank eligible versions by latest admitted OOS expectancy, then drawdown.
        evidence={}
        for s,kind,p in self.db.execute("SELECT experiment,kind,payload FROM records WHERE kind IN ('research_transition','champion_promotion') ORDER BY seq"):
            p=json.loads(p)
            if p.get('evidence') and not assessment(p['evidence']): evidence[(s,p['version'])]=p['evidence']
        board=[]
        for row in rows:
            e=evidence.get((row['strategy'],row['version']))
            if row['state'] in ('CANDIDATE','CHAMPION') and e:
                board.append(dict(**row,protocol_hash=e['protocol_hash'],net_expectancy=e['net_expectancy'],drawdown=e['drawdown'],
                                  evidence_kind=e['kind'],result_hash=e['result_hash']))
        board.sort(key=lambda x:(-x['net_expectancy'],x['drawdown'],x['strategy'],x['version']))
        reviews=[json.loads(r[0]) for r in self.db.execute('SELECT review FROM research_trade_reviews')]
        groups=defaultdict(list)
        for row in board:groups[row['protocol_hash']].append(row)
        return dict(registry=rows,leaderboards_by_protocol=dict(groups),
            leaderboard=board if len(groups)<=1 else [],
            leaderboard_note='Only compare a common preregistered protocol; no pooled ranking across protocols',
            champion=next((r for r in rows if r['state']=='CHAMPION'),None),
            review_metrics={kind:trade_diagnostics([r for r in reviews if r['kind']==kind]) for kind in sorted(KINDS)},
            policy=POLICY,broker_execution_enabled=False,journal_chain=self.journal.verify())
    def cycle(self,at,sources,blockers):
        now=instant(at);local=now.astimezone(ZoneInfo('America/Chicago'))
        cycle_id='research-cycle:'+str(int(now.timestamp())//7200)
        payload=dict(sources=sources,blockers=blockers,observed_at=at)
        # Durable claim protects against overlapping schedulers and crash reruns.
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('INSERT INTO research_cycle_lock VALUES(1,?)',(cycle_id,))
            self.db.execute('INSERT INTO claims VALUES(?,?)',(cycle_id,digest(payload)))
            self.journal._append(cycle_id,'started',dict(plan_hash=digest(payload)))
        try:
            result=dict(observed_at=at,reporting_date=local.date().isoformat(),
                reporting_week='%04d-W%02d'%local.isocalendar()[:2],
                sources=sources,blockers=blockers,**self.snapshot(),
                market_experiments_executed=0,simulation_running=False,
                cycle_scope='source/admission/governance review; not a trading worker')
            self.journal.append(cycle_id,'research_cycle_completed',result)
            return result
        except Exception:
            self.journal.append(cycle_id,'research_cycle_failed',dict(reason='local_cycle_error',retry_requires_review=True))
            raise
        finally:
            # A process kill never reaches here: retained lock needs explicit reconciliation.
            with self.db:self.db.execute('DELETE FROM research_cycle_lock WHERE singleton=1 AND cycle=?',(cycle_id,))
    def report(self,kind,at):
        """Journal-backed once-per-period reports; export recovery reads committed payload."""
        if kind not in ('daily','weekly'): raise ValueError('unknown report cadence')
        local=instant(at).astimezone(ZoneInfo('America/Chicago'))
        day=local.date()
        if kind=='daily':start=end=day
        else:
            end=day-timedelta(days=day.weekday()+1);start=end-timedelta(days=6)
        report_id=f'research-report:{kind}:{start}:{end}'
        existing=self.db.execute("SELECT payload FROM records WHERE experiment=? AND kind='research_report_completed'",(report_id,)).fetchone()
        if existing:return json.loads(existing[0])
        self.journal.claim(report_id,digest(dict(kind=kind,start=str(start),end=str(end))))
        cycles=[]
        for (encoded,) in self.db.execute("SELECT payload FROM records WHERE kind='research_cycle_completed' ORDER BY seq"):
            c=json.loads(encoded)
            d=instant(c['observed_at']).astimezone(ZoneInfo('America/Chicago')).date()
            if start<=d<=end:cycles.append(c)
        result=dict(kind=kind,created_at=at,period_start=str(start),period_end=str(end),
            timezone='America/Chicago',observed_cycles=len(cycles),
            last_observed_snapshot=cycles[-1] if cycles else None,
            evidence_gap=not bool(cycles),
            note='No cycles means no evidence for this period, not zero trading activity. Older reports remain separate historical evidence.',
            broker_execution_enabled=False)
        self.journal.append(report_id,'research_report_completed',result)
        return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--journal',required=True)
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();data=json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
    target=Path(args.output)
    if target.exists(): raise ValueError('output already exists; reconcile instead of overwrite')
    workflow=Workflow(args.journal)
    try:
        for card in data.get('new_strategies',[]):workflow.register(card['strategy'],card['version'],card['spec'])
        result=workflow.cycle(data['observed_at'],data['sources'],data['blockers'])
        # The committed journal is authoritative if export is interrupted.
        with target.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    finally:workflow.close()

if __name__=='__main__':main()
