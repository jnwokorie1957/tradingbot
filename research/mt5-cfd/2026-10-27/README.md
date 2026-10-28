# NAS100 / SPX500 research results — October27,2026

These are exploratory **broker-CFD bar-model diagnostics**, not actual trades or independently validated account returns. No strategy was qualified or promoted, and no live or paper-broker settings were changed. Source strategy specification and signal kernel: [`215ba44`](https://github.com/jnwokorie1957/tradingbot/tree/215ba44ba0a9119aaece4ff5823e0747b50f525f).

## Data and original screen

The private MT5 sample contains 76,761 completed native M1/M5/M15 bars for NAS100 and SPX500 over 30 calendar days, approximately September28–October28 in reported broker time (22 evaluated New York sessions). The clock was about 3 hours ahead of UTC at capture. Historical clock mapping was not verified, so UTC+3 is a primary assumption and UTC+2 a sensitivity case. Earlier M5/M15 data was used only to warm indicators. These are CFDs, not CME futures.

The initial screen covered 120 related configurations:20 strategy/instrument/timeframe combinations, three cost cases and two clock assumptions. It did not simulate a$500 account or apply the per-trade dollar cap. Strongest primary results were NAS100 M5 pullback (+11.11R,84 outcomes,38.1% wins) and SPX500 M15 breakout (+5.75R,37 outcomes,59.5% wins), before unknown commissions. Their whole-day bootstrap mean-R intervals included zero. The initial1-minute variants were negative on both instruments. Squeeze generated no entries. VWAP candidates lacked actual traded volume; FX and monthly candidates lacked their required markets/history.

## Bounded improvement experiment

The user then authorized a **$25 per-trade ceiling for offline tests** (5% of an initial $500). This did not authorize deployment or a change to the existing bot's portfolio and loss limits.

For each strategy, exactly 24 development configurations were tested: targets 0.75/1/1.5/2R; filters none/EMA50 direction+slope/strong directional close; entry windows 10:00–15:00 or10:00–12:00 New York. Lookback 20, candle-extreme structural stops, maximum holding 1 hour and flatten 15:55 stayed fixed. Minimum lots and lot increments came from current symbol metadata. Stops were never compressed to fit the cap.

The first 15 sessions selected candidates; the last 7 were a **reused chronological stability check**. All30 days had already been inspected, so none of this is a fresh holdout. The fixed development screen required at least 20 outcomes, win rate >60%, PF inR ≥1.2, positive expectancy and positive development stressR. **No variant passed.** The original2R configuration therefore remained the frozen no-improvement comparator.

Two insufficient-sample morning1R challengers were subsequently frozen as explicit exploratory follow-ups before their later-block scoring. They change the target to 1R and the entry window to 10:00–12:00, with no added signal filter. They do not replace the failed 20-outcome gate.

| Morning1R challenger | Full-sample outcomes | Full-sample win rate | Later-block outcomes | Later-block win rate | Full-sampleR |
|---|---:|---:|---:|---:|---:|
| NAS100 M5 pullback |13|61.5%|2|50.0%|+2.99R|
| SPX500 M15 breakout |27|59.3%|8|50.0%|+5.00R|

NAS100 exceeded60% only on a tiny pooled, reused sample. Neither strategy established a reliable win rate above60%. A smaller target can improve win rate while reducing average winning payoff. These results do not satisfy the repository's300-trade/independent-forward-evidence requirements.

## Ending-balance columns

Balances below start at $500, use legal current lot increments, and include modeled spread/slippage, **before unknown commissions**. Historical margin availability is assumed feasible for this conditional calculation and is not verified. These are not real account balances.

| Full-period model | $25-only ending balance | Trades | Ending balance with remaining limits | Trades |
|---|---:|---:|---:|---:|
| NAS100 original2R |$500.21|56|$508.61|7|
| NAS100 morning1R |$553.21|13|$504.40|1|
| SPX500 original2R |$657.40|35|$491.60|4|
| SPX500 morning1R |$630.40|27|$499.70|4|

The **$25-only** column is an isolated sizing scenario that omits the remaining portfolio/daily/drawdown caps; it is not permission to relax them in the bot. Its original NAS100 configuration experienced about44.6% marked drawdown; original SPX500 about18.3%. The morning challengers had about7.2% and7.1% marked drawdown respectively under this scenario. These figures use minute-open liquidation-value marks and final exits, not a complete tick equity path.

The **remaining-limits** column enforces min($25,1% current equity),2% daily pause and10% drawdown halt, one position per separately funded strategy. Its effective initial position-risk allowance is therefore$5. The old0.5% per-trade restriction is superseded only for this diagnostic; no repository execution configuration is changed. Unknown fees can reduce balances or make a marginal lot size ineligible. Risk pauses latch even when price recovers before a next-minute exit. Each development/later row in the CSV restarts at $500; full-period rows carry cash continuously and must not be formed by adding separate ending balances.

Signal outcome counts/win rates and the remaining-limits account trade counts differ because capital constraints reject additional entries. Do not treat the signal win rate as the win rate of the smaller account subset, or add separate-strategy balances into one portfolio.

## Fill model and limitations

Completed bars determine signals; a scheduled entry occurs at the first modeled M1 open 60 seconds later, within the allowed entry window. Ask prices are approximated from bid bars plus reported spread. The improvement run rounds modeled spread up to a legal tick and reward toward entry. Natural stops remain at the signal candle's extreme. Stops win ambiguous stop/target minutes; adverse stop gaps fill at the adverse open. No favorable target-gap improvement is credited. Baseline costs use reported spread plus one adverse tick per side; stress uses1.5 times spread plus two ticks per side. These assumptions cannot reconstruct an executable tick path.

The improvement baselines apply the$25 pre-fee minimum-lot gate and stricter entry-window/tick-rounding rules; they are not directly comparable with the original unconstrained84/37-outcome screen. This is a finite parameter search with multiple testing and previously inspected observations. It does not establish expected future performance. Timezone, point-in-time specifications, margin, fees, spread extremes and execution paths need independent verification before any governed account experiment. No martingale, stop compression, averaging down or real-money execution was used.

## Files and verification

- [Initial aggregate screen](initial_screen.csv): all 120 configurations, including rejected/zero-outcome cases.
- [Development grid](improvement_development.csv): all 48 configurations and development ending-balance columns.
- [Follow-up comparisons](followup_comparison.csv): baseline/challenger, development/later/full periods, both clocks/cost cases and both ending-balance models.
- [Frozen methodology and hashes](methodology.json): original protocol, selection freeze, explicit follow-up and balance-model amendment.
- [Verification](verification.json): 172 existing repository tests and 18 local diagnostic tests passed. Original summaries and account balances reconcile to private ledgers; earlier-data prefix checks passed.

Raw broker bars, price-level trade ledgers, account identifiers, credentials and runtime files remain private. Local analysis scripts and raw inputs are not published in this results-only record, so the public aggregate package alone is not a fully reproducible backtest. No existing research record or engine was replaced.
