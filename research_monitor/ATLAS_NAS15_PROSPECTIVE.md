# NAS15 regime research and prospective receipt-clock validation

This optional research workflow preserves the approved $5,000 all-in min(0.5% equity,$25) trade ceiling,1% gross combined risk,2% daily-loss and10% drawdown entry pauses, natural stops,1.5R and no arbitrary daily quota. It changes no frozen financial core or existing collector. SPX15 remains the companion strategy; NAS5 is excluded in these alternative comparison books.

The development-only v2 screen fixes four hypotheses plus control: adding short breakouts, adding only shorts with the existing strongclose65/efficiency0.30 confirmations, completedUTC4hEMA20 alignment on longs, and that alignment on both directions. Complete4h bars require all240 observed consecutive minutes; no forming bars or gap filling. EMA20 and slope rules transfer the existing hourly confirmation, without a threshold grid. The selected long4h filter improved development NAS and portfolio profit and drawdown at both costs but only reached50% win rate. A rate above60% is not established. Failed variants are retained locally. No already-reviewed June–October prices were rescored for this v2 selection.

`atlas_nas15_prospective.py` freezes the control/h4_long protocol, source identities, legal contract/cost snapshots and prior warmup identities before future financial observations. It reads the existing collector SQLite database in query-only mode; it has no MT5 API, authentication or order transport. It starts no second collector and changes no existing paper book.

This is a hypothetical prospective RECEIPT-CLOCK REPLAY, not actual order execution or real-time evaluator fills. Its recorded first collector receipt times determine available information and virtual execution, even when evaluated later. It reconstructs finalized minute candles causally from received ticks and refuses late revisions or future-dated clock inconsistencies. Signals enqueue only after their complete minute inputs were available. Source-ordered received paths manage virtual stops; a fresh received quote admits entries after the existing60second delay. Prior/pre-freeze data supplies indicators only. Liquidity, actual fills, fees and historical clock/margin remain uncertain.

The evaluator waits for five newly completed sufficiently observed NewYork weekday clock-window sessions beyond the last scored batch. Both symbols need351/390 observed regular-window minutes. It creates immutable quote snapshots and complete fixed-variant ledgers; cumulative batches overlap and are NOT independent repetitions. At least30 NAS fills,75% control capture, WR>60% at both costs, no NAS/portfolio profit decrease and no NAS/portfolio drawdown increase are required by the prospective target gate. Sample size and serial-dependence limitations remain; a candidate selected on these observations needs another new market block. Never refit these frozen rules on the new cohort.

These commands require the private workspace layout and completed development artifacts from ATLAS.md; they refuse to overwrite a cohort or prior run. From repository root:

```sh
python -m research_monitor.atlas_nas15_regime_study --root WORKSPACE
python -m research_monitor.atlas_nas15_prospective --root WORKSPACE --freeze
python -m research_monitor.atlas_nas15_prospective --root WORKSPACE --status
python -m research_monitor.atlas_nas15_prospective --root WORKSPACE
python -m unittest discover -s research_monitor/tests -p test_atlas_nas15_regimes.py -v
python -m unittest discover -s research_monitor/tests -p test_atlas_nas15_prospective.py -v
```

The existing provisioned workspace already has a frozen prospective_v1 protocol; do not repeat --freeze there. Source changes require a new preserved version/cohort, not an override. A status call performs availability checks without financial processing; the finite evaluation refuses an unchanged/insufficient session set. New batch artifacts and quote snapshots remain local. No ongoing optimizer process is implied by a waiting status; the existing quote collector continues while this computer and MT5 remain available. Original benchmarks and every experiment failure remain preserved. Stops and pauses do not guarantee realized-loss ceilings.
