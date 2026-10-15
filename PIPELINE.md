> Reviewed audit-v3 software: 82/82 suite tests and 8/8 independent adversarial probes passed. Plan version 2.0.0; engine configuration version 5 in engine_v4.py. Planned all-in trade risk is min($2.50, equity * 0.005, equity * configured trade_risk). This is software verification, not a profitability or execution qualification. See AUDIT-CHANGES.json and INDEPENDENT-REVIEW.json for scope and residual limits. The original baseline description below is superseded where audit corrections differ.

# Executable offline research pipeline

Core runner uses the Python standard library; tested on Python 3.15 on Windows. The separately tested closing-continuation signal kernel uses IANA timezone data (system timezone database or the `tzdata` package on Windows). No broker client, network transport, order API, account login, automatic recovery, or trading loop is included. Atlas and its runtime paths remain separate. Existing README.md and RESEARCH.md are preserved.

Run software verification from the repository root:

```text
python -m unittest discover -s tests -v
python -m trading_pipeline synthetic-check --output local-results/synthetic-check-001
```

The second command generates explicitly synthetic input and runs the full training/selection/two-window validation/cost-stress flow. Its simulated fills are software fixtures, not market or broker results. Use a new output directory each time; never replace a previous run. Temporary test artifacts are retained under ignored local-results/ for audit.

## Real-data admission and experiments

Prepare a **private** dataset directory with `manifest.json`, `contracts.json`, `plan.json`, and separate chronological `train.jsonl` and `validation.jsonl` event files. The fixture generator demonstrates the schema, but its values and verification labels must never be relabeled as real evidence.

```text
python -m trading_pipeline register --dataset private-data/cohort-001 --journal local-results/research.sqlite --experiment cohort-001 --output local-results/cohort-001-plan.json
python -m trading_pipeline run --dataset private-data/cohort-001 --journal local-results/research.sqlite --experiment cohort-001 --plan local-results/cohort-001-plan.json --output local-results/cohort-001
```

Registration freezes implementation identity, contracts, dataset manifest, strategy variants, chronological windows and costs. A minimum one-hour embargo, matching the runner's maximum holding time, separates training, validation windows and final holdout. The journal atomically claims an experiment ID, retaining it even after failure or interruption. A crashed/claimed run needs review; it is not silently restarted or reset. Input errors, rejected training, trial failures and unresolved positions remain recorded. SQLite records are append-only with a verified hash chain. These controls prevent accidental rewriting; they are not a security boundary against an administrator who rewrites the entire database.

Required provenance includes source reference, independent review reference, exact file hashes, validated timestamp semantics, a verified bid/ask execution path, effective-dated costs, and unseen validation status. These are assertions that a reviewer must substantiate; setting a Boolean is not external verification. Protected observer receipts are prohibited even if their market timestamps precede October 8. September's existing snapshot is reused development data and does not pass unseen validation admission. The final holdout has a separate commitment and remains locked: **this release has no holdout scoring command**.

An admission-only check of the known September snapshot is available without examining October observer data:

```text
python -m trading_pipeline.audit_legacy --source PATH_TO_EXISTING_PRIVATE_MONTH_SNAPSHOT --output local-results/september-admission-001
```

It verifies the exact historical snapshot hash and counts September timestamps only. It does not calculate signals, returns or fills. Raw data and local journals are not included in the repository.

## Causality, strategies and costs

The preserved engine v3 SHA-256 is `b01fc9091c59e42eaddcc555c6433d14c3e775413fb9e0b40ad107568535c9e2`. Its tested whole-contract controls and next-quote fill rules are reused without editing the original file or Atlas. The new wrapper resets indicators after any discontinuity and permits at most one global position, producing nonoverlapping trades. That does not prove statistical independence.

