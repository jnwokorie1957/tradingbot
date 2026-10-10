# Trading Bot Research

Evidence-based research for simulated trading. This repository records successes, failures, unresolved questions, and versioned experiments. It does not claim a profitable or running trading system.

## Current objective

Evaluate whether a separately funded USD 500 simulated account can reach USD 1,000 over seven days, and whether results repeat across independent periods. This is an aspirational research target, not an expected return. Risk controls must not be loosened to reach it.

## Research record

See [RESEARCH.md](RESEARCH.md) for the initial evidence register, failed feasibility tests, recovery policy, and next experiments. Updates should preserve prior results and identify their evidence sources.

A two-hour review during active training has been requested. Scheduling, runtime access, and automatic recovery are not yet verified or activated. No current top-ten profitable-strategy ranking or paper P&L has been established.

## Boundaries

- Simulation only; no live trading or broker order submission
- Net results must include realistic costs, drawdowns, and uncertainty
- Separate historical development, held-out evaluation, and forward paper results
- Preserve explicit user pauses and risk halts
- Never erase losses, fabricate fills, or reuse protected observations for optimization
- This is a public repository: exclude credentials, account identifiers, private runtime captures, raw broker data, and personal financial records

## Related implementation

Previously published read-only research infrastructure remains in [projectatlas](https://github.com/jnwokorie1957/projectatlas/tree/16fa1816fe349fe1b688358cc209c1438761ba57/tools/ibkr-paper-sim/data-observer). This repository does not move, activate, or replace that runtime.

Initial record date: 2026-10-10.
