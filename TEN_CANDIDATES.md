# Tradingbot: ten deterministic research candidates

Research cut: 15 October 2026. Simulation only. No strategy has been implemented or backtested by this research pass. No downloaded code was executed. This is an implementation specification, not investment advice or a performance ranking.

## Scope and evidence labels

- These belong to the broader Tradingbot research track. Keep Atlas ICT rules and evaluation separate.
- Every card is either a **source-derived adaptation** or a **new indicator-based hypothesis**. Changed instruments, execution, sizing, stops, or horizons prevent a claim of source reproduction.
- The prior 72 breakout/pullback trials (992 occurrences) and 18 mean-reversion trials (1,425 occurrences) produced zero eligible trades under the $2.50 cap. They did not establish fills, P&L, ROI, or win rate. Their inspected data is development data, not a fresh holdout.
- “First ten” is a preregistration order, not a top-ten ranking. No 60% winning-trade claim is verified.

## Shared execution and risk contract

1. Each candidate is initially an isolated $500 account simulation. Keep the $2.50 per-trade planned-loss ceiling and all existing stricter account safeguards. Do not add ten independent exposures to a purported single $500 portfolio. Combining candidates needs a separate concurrent-risk allocation rule.
2. At a signal, calculate its natural stop first. Choose the largest legal position increment whose planned stop loss, actual round-trip fee function, spread, and declared adverse-slippage reserve fit $2.50 and available margin. Reject zero size. Unknown costs, minimum size, margin, or executable prices mean **feasibility unverified**, not a pass. Never shrink a natural stop or invent fractional futures to force eligibility.
3. Signals use completed bars only: a bar [t−Δ,t) is available at t. Market entries occur at the first fresh executable quote after the decision time and declared processing latency. Scheduled entries expire after 60 seconds if no fresh quote; breakout orders follow the card's cancellation time. Use ask to buy and bid to sell. Do not add the spread twice when quote-based fill prices already contain it.
4. Stops are stop-market exits using the executable exit-side quote; gaps fill at the first available adverse price plus declared slippage. Targets trigger market exits on the executable exit side. A stop and a planned-risk cap do not guarantee a maximum realized loss.
5. Round futures stop distances upward and stop prices away from entry to valid ticks. Round profit targets toward entry. Reject zero-distance/invalid stops or entries already through a frozen target. No averaging down, pyramiding, or same-bar re-entry. Quote/tick sequencing resolves stop/target ambiguity; OHLC-only results are diagnostic and use adverse ordering rather than favorable invented paths.
6. Use IANA zones America/New_York and Europe/London independently, exchange/fixing calendars, and point-in-time instrument specifications. Skip shortened futures sessions. Preserve gaps and bad-data rejections; do not forward-fill across missing trading intervals.
7. Futures signals use that specific contract's trade bars and volume. Select a roll using information available before the session, such as prior-session volume, and preserve real contract execution prices. NQ signals with MNQ fills are a separate declared cross-instrument experiment, not the baseline.
8. For intraday indicators below, calculate across chronological bars, not just the entry window, except session-anchored VWAP. True range TR=max(H−L, abs(H−previous C), abs(L−previous C)). “ATR-SMA(n)” means the arithmetic mean of the last n completed TRs. “ATR-Wilder(14)” seeds with 14 TRs, then uses (13×prior ATR+new TR)/14.
9. For cards 5–7 only: futures entries 10:00–15:00 New York, flatten 15:55; FX entries 08:00–16:00 London, flatten 16:55. Reject entry signals whose next executable quote is outside the window. A holding-bar count starts with the first full bar after entry; execute time exits after the stated number completes.

### Instrument feasibility before strategy testing

