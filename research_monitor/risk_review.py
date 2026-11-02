"""Fixed drawdown hypotheses. No sizing increase or changes to structural stops."""
POLICIES=('baseline','cap15','equity2pct','one_entry','stop_after_loss','cooldown_loss30','trend_entry','strong_close')
ADAPTIVE=('baseline','cap20','loss_step20','streak_step15','drawdown_step20','drawdown_step15','two_daily_losses','cost_gate')
TIGHT=('streak_step15','streak_step10','streak_staircase','streak_slow_restore','streak_dd10','streak_pause90','streak_cost08','streak_strength')
RECOVERY=('streak_step10','recovery_slow10','recovery_guard20','recovery_daily2','recovery_trend')

class RiskReview:
 def __init__(self,name):
  if name not in POLICIES+ADAPTIVE+TIGHT+RECOVERY:raise ValueError('Unknown drawdown policy')
  self.name=name;self.session=None;self.entries=0;self.loss_halt=False;self.last_loss=None
  self.loss_streak=0;self.daily_losses=0;self.peak_equity=500.;self.throttled=False
  self.recovery_lock=False;self.recovery_wins=0
 def session_start(self,date):
  if date!=self.session:self.session=date;self.entries=0;self.loss_halt=False;self.daily_losses=0
 def observe_equity(self,equity):
  self.peak_equity=max(self.peak_equity,equity)
  drawdown=1-equity/self.peak_equity
  threshold=.10 if self.name in ('drawdown_step20','streak_dd10','recovery_guard20') else .15
  if drawdown>=threshold:self.throttled=True
  elif drawdown<=.05:self.throttled=False
 def cap(self,cash):
  if self.name=='recovery_slow10' and self.recovery_lock:return 10.
  if self.name in RECOVERY and self.loss_streak>=2:return 10.
  if self.name=='recovery_guard20' and self.throttled:return 20.
  if self.name=='streak_slow_restore' and self.recovery_lock:return 15.
  if self.name=='streak_dd10' and self.throttled:return 10.
  if self.name=='streak_staircase' and self.loss_streak>=3:return 10.
  if self.name=='streak_step10' and self.loss_streak>=2:return 10.
  if self.name in TIGHT and self.loss_streak>=2:return 15.
  if self.name=='cap20':return 20.
  if self.name=='loss_step20' and self.loss_streak>=1:return 20.
  if self.name=='streak_step15' and self.loss_streak>=2:return 15.
  if self.name=='drawdown_step20' and self.throttled:return 20.
  if self.name=='drawdown_step15' and self.throttled:return 15.
  return min(25.,15. if self.name=='cap15' else max(cash,0)*.02 if self.name=='equity2pct' else 25.)
 def reason(self,now):
  if self.name=='one_entry' and self.entries>=1:return 'one_entry_session_limit'
  if self.name=='stop_after_loss' and self.loss_halt:return 'loss_session_halt'
  if self.name=='two_daily_losses' and self.daily_losses>=2:return 'two_daily_losses'
  if self.name=='recovery_daily2' and self.daily_losses>=2:return 'two_daily_losses'
  if self.name=='streak_pause90' and self.loss_streak>=2 and self.last_loss is not None and now<self.last_loss+5400:return 'streak_pause90'
  if self.name=='cooldown_loss30' and self.last_loss is not None and now<self.last_loss+1800:return 'loss_cooldown'
  return None
 def entered(self):self.entries+=1
 def entry_reason(self,signal,spread,slip,distance):
  if self.loss_streak>=2:
   if self.name=='recovery_trend' and not signal.get('trend_aligned'):return 'recovery_trend_not_aligned'
   if self.name=='streak_cost08' and (spread+2*slip)/distance>.08:return 'recovery_cost_above_eight_percent_R'
   if self.name=='streak_strength' and not signal.get('strong_close'):return 'recovery_weak_close'
  return None
 def exited(self,pnl,at):
  if pnl<0:
   self.loss_halt=True;self.last_loss=at;self.loss_streak+=1;self.daily_losses+=1;self.recovery_wins=0
   if self.loss_streak>=2:self.recovery_lock=True
  elif pnl>0:
   self.loss_streak=0;self.recovery_wins+=1
   if self.recovery_wins>=2:self.recovery_lock=False
