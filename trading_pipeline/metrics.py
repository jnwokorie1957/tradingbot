"""Descriptive diagnostics with dependence-aware daily block resampling."""
import math,random,statistics
from collections import defaultdict

def wilson(wins,n,z=1.959963984540054):
 if not n:return None
 p=wins/n;den=1+z*z/n;center=(p+z*z/(2*n))/den
 half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return [max(0,center-half),min(1,center+half)]

def summarize(trades,equity_path,synthetic=False):
 pnl=[x['net_pnl'] for x in trades];n=len(pnl);wins=sum(x>0 for x in pnl)
 gain=sum(x for x in pnl if x>0);loss=-sum(x for x in pnl if x<0)
 peak=500.;dd=0.
 for equity in equity_path:peak=max(peak,equity);dd=max(dd,(peak-equity)/peak)
 days=defaultdict(list)
 for t in trades:days[t['exit_at'][:10]].append(t['net_pnl'])
 expectancy_ci=None
 if len(days)>=5:
  groups=list(days.values());rng=random.Random(1729);samples=[]
  for _ in range(2000):
   drawn=[groups[rng.randrange(len(groups))] for _ in groups]
   samples.append(sum(map(sum,drawn))/sum(map(len,drawn)))
  samples.sort();expectancy_ci=[samples[49],samples[1949]]
 return dict(closed_trades=n,nonoverlapping_trades=n,independence_proven=False,trade_days=len(days),wins=wins,win_rate=wins/n if n else None,win_rate_wilson_95=wilson(wins,n),win_ci_assumption='Binomial reference only; clustered trades are not independent',net_pnl=sum(pnl),expectancy=statistics.mean(pnl) if n else None,expectancy_day_block_bootstrap_95=expectancy_ci,bootstrap_seed=1729,bootstrap_samples=2000,profit_factor=gain/loss if loss else None,no_losing_trades=bool(n and not loss),maximum_drawdown_fraction=dd,ending_equity=equity_path[-1] if equity_path else 500.,synthetic=synthetic)

def assess(metrics,*,synthetic,clean,independent_review=False):
 reasons=[]
 if synthetic:reasons.append('synthetic_software_test')
 if not clean:reasons.append('incomplete_or_invalid_trial')
 if metrics['closed_trades']<200:reasons.append('fewer_than_200_nonoverlapping_trades')
 if metrics['trade_days']<30:reasons.append('fewer_than_30_trade_days')
 if metrics['win_rate'] is None or metrics['win_rate']<.6:reasons.append('win_rate_below_target_or_unavailable')
 if metrics['expectancy'] is None or metrics['expectancy']<=0:reasons.append('nonpositive_or_missing_expectancy')
 if metrics['profit_factor'] is None or metrics['profit_factor']<1.3:reasons.append('profit_factor_below_target_or_unavailable')
 ci=metrics['expectancy_day_block_bootstrap_95']
 if ci is None or ci[0]<=0:reasons.append('expectancy_uncertain')
 if metrics['maximum_drawdown_fraction']>=.10:reasons.append('drawdown_limit_reached')
 if not independent_review:reasons.append('independent_review_required')
 return dict(statistical_screen_pass=not [r for r in reasons if r!='independent_review_required'],qualified_for_paper=False,broker_execution_enabled=False,reasons=reasons,notes='Passing thresholds is not proof of edge, independence, robustness or permission to activate.')
