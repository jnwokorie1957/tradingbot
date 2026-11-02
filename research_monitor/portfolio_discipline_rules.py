"""Entry admission based only on completed loss history and pre-entry features."""
from copy import deepcopy

CONFIGS={
    'control':{},
    'nas15_eff_after1':{'NAS15':{'efficiency_after_losses':1}},
    'nas15_eff_after2':{'NAS15':{'efficiency_after_losses':2}},
    'nas15_cooldown30':{'NAS15':{'loss_cooldown_seconds':1800}},
    'nas15_daily2':{'NAS15':{'daily_loss_limit':2}},
    'nas15_daily1':{'NAS15':{'daily_loss_limit':1}},
    'portfolio2loss_cooldown30':{name:{'portfolio_two_loss_pause_seconds':1800} for name in ['SPX15','NAS15','NAS5']},
}


def apply(lanes,name):
    if name not in CONFIGS:raise ValueError('Unregistered discipline hypothesis')
    out=deepcopy(lanes)
    for lane,changes in CONFIGS[name].items():out[lane].update(changes)
    return out


def reject_state(lane,signal,guard,now,portfolio_history):
    threshold=lane.get('efficiency_after_losses')
    if threshold is not None and guard.loss_streak>=threshold and signal.get('features',{}).get('directional_efficiency',-1)<.30:return 'recovery_efficiency_below_030'
    cooldown=lane.get('loss_cooldown_seconds')
    if cooldown and guard.last_loss is not None and now<guard.last_loss+cooldown:return 'loss_cluster_cooldown'
    limit=lane.get('daily_loss_limit')
    if limit is not None and guard.daily_losses>=limit:return 'daily_loss_entry_halt'
    pause=lane.get('portfolio_two_loss_pause_seconds')
    if pause and len(portfolio_history)>=2 and all(pnl<0 for _,pnl in portfolio_history[-2:]) and now<portfolio_history[-1][0]+pause:return 'portfolio_loss_cluster_pause'
    return None
