# Atlas bounded entry research

These optional offline drivers do not change or activate the frozen paper-forward cohort, broker routing or approved risk controller.

`atlas_two_strategy_replay.py` compares the user-requested $5,000 SPX15/NAS15 composition with the preserved three-strategy allocation at standard and higher costs. It replays the remaining lanes chronologically rather than subtracting a ledger contribution, reconstructs quote-level equity/drawdown, and verifies that prior results and source files are unchanged.

`atlas_nas15_winrate_study.py` registers six NAS15 entry hypotheses plus control: strong candle close, efficiency>=0.30, their combination, the existing2ATR opening-gap cap, causal15minute retest, and retest with strong impulse close. Retests use completed1minute confirmations, the original structural stop and the existing60second execution delay. No narrower stop, changed1.5R exit, increased risk or threshold grid is used. SPX15 signal rules remain fixed.

Development is December15,2025–May31,2026. Select at most one candidate using development records, persist the selection before continuing that candidate and control through June1–October30,2026, and retain continuous account/recovery state. Later results never select a replacement candidate. Every period has already been exposed to prior research; these are not untouched out-of-sample or independently validated results.

Development gates require at least15 NAS fills per cost and75% baseline capture, positive NAS profit,95% NAS/portfolio profit retention and no greater portfolio drawdown. Ranking then uses minimum two-cost NAS win rate, higher-cost NAS profit and sample size. A clearly labeled diagnostic fallback may be checked if no candidate qualifies. A descriptive rate above60% does not itself establish improvement; preserve a profitable baseline if later costs, profit, drawdown or sample support fail. Binomial confidence intervals do not account for serial dependence or multiple hypothesis selection.

Use the private workspace layout and dependencies documented in ATLAS.md. The runners require NEW fixed output directories and refuse to overwrite prior runs. From repository root:

```sh
python -m research_monitor.atlas_two_strategy_replay --root WORKSPACE
python -m research_monitor.atlas_nas15_winrate_study --root WORKSPACE
python -m unittest discover -s research_monitor/tests -p test_atlas_nas15_winrate.py -v
python -m unittest discover -s research_monitor/tests -p test_entry_quality_v2.py -v
```

Both runners retain min(0.5% equity,$25) all-in trade risk,1% gross simultaneous portfolio risk,2% daily-loss and10% drawdown entry pauses, legal lot increments, margin reserves and no arbitrary daily trade-count quota. Fees, historical clock/margin and actual execution remain unverified. Stops and pauses do not guarantee realized-loss limits. Private prices, ledgers and checkpoints remain local; generated reports are not needed to import this code.
