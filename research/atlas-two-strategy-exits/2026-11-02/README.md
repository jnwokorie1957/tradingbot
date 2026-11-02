# Atlas two-strategy exit replay

SPX50015m1.5R plus NAS10015m2R, excluding Nasdaq5m; shared5000USD paper account. Dates2025-12-15 through2026-10-30. Approved risk controller unchanged: min(0.5percent equity,25USD)pertrade,1percent grossopen,2percent daily-loss entrypause,10percent peakDD entrypause,no quota.

All prices reused; not independentOOS. Four new replays: standard/higher/severe requested composition and a new severe1.5R/1.5R comparator. Original standard/higher two-strategy controls independently reconciled from preserved ledgers. All four new ledgers independently reconcile money and full quote drawdown. No experimental deployment or live execution. Fees, historical clock, contract/margin and liquidity remain uncertain.

Open index.html for all three cost comparisons. Aggregate outputs only; private quotes, individual fills and decision ledgers remain local. Run source: atlas_exit_research/two_strategy.py. Completed-output guard prevents accidental overwrites.