Implemented runner specifications are version 1.0.0 breakout and pullback from the prior engine. Breakout compares the completed close with preceding lookback highs/lows. Pullback requires a rising/falling preceding-close trend and a mean touch/recovery. Stops use the signal-bar extreme. The first strictly later valid quote consumes the intent; entry uses ask/bid plus adverse slippage. Targets use the registered reward/risk multiple. Stop gaps execute at the available adverse quote, not the planned stop. Default signal lifetime is 60 seconds and maximum holding time is one hour. Read engine_v3.py for the exact frozen rules. These are baseline controls, not reproductions of newly discovered papers.

`TEN_CANDIDATES.md` archives the complete delegated ten-candidate specification and supersedes the early CANDIDATE_SEEDS.json notes. The most compact new candidate, closing-half-hour continuation, has a separate executable signal kernel in closing_continuation.py with winter/summer timezone, availability, warmup, previous-close, gap and contract-identity tests. It emits unqualified intentions only and is intentionally **not yet wired into the risk/fill runner**: the baseline engine's target and timeout rules must not be silently substituted for that candidate's no-target/16:00 rules. Other new candidates remain specification-only. No source claim has been reproduced.

Both baseline and stress scenarios include fees and at least one adverse slippage tick; stress uses 1.5x fees/carry and two ticks. Actual bid/ask spreads remain in the data. No zero-cost scenario is selected to rescue a candidate. Financing adjustments require timestamped provenance; USD-only metadata is required. Expiry-specific roll events require a known successor and flat positions; no stitched fill is invented. Non-USD FX conversion and comprehensive session/calendar-aware strategies are not implemented by this release.

Risk remains USD500 initial equity, 0.5% per trade, 1% aggregate open risk, 2% daily pause and 10% drawdown pause. Whole futures only; margin plus loss reserves must fit. These are risk controls, not guarantees against losses through gaps. No risk relaxation, fractional futures, or leverage assumption is used.

## Validation and interpretation

All registered variants run on training data. A profitable completed training trial is selected by net P&L, then drawdown, then deterministic specification hash. Selection is frozen in the journal **before** reading validation. At least two disjoint chronological validation windows run the same frozen strategy under both cost scenarios with a new USD500 diagnostic cohort per window. This is fixed-origin/anchored forward validation, not a continuously reoptimized portfolio. Returns from separately funded cohorts must not be summed as one account return. Full expanding-window retraining and automated parameter searches are deferred.

Metrics include net P&L, expectancy, profit factor, marked-equity drawdown, closed nonoverlapping trades, trade days, a binomial-reference Wilson win interval and seeded daily-block bootstrap expectancy intervals. Wilson intervals do not correct clustered dependence; daily blocks also have limitations. Zero trades produce unavailable win rate/expectancy, not a claimed 0% win rate. Missing losses produce unavailable profit factor rather than an invented finite value. Open positions at a boundary make the result inconclusive; no boundary fill is fabricated.

The statistical screen requires at least200 nonoverlapping trades,30 trade days, win rate at least60%, positive expectancy and its block-bootstrap lower bound, profit factor at least1.3, drawdown below10%, and positive results in every validation window and cost scenario. These conservative floors are not proof of independence or robustness. Synthetic results cannot pass. `qualified_for_paper` and `broker_execution_enabled` remain false even if statistical thresholds pass: independent strategy/data/cost/execution review is still required. The final holdout remains untouched.

## Current limitations and next milestone

The existing real dataset fails admission: bars only, reused September validation, unverified timestamp semantics and absent effective-dated account costs/margins/eligibility. Therefore there is no real-market performance ranking, qualified strategy, or paper-order evidence from this release. Newly sourced strategies and negative controls remain specification candidates until deterministic implementations and causal tests are reviewed.

The smallest next verifiable milestone is independent review of this runner plus one admitted, provenance-verified bar-and-quote dataset with separate unseen validation and dated contract/cost evidence. Run a preregistered baseline without changing the risk cap, then retain its result whether profitable, rejected, or inconclusive. No scheduler or broker execution is activated by publishing this code.