NQ is $5 per minimum tick; ES is $12.50. Neither can support even a one-tick stopped position under $2.50 before costs. MNQ is $0.50 per tick and MES $1.25, leaving at most five and two ticks respectively before costs. Treat NQ/ES as possible signal/reference data, not risk-eligible execution contracts. Sources: [CME E-mini pricing](https://www.cmegroup.com/education/courses/introduction-to-equity-index-products/discover-equity-index-notional-value-and-price), [CME NQ specifications](https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.contractSpecs.html), [CME micro specifications](https://www.cmegroup.com/articles/faqs/micro-e-mini-equity-index-futures-frequently-asked-questions.html).

FX requires the chosen venue's actual base-unit minimum/increment, commission minimums, margin rules, spreads and financing. A convenient fractional-lot assumption is insufficient.

## 1. Directional five-minute opening-range breakout

**Status:** Source-derived futures adaptation. **Markets:** MNQ and MES separately; NQ/ES reference-only under this cap.

**Rules:** At 09:35 New York freeze OHLC of [09:30,09:35). If C>O, arm one buy-stop at H+one tick; if C<O, one sell-stop at L−one tick; doji means no trade. Use the first qualifying executable crossing after arming, with gap/slippage handling. Cancel pending entry at 15:55. One fill per day. Initial fixed stop distance is ceil-to-tick(0.10×ATR-SMA(14) from the previous fourteen complete regular sessions). No target; exit at 16:00 or stop.

**Data:** Five-minute opening range, prior fourteen regular-session daily OHLCs, intraday quotes; sufficient contract history across rolls.

**Hypothesis/failure:** Initial directional imbalance persists. Fails on opening reversals, quiet chop and cost-dominated tiny budgets. Never include today's daily range in ATR. Tick buffer, cutoff, futures transfer and account sizing are our additions; the paper's stock selection is absent.

**Source:** [Zarattini, Barbon and Aziz, SSRN 4729284](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284), [university-hosted full paper, sections 2–4](https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content). Research used over 7,000 stocks in 2016–2023, not a $500 futures account. Stock-portfolio findings are not evidence for this adaptation.

## 2. Closing-half-hour continuation

**Status:** Source-derived stop-controlled adaptation. **Markets:** MNQ and MES separately.

**Rules:** At 15:30 New York, r=last trade price available at 15:30 / previous regular-session 16:00 close−1. Long if r>0, short if r<0, zero skip. Enter after the decision. Fixed stop distance=ATR-SMA(20) of the last twenty completed five-minute bars, rounded upward to a tick. Exit 16:00 or stop; no target or re-entry.

**Data:** Prior regular-session close, at least twenty five-minute bars, synchronized quotes/trades. No dealer-gamma feed is required in this seed.

**Hypothesis/failure:** Late hedging/rebalancing continues the day's move. Closing reversals and positive-gamma environments can defeat it. Do not use later futures settlement as the 16:00 cash close; do not fill at a price used to finish the signal.

**Source:** [Baltussen, Da, Lammers and Martens, JFE 2021, sections 2 and 3.4](https://academicweb.nd.edu/~zda/intramom.pdf). Their cross-asset futures evidence spans 1974–2020. The added ATR stop and this small-account execution are not the paper's strategy; no source portfolio Sharpe is inherited.

## 3. Noise-band momentum with VWAP protection

**Status:** Source-derived adaptation. **Markets:** MNQ/MES separately; futures traded volume only.

**Rules:** At each 10:00,10:30,…,15:30 New York, m(t)=mean(abs(P_d(t)/O_d−1)) over fourteen prior valid regular sessions. U=max(today 09:30 open, previous 16:00 close)×(1+m); L=min(open,previous close)×(1−m). Compute current regular-session VWAP from one-minute typical-price×actual-volume bars, anchored at 09:30. While flat, long if P>max(U,VWAP); short if P<min(L,VWAP). Enter next quote. Initial stop is max(U,VWAP) for long or min(L,VWAP) for short, rounded away from entry. At later checkpoints ratchet the stop only favorably; if already breached, exit immediately. Protective stops remain active intrabar. No target; flatten 16:00. After exit, wait until a later checkpoint before another entry; no instantaneous reversal.

**Data/traps:** At least fourteen aligned intraday sessions, one-minute OHLCV and quotes. Do not include the current day in historical bands, use full-day VWAP early, or relabel spot tick volume as traded volume.

**Hypothesis/failure:** Abnormal movement beyond historical same-clock noise persists; whipsaws, jumps and stale volatility estimates are failure modes. Intrabar protection, monotonic ratcheting, bar-VWAP convention and futures transfer are explicit deviations from the published semi-hourly strategy.

**Source:** [Zarattini, Aziz and Barbon, Beat the Market, September 2025 revision](https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf). SPY research uses 2007–early-2024 data and stock commission assumptions, not micro-futures costs.

## 4. Twelve-month price-trend benchmark

**Status:** Deliberately slow, source-inspired benchmark; not intraday momentum or an exact TSMOM reproduction. **Markets:** EURUSD and GBPUSD separately.

**Rules:** Build daily midpoint OHLC on 17:00-to-17:00 New York sessions. After the final trading day's 17:00 close of month m, S=log(C_m/C_(m−12)), requiring thirteen month-end prices. At 08:00 London on the next available weekday, long for S>0, short for S<0, zero skip. Fixed stop distance=2×ATR-SMA(20) of completed daily midpoint bars, measured from the entry midpoint. Long stop uses bid crossing below; short uses ask crossing above. Hold until stop or the next month's scheduled 08:00 rebalance. No target and no re-entry after a stop within that month. A same-direction monthly renewal still closes/reopens and pays both sets of costs in this deliberately simple implementation.

**Data/traps:** Thirteen month-end prices, twenty daily ranges, intraday bid/ask history and actual financing/rollover charges. No lookahead to the month-end close before it is published. Broker financing and weekend gaps matter; without a credible holding-cost reserve, feasibility remains unverified.

**Hypothesis/failure:** Slow information diffusion produces persistent trends; sideways markets, sharp reversals and financing can dominate. Spot price returns, the stop, execution time, fixed-risk sizing and two-pair universe differ from original excess-return, volatility-scaled multi-asset portfolios.

**Source:** [Moskowitz, Ooi and Pedersen, AQR research](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum), [original factor-data description](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data). Original benchmark uses twelve-month signals/one-month holdings across 58 instruments, 1985–2009; factor returns cannot substitute for executable pair-level data.

## 5. Session VWAP excursion and reclaim

**Status:** New indicator-based hypothesis. **Markets:** MNQ/MES separately; no spot-FX version in this seed.

**Rules:** Five-minute bars; reset at 09:30 New York. For session bars p=(H+L+C)/3, W=sum(volume), μ=sum(volume×p)/W, σ=sqrt(sum(volume×(p−μ)^2)/W). Require six completed session bars and W,σ>0. Long when previous close was below its then-current μ−2σ and current μ−2σ≤C<μ. Short symmetrically when previous close was above μ+2σ and current μ<C≤μ+2σ. Enter next quote. Long stop=min(previous low,current low)−one tick; short stop=max(highs)+one tick. Freeze target at current μ. Exit stop, target, twelve full holding bars or 15:55, earliest wins.

**Data/traps:** Specific-contract OHLCV plus quotes. This σ is volume-weighted population dispersion of bar typical prices, an explicit approximation, not true trade-level dispersion. Never revise the frozen target or historical VWAP with future data.

**Hypothesis/failure:** A failed extreme excursion returns toward the session mean. Persistent trend/news days and stale means are the main failures.

**Source:** [TradingView official VWAP definition](https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/). It establishes the indicator, not this entry/stop/target strategy or profitability. The two-SD reclaim rules and all parameters are ours.

## 6. Volatility compression-to-expansion breakout

**Status:** Author-inspired simplified hypothesis; not a reproduction of Bollinger Method IV. **Markets:** MNQ/MES/EURUSD/GBPUSD, separately.

**Rules:** Fifteen-minute bars. M=SMA20(close), s=population SD of those closes, U=M+2s, L=M−2s, B=(U−L)/M. After 125 valid B values, while flat/unarmed in the entry window, arm when B≤minimum(previous 124 B). The arm expires after eight subsequent bars and cannot refresh. Enter long after two consecutive post-arm closes above their respective U, short after two below L; consume the arm on that signal. Second close must occur by arm+8. Fixed stop distance=ATR-Wilder(14) through signal bar; target=2×that distance from actual entry. Exit stop, target, sixteen full holding bars or session flatten. No immediate re-arm until the next bar after exit.

**Data/traps:** At least 144 fifteen-minute bars to form the bandwidth history, more for stable Wilder initialization, plus quotes. No future-defined squeeze percentile or subsequent volatility information. Freeze entry ATR. False expansion and news-spread widening are natural failure modes.

**Source:** [John Bollinger author documentation, pp.2–3](https://www.bollingerbands.com/_files/ugd/58be43_d09c50b6e8ea4afd9af0523ef94de876.pdf), [author's rules](https://www.bollingerbands.com/bollinger-band-rules). His described Method IV includes ADX; omitting it, intraday rescaling, arm lifetime, ATR stop and target are our choices. No source profitability is claimed.

## 7. RSI-2 pullback reversal

**Status:** Connors-inspired intraday hypothesis, including a new symmetric short side. **Markets:** MNQ/MES/EURUSD/GBPUSD separately.

**Rules:** Five-minute bars; require 200 completed closes. RSI2 uses Wilder average gains/losses with coefficient 1/2, seeded by the first two changes. RSI=100−100/(1+gain/loss); define loss=0,gain>0 as 100; gain=0,loss>0 as 0; both zero as 50. Long if C>SMA200, RSI_(t−2)<65, and RSI_(t−2)>RSI_(t−1)>RSI_t. Short if C<SMA200, RSI_(t−2)>35, and RSI_(t−2)<RSI_(t−1)<RSI_t. Enter after signal. Fixed stop distance=ATR-Wilder(14). Long exit after a completed RSI>75, short after RSI<25; execute next quote. Also exit on stop, twelve full holding bars or session flatten. No profit target.

**Data/traps:** Five-minute bars with explicit initialization and quote execution. Same-close signal and fill is disallowed. Daily-to-five-minute rescaling and shorts are unvalidated. Persistent selloffs/rallies, trend breaks and costs can overwhelm reversion.

**Source:** [Larry Connors's R2 article](https://tradingmarkets.com/recent/the_improved_r2_strategy_84_correct_with_just_6_rules_-674361), [official RSI formula](https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/). The author example is daily and long-only; headline historical correctness is not evidence for this implementation.

## Common additions for FX flow cards 8–10

Use fifteen-minute midpoint bars and bid/ask ticks. At entry, D=max(0.0010, 2×ATR-SMA(20) of fully completed fifteen-minute bars). Thus the floor is ten pips for USD-quoted EUR/GBP. Stop from entry midpoint m: long bid≤m−D; short ask≥m+D. No trailing/target/re-entry. A declared conservative baseline reserves D+current full spread+two pips per base unit plus actual round-trip commissions, representing one pip adverse slippage on each side. This is an assumed stress allowance, not empirical protection. Round size down to verified unit increments. Existing risk/margin safeguards still apply. A more pessimistic stress case must be reported; costs cannot be tuned to create a pass.

## 8. London post-fix USD reversal

**Status:** Source-derived hypothesis with important published negative cost evidence. **Markets:** EURUSD/GBPUSD separately.

**Rules:** On weekdays with a normal scheduled 16:00 London WMR fixing, buy at 16:05 Europe/London. Exit 16:00 America/New_York or the common stop. No condition on the pre-fix price direction. The delay and exit time are deliberate choices.

**Data/traps:** Fixing calendar, independent timezone conversion and executable quotes. Do not fill at a published fixing rate: it is a benchmark, not an executable point quote. Do not silently turn the rule into “fade whichever direction occurred.”

**Hypothesis/failure:** USD demand concentrated around the fix later unwinds. Persistent dollar demand, news, changing flow and transaction costs can erase it.

**Source:** [Krohn, Mueller and Whelan, final Journal of Finance 2024 paper, V.E/Table X](https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13306); [LSEG fixing description](https://www.lseg.com/en/ftse-russell/benchmarks/wmr-fx-benchmarks). Crucially, the final paper's tested liquidity-taking AUD/GBP reversal strategies become negative after costs. Dealer liquidity provision is a different activity. No net retail edge is established.

## 9. European morning local-currency selling

**Status:** Source-derived session adaptation. **Markets:** EURUSD primary; GBPUSD separately identified transfer/negative control.

**Rules:** Monday–Friday, short at 07:00 Europe/London; exit 08:00 America/New_York or common stop. One trade, no afternoon reverse trade, no hindsight news-day deletions. Respect the actual elapsed interval as US/UK daylight-saving dates differ.

**Data/traps:** Fifteen-minute midpoint bars and bid/ask quotes. Never hardcode this as a fixed UTC interval. Midquote direction frequency is not a net winning-trade rate. Report holiday/news strata without selecting only favorable days.

**Hypothesis/failure:** Local investors' foreign-asset purchases create local-currency selling pressure. Opposing macro trends, policy surprises, changed session flows and spread costs can dominate.

**Source:** [Breedon and Ranaldo, SNB Working Paper 2011-04](https://www.snb.ch/public/publication/fr/www-snb-ch/publications/research/working-papers/2011/working_paper_2011_04/publications0_fr/working_paper_2011_04.n.pdf). Its 1997–2007 cost results favor EURUSD relative to other examples; GBPUSD morning/afternoon variants lose after quoted spreads. EBS represented under 5% of GBPUSD turnover in that sample. This is old interdealer evidence, not current broker validation.

## 10. Month-end equity-hedging flow

**Status:** Source-inspired cross-asset calendar hypothesis. **Markets:** EURUSD/GBPUSD separately.

**Rules:** Trade only the last scheduled London WMR fixing business day of each month, if its fix is at normal 16:00. Fix equity proxies as S&P 500 USD price index, EURO STOXX 50 EUR price index, FTSE 100 GBP price index. Compute each index's log return from its final official close before month start to its latest official close published before 00:00 London on fixing day. S=US return−relevant EUR/UK return. Buy pair if S≥0.02; sell if S≤−0.02; otherwise skip. Enter 15:00 London; exit 16:00 or common stop. Missing index observations invalidate the month.

**Data/traps:** Point-in-time index closes and fixing calendar, plus common FX data. No same-day equity close; no substitutions between price/total-return or local-currency/USD indices. Threshold, proxy set and two-country difference are our frozen choices. At most twelve opportunities per pair annually before filtering, so a short sample is inconclusive.

**Hypothesis/failure:** Outperforming-country equity exposure prompts currency hedge sales. Different hedge ratios/timing, bond flows and anticipatory crowding can defeat this proxy.

**Source:** [Melvin and Prins, ECB-hosted author paper](https://www.ecb.europa.eu/events/pdf/conferences/131216/Third_FX_Workshop_MELVIN_PRINS_Equity%20hedging%20and%20exchange%20rates%20Nov%202013.pdf?37cad5300a1a2b823aec4ad71d721cec=), subsequently Journal of Financial Markets 2015. Public sample: April 2004–December 2012; pooled explanatory R² only 0.03. [Ben Zeev and Nathan 2023](https://www.bgu.ac.il/media/qsgjpsib/2315.pdf) finds Israeli institutional hedging throughout the month, limiting universal month-end assumptions. Neither validates this retail implementation.

## Bounded evaluation plan

### Gate A: deterministic implementation

Freeze these exact rules, market assignments, source versions, cost assumptions and code/data hashes before results. Unit-test DST transitions, missing bars, warmup, roll changes, no future data, stop rounding, quote-side fills, fee minima, zero sizing and simultaneous stop/target cases. Indicator initialization, changing cutoffs or adding a filter is a new trial, not an invisible repair to bad performance.

### Gate B: market/account feasibility

For each candidate/instrument record raw signals, data-quality rejects, unavailable quotes, minimum-unit rejects, cost/risk rejects and margin rejects separately. If no opportunity survives, stop that configuration as **risk/cost infeasible**, with the distribution of required minimum risk. Do not compute a win rate or account return from nonexistent fills. Do not endlessly tune the already-inspected July/August data.

### Gate C: independent evidence

Use chronological untouched evaluation blocks with an embargo covering each candidate's maximum holding interval, then one sealed final block. Previously inspected periods are development only. Indicators may warm up on older data but decisions remain causal. Freeze the split before viewing results. Include all candidate×instrument tests in the multiple-testing ledger; the ten families imply more than ten tests if evaluated on several instruments.

Report net expectancy in dollars and R, trade count, eligible-signal fraction, turnover, average win/loss, profit factor, drawdown, time underwater, costs and financing, with day/week-block bootstrap uncertainty appropriate to dependence. Monthly strategies require substantially longer history; if the evidence is too sparse, label it insufficient rather than giving a leaderboard. Report baseline and worse-cost cases. Gross signal efficacy is a separate diagnostic, never substitute account P&L. Compare simple always-long/time-matched controls where relevant; do not select a post-hoc best subset of sessions.

### Gate D: publication decision

Only independent cost-inclusive results can support any ranking. Retain rejected, flat and inconclusive candidates in the ledger. Passing an offline test is not permission for broker-paper or live execution. No account connection, subscription, order or live money is part of this research assignment.

## Additional feasibility evidence, outside the ten seeds

- **Smaller index denominations:** [CME's current E-nano FAQ](https://www.cmegroup.com/articles/faqs/faq-e-nano-equity-index-futures.html) lists NNQ at $0.20/point with $0.10 tick and NES at $0.50/point with $0.25 tick. NES already appeared in the project's earlier finite data observation; that was bar ingestion, not quotes/fills or validated tradability. Investigate contract-specific current quote coverage, fees, margins, spread/liquidity and broker support separately. Do not relabel MNQ fills as NNQ or shrink historical contracts synthetically. Smaller size does not prove an edge.
- **Negative cost comparator:** [New York Fed Overnight Drift, August 2022 revision](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf), using 1998–2020 ES data, reports 02:00–03:00 Sharpe 1.1 before costs but −0.5 after bid–ask spreads; its wider interval differs. This was not added as an eleventh candidate. It illustrates why statistically significant intraday drift is not automatically executable profitability.
- **Spot volume:** [OANDA's candle schema](https://developer.oanda.com/rest-live-v20/instrument-df/) defines volume as price-update count. Such a field cannot silently stand in for futures traded volume in cards 3 or 5.

## Completion status

Public primary papers and official/author documentation reviewed; ten rules specified. No source algorithm was executed, no account was connected, no backtest was run, and no performance or risk-eligibility result is claimed for these candidates. Remaining work is implementation, actual data/cost validation and independent evaluation.
