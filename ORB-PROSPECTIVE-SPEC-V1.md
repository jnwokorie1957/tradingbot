# Prospective MNQ opening-range hypothesis v1 — RESEARCH, not executed

Source lead: Zarattini, Barbon and Aziz, *A Profitable Day Trading Strategy for
the U.S. Equity Market*, DOI 10.2139/ssrn.4729284; author abstract read October 31:
https://www.abarbon.com/papers/a-profitable-day-trading-strategy-for-the-u-s-equity-market
The paper studies equity opening-range breakouts and unusual activity. It does
not validate this MNQ adaptation or a >60% win rate. Only the abstract was reviewed;
no source performance is imported as our result. This is a proposed deterministic
variant, not a reproduction or approved experiment claim.

Freeze before any dataset admission: MNQ only, one contract maximum, 15-minute
opening range from 09:30:00 inclusive to 09:45:00 exclusive America/New_York on
full US equity sessions; holidays and shortened sessions excluded by dated official
calendar. Require all fifteen completed one-minute TRADES bars. No forward-fill.
High/low define the range. Between 09:45 and 11:00 exclusive, first completed
one-minute close strictly outside the range generates a directional signal.
No volume filter, no parameter search, no second signal after a skip or trade.

Entry is the first valid executable quote event strictly after signal close and
within five seconds, at ask for long/bid for short, with reviewed adverse slippage
and sufficient displayed size. Reject frozen/delayed/crossed/untimestamped quotes,
stale input, unavailable margin/cost, existing opposite exposure or duplicate setup.
Stop at the opposite opening-range boundary; never tighten it to meet risk.
One-contract all-in risk uses the new profile only after independent activation
review. If stop plus fees/spread/slippage exceeds its cap or portfolio budget, skip.
Target is two times entry-to-stop price distance, not a promise of 2R net of costs.
Exit on first subsequent executable quote reaching stop or target, adverse gaps
filled at available quote, or first valid quote at/after 15:55 New York time.
Missing exit quotes freeze qualification and record unresolved exposure, not an
invented fill. Entry/exit fees and any applicable holding costs reduce net return.

Prospective allocation: after a separately reviewed start timestamp and contract
roll/calendar manifest, first 60 eligible sessions are development for engineering
verification only; next 60 are validation; next three consecutive 60-session blocks
are fixed-rule walk-forward evaluations; final 60 sessions are sealed holdout.
No existing consumed or accidentally exposed windows qualify. Do not start counting
until allocation/manifest hashes and experiment identity are approved and recorded.
No rules may change within this version; any revision gets a new identity and new
non-overlapping evaluation. Test phases may have fewer than 300 eligible trades;
do not extend or cherry-pick windows to reach a target after seeing outcomes.

Report every session, signal, skip, loss, missing-data case and cost assumption;
net expectancy with session-block uncertainty, drawdown, profit factor, win rate,
loss streaks and weekly/monthly consistency. Sharpe only from a complete dated
equity-return series with declared annualization. Report robustness under doubled
cost/slippage as sensitivity, never alternative winning parameter selection.
Existing independent-review, unseen-OOS and actual-forward gates remain binding.
No champion, leaderboard admission, schedule, data acquisition or test run is
created by publishing this specification. All execution remains local paper-only.
