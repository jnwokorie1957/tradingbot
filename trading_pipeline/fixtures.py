"""Explicit synthetic software fixture generator; never market performance data."""
import json,hashlib
from pathlib import Path
from .runner import code_identity

def create(folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 contracts={'TEST':dict(root='TEST',contract_id=1,contract_month='202602',last_trading_date='20260220',exchange='SYNTHETIC',currency='USD',multiplier=1,tick=.25,initial_margin=100,maintenance_margin=80,fee_per_side=.1,daily_carry_fee=0,spec_verified=True,permission_verified=True,costs_verified=True,data_verified=True,evidence_source='SYNTHETIC SOFTWARE TEST',valid_from='2026-01-01T00:00:00Z',valid_until='2026-02-01T00:00:00Z',exit_before='2026-01-30T00:00:00Z',requires_adjustment=False)}
 def rows(day):
  prefix=f'2026-01-{day:02d}T00:';events=[]
  for i,price in enumerate([100,100,101]):
   events.append(dict(id=f'd{day}-bar{i}',kind='bar',contract='TEST',start=prefix+f'0{i}:00Z',end=prefix+f'0{i+1}:00Z',available_at=prefix+f'0{i+1}:00Z',open=price,high=price,low=price if i<2 else 100.5,close=price,volume=10))
  for second,bid in [(1,101),(2,105)]:
   at=prefix+f'03:0{second}Z';events.append(dict(id=f'd{day}-quote{second}',kind='quote',contract='TEST',available_at=at,quote_at=at,bid=bid,ask=bid+.25,bid_size=1,ask_size=1,quality='verified'))
  return events
 files={}
 for name,days,start,end in [('train',[1],'2026-01-01T00:00:00Z','2026-01-01T01:00:00Z'),('validation',[2,3],'2026-01-02T00:00:00Z','2026-01-04T00:00:00Z')]:
  data=''.join(json.dumps(r)+'\n' for day in days for r in rows(day));p=folder/(name+'.jsonl');p.write_text(data,encoding='utf-8')
  files[name]=dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),start=start,end=end)
 manifest=dict(dataset_id='SYNTHETIC-TEST-ONLY',synthetic=True,partition='development',source_kind='synthetic',verified=True,review_reference='SYNTHETIC TEST',timestamp_semantics_verified=True,quote_path_verified=True,effective_costs_verified=True,source_reference='fixtures.py generated software-only data',prior_exposure='synthetic',bar_seconds=60,files=files,final_holdout=dict(start='2026-01-04T01:00:00Z',access='locked',commitment_sha256='0'*64,path='NEVER_OPEN_THIS_HOLDOUT'))
 plan=dict(risk={'budget':500,'trade_risk':.005,'portfolio_risk':.01,'daily_pause':.02,'drawdown_pause':.10},hypotheses=[dict(family='breakout',version='1.0.0',lookback=2,reward_risk=2.)],scenarios=[dict(id='baseline',fee_factor=1,slippage_ticks=1),dict(id='stress',fee_factor=1.5,slippage_ticks=2)],validation_windows=[dict(start=f'2026-01-0{i}T00:00:00Z',end=f'2026-01-0{i}T01:00:00Z') for i in [2,3]])
 for name,value in [('manifest.json',manifest),('contracts.json',contracts),('plan.json',plan)]:
  (folder/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
 return plan,manifest,contracts
