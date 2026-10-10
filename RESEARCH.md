# Trading Bot Research Record

_Last updated: 2026-10-10. Simulation only._

## 1. Objective and honest baseline

Research target: grow an independently funded **USD 500 simulated account to USD 1,000 over seven days**, then test whether the result repeats. This requires a 100% return; it is not a forecast, guarantee, or justification for relaxing risk controls.

Current evidence does **not** establish profitable trading:
- No current training process or continuous collector has been verified.
- Two-hour reviews and automatic recovery have been requested but are not yet activated.
- The feasibility studies below did not compute fills, P&L, ROI, or win rates.
- There is no verified top-ten strategy ranking or complete inventory of all bot runtimes.
- This document records historical findings, not a fresh reproduction of every experiment.

## 2. Evidence register

### Public implementation

[projectatlas commit 16fa1816](https://github.com/jnwokorie1957/projectatlas/commit/16fa1816fe349fe1b688358cc209c1438761ba57) published 40 reviewed files for a **finite, read-only 1OZ historical-data observer**. Its documented publication test run passed 160 tests with one skipped.

That observer does **not** provide quote collection, strategy scoring, trading execution, or an active training service. Its runtime gate is closed. NES and SIC configuration entries in that public revision are not proof that its wire adapter supports those roots.

The public record reports one bounded history diagnostic: 129 callbacks, 126 accepted bars, three quarantines, one 30-minute gap, approximately 7.74 seconds, and a history-end marker. An end marker proves response completion, not complete coverage or a trading edge.

### Previously reviewed, unpublished results

Later multi-root observations and feasibility results below were reported by prior implementation and independent-review work. They have **not been freshly reproduced for this document**, and their underlying private local artifacts are not included in this repository. They are not fully reproducible from the public commit alone.

Reported software checks, across distinct versions and scopes:
- Offline simulator: 39 tests and 12 adverse-condition checks
- Research components: 20 tests
- Earlier observer: 42 tests and four independent checks
- Later local root-enumeration correction: 179 passed, one skipped
- Mean-reversion feasibility review: nine independent tests passed

Do not add these into one unique test count. Software tests are not market-performance evidence.

## 3. Technical successes

A later, locally reviewed three-root batch on 2026-10-08 completed in approximately 26.862 seconds:

| Root | Accepted bars | Quarantines | Timestamp gaps |
|---|---:|---:|---:|
| 1OZ | 128 | 3 | 1 |
| NES | 120 | 3 | 3 |
| SIC | 124 | 5 | 2 |
| Total | 372 | 11 | 6 |

Useful outcomes: bounded data retrieval, completion receipts, explicit quarantines, preserved gaps, and independent ledger checks. These are infrastructure successes, not profitable trades.

**Protection boundary:** observations received on or after 2026-10-08 00:00 UTC remain protected from fitting, optimization, strategy selection, and profitability scoring under the existing policy. Earlier market timestamps inside those later receipts do not make the records development data. This document does not relax that restriction. Quality-only audits are distinct from strategy evaluation.

September data was repeatedly used for development. It is not an untouched validation sample.

## 4. Failed feasibility studies

All figures in this section are previously reported development diagnostics. Opportunity counts can repeat under different scenarios; they are not fills or independent trades.

| Study | Reported scope | Result under existing USD 2.50 trade-risk cap |
|---|---|---|
| Fixed breakout / pullback | 72 diagnostic trials; 992 opportunity occurrences | Zero cost/risk-eligible opportunities |
| Fixed mean reversion | 18 trials; 1,425 scenario occurrences, including 475 baseline opportunities | Zero cost/risk-eligible opportunities |

Minimum reported stop-plus-cost estimates:

| Root | Breakout / pullback | Mean reversion |
|---|---:|---:|
| 1OZ | USD 4.82 | USD 7.57 |
| NES | USD 2.72 | USD 3.47 |
| SIC | USD 8.52 | USD 18.52 |

A separate sensitivity analysis reused the same 992 breakout/pullback occurrences across 144 diagnostics. At a hypothetical USD 5 trade-risk budget, 18 fitted baseline sizing, but none fitted joint cost stress. **The actual operating risk policy was not changed.**

### What went right
- Feasibility was checked before inventing fills or profitability.
- Cost stress exposed fragility hidden by looser sizing.
- Independent checks reproduced the reported mean-reversion counts and arithmetic.
- Failed candidates and uncertainty were retained.

### What went wrong
- Minimum whole-contract stop risk and assumed costs exceeded the small-account budget.
- A larger hypothetical budget did not solve joint cost stress.
- Historical bars alone did not satisfy the existing next-quote execution model.
- Reused development data could not support independent validation claims.

### Lessons for the next test
Check contract economics first. A candidate that cannot fit the budget should be rejected before expensive signal optimization. A failed feasibility test is not a measured monetary loss, and it does not prove the signal lacks predictive value. It does prove that the tested configuration cannot support the proposed execution under its assumptions.

## 5. Constraints to preserve

Existing research defaults:
- Per-trade risk: 0.5% of equity, initially USD 2.50
- Aggregate open risk: 1%, initially USD 5
- Daily loss pause: 2%, initially USD 10
- Drawdown pause: 10%, initially USD 50

These are controls, not guaranteed loss ceilings. Gaps and execution costs can exceed planned loss.

Use whole futures contracts; do not import MT5 fractional-lot or 1:500 leverage assumptions. Applicable margin, fees, eligibility, and causal execution data remain unresolved. Public margin scenarios do not prove account-specific eligibility. QNDX remains excluded because of conflicting tick evidence.

No live orders, broker what-if calls, account changes, credential changes, or automatic scaling are authorized by this research record.

## 6. Two-hour review and ranking specification

During verified active training, snapshot each bot's version, run ID, process state, last progress timestamp, checkpoint, data split, and ledger integrity.

Each report should show up to ten evidence-supported strategies:
1. Net simulated ROI and ending equity after costs
2. Realized and unrealized P&L separately
3. Maximum drawdown, exposure, closed trades, and risk breaches
4. Repeatability across separate evaluation periods
5. What worked, what failed, and supporting evidence
6. One bounded, preregistered next experiment

If fewer than ten qualify, show fewer. If none have valid performance evidence, state that instead of fabricating a ranking. Diagnostic candidates can be listed separately as unranked.

Each weekly evaluation cohort starts with its own USD 500 balance and immutable ledger. Freeze its strategy and cost assumptions. Revisions create new versions and separate cohorts; never reset losses, combine separately funded accounts into one return, or rewrite a cohort to improve reported results.

Net equity ROI = (ending marked-to-market equity minus starting equity) / starting equity, with costs, open-position treatment, time window, and any external flows disclosed. Do not annualize a two-hour result into a weekly promise.

Repeatability requires multiple preregistered, nonoverlapping evaluation periods and disclosure of uncertainty, losing weeks, worst drawdown, and all attempted variants. Overlapping rolling weeks are correlated. A single winning week does not establish repeatability.

## 7. Pause diagnosis and safe recovery

| State | Required response |
|---|---|
| USER_PAUSED | Preserve the explicit stop; do not resume without authorization |
| RUNNING | Review new progress without launching duplicate workers |
| ERROR | Diagnose and repair only an authorized, recoverable technical failure |
| COMPLETED | Preserve results; plan the next distinct experiment |
| MARKET_CLOSED | Treat scheduled inactivity as normal, not a crash |
| OFFLINE_UNKNOWN | Reconnect and reconcile evidence before classifying or restarting |
| RISK_HALT | Preserve the guard; investigate without bypassing it |
| ACCESS_BLOCKED | Report the missing access; do not evade restrictions |

Recovery resumes the same version and cohort from a verified checkpoint after reconciling simulated positions and pending events. Use a single-worker lock and idempotency identifiers to prevent duplicate fills. Keep the original error and bounded retry history. An ambiguous stop is not evidence of permission to restart; risk and access barriers remain in force.

## 8. Next experiments, not completed work

1. Inventory accessible bots and their actual run states. Distinguish code, data collection, development testing, and forward simulation.
2. Verify contract specifications and dated cost assumptions. Reject infeasible candidates under the unchanged budget.
3. Validate a causal execution-data path. With bars only, report signal diagnostics rather than invented next-quote fills.
4. Preregister a small set of fixed hypotheses and permitted data windows; keep the existing protected observations untouched.
5. Add restart and duplicate-prevention tests before enabling autonomous recovery.
6. Verify one complete scheduled review against actual runtime evidence before describing the two-hour service as operational.
7. Compare independent evaluation cohorts only after enough genuine results exist. Retain every failure and amendment.

## 9. Append-only experiment entry

- Experiment ID, UTC timestamp, prior entry, and state
- Hypothesis, predeclared success/failure criteria, and stopping rules
- Code revision, configuration hash, source receipt, and artifact availability
- Development / evaluation / forward-paper designation and earlier data use
- Instrument definitions, costs, risk limits, and execution assumptions
- Starting equity, unique opportunities, repeated scenarios, rejected entries, and fills
- Net ROI, realized/unrealized P&L, drawdown, sample size, and uncertainty, or **not computed**
- What worked, what failed, alternative explanations, and reproduction outcome
- User-pause or failure evidence, recovery actions, and remaining blockers
- Next version and experiment rationale

Corrections must be linked amendments. Never silently erase prior results. Publish only sanitized research summaries; keep credentials, private account records, machine identities, raw broker data, and private captures out of this public repository.
