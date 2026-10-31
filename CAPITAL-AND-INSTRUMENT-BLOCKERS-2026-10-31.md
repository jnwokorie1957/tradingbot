# Capital profile and instrument admission diagnosis

Prepared October 31, 2026 UTC. New research profile: $5,000 starting equity,
$25,000 aspiration. This does not reset or overwrite the $500 studies. It is a
versioned research configuration, not an activated runner or a qualified strategy.
At 01:36 UTC the user approved the NEW profile's all-in cap as
min(0.5% current equity, $25, any lower configured cap). Legacy profiles retain
$2.50. The diagnosis below preserves the earlier $2.50 comparison as historical
context; the new profile is not activated and no admission gate is waived.
No market experiment, broker call or runtime restart was performed for this note.

## What actually blocked progress

Capital was not the only blocker. The separate research worker uses assumed
round-trip fees of $3 for MNQ/MES and $4 for XAUUSD/MCL. These assumptions already
exceed $2.50 before stop risk. They are not verified applicable broker charges.
Increasing equity alone leaves this fixed cap unchanged. Public IBKR pricing lists
$0.25 per side for MNQ/MES/MCL at the first volume tier, plus exchange/regulatory
fees; it does not validate the worker's complete $3/$4 assumptions. Therefore an
unverified assumption must not be described as proof that these products cannot
trade. A dated complete fee model, actual structural stop and execution quotes
are still required. Current public pricing cannot be backdated into prior tests.

The baseline's 50,000 threshold is computational batching, not statistical power
or execution admission. The saved diagnosis at 2026-10-31 01:03:39 UTC found 34,920
positive instrument-minute row-count additions (15,080 below that threshold).
These are neither independent observations nor eligible trades. The expanded
worker's zero new validation rows means zero additions since its completed batch.
The reserved July-September 2025 collection finished October 28 at 20:30:13 UTC;
the expanded receipt at 20:49:44 UTC already included 90,375 MNQ, 90,375 MES,
90,660 XAUUSD and 90,690 MCL validation minutes. That validation is consumed.
It must not be relabeled fresh OOS under a larger capital profile.

## Instrument-by-instrument matrix

All rows below remain NOT ADMITTED for funded simulation. Source metadata is
historical owner-recorded evidence, not a fresh audit of raw prices or holdout.
No private account details or licensed observations are reproduced.

| Product | Identity and minimum unit | Price evidence and split state | Exact unresolved execution inputs / next action |
|---|---|---|---|
| MNQ | CME Micro E-mini Nasdaq-100 future, $2/point; 0.25-point tick = $0.50; one whole contract | Baseline October 29 09:27:52 UTC: 369,688 rows; expanded Q3 count above already used. Bars do not establish next executable bid/ask. | Bind dated contract/expiry, authorized session calendar and causal quotes; replace assumed $3 with effective broker + exchange + regulatory charges and measured/conservative reviewed slippage; dated margin and structural stop unknown. |
| MES | CME Micro E-mini S&P 500 future, $5/point; 0.25-point tick = $1.25; one whole contract | Same baseline timestamp: 369,690 rows; Q3 validation consumed. | Same evidence requirements as MNQ; $5,000 does not prove applicable initial/maintenance margin fits. A one-tick stop alone costs $1.25 before execution costs. |
| XAUUSD | Worker uses a spot-gold midpoint series and assumes multiplier 1, tick 0.01. This is NOT verified as an executable CFD, US spot-gold contract or 1OZ future. | Baseline 13,680 rows at that timestamp; Q3 consumed. Midpoint lacks executable spread and volume; cannot establish a volume-weighted VWAP strategy or fills. | Resolve exact broker product and permitted minimum size before assigning specifications, margin, storage/borrow costs or short eligibility. IBKR's published metals schedule has a $2 minimum per order: if applicable to this exact product/account, a normal entry and exit imply at least $4 commission, exceeding the retained cap. Do not apply that schedule to an unidentified CFD. |
| MCL | NYMEX Micro WTI, 100 barrels; $0.01/barrel tick = $1; one whole contract | Baseline 59,340 rows; Q3 consumed. Worker selects dated contracts with expiry > row date + 7 days. Archive counts across expiries are not unique tradable minutes. | Review roll/calendar mapping, gaps and executable quotes. Replace assumed $4 with dated complete cost evidence; applicable margin and actual structural stop unknown. The seven-day selection rule alone does not prove a valid tradable roll. |

CL is a larger reference archive, not an automatic substitute for MCL. Earlier
1OZ/NES/QNDX/SIC candidates remain separate identities; this profile does not
silently replace them or resolve the previously quarantined QNDX tick conflict.
No current applicable broker margin was verified: the public futures margin URL
redirected to a country/product selector without contract rows. Exchange marketing
margin estimates cannot substitute for an applicable dated broker requirement.

## Non-executing feasibility illustration

For one contract, total planned risk = structural stop distance * multiplier +
round-trip commissions/fees + spread/slippage + applicable carrying/roll costs.
Stop distance must come from a causal setup, never be squeezed to fit the cap.

The following are **zero-cost mathematical ceilings**, not feasible trade sizes:

| Future | Stop ticks at $2.50 ceiling | Stop ticks at hypothetical $25 ceiling |
|---|---:|---:|
| MNQ | 5 | 50 |
| MES | 2 | 20 |
| MCL | 2 | 25 |

Real ceilings are lower after costs. Neither column authorizes execution. The
$25 column remains a zero-cost illustration, not an execution permission. The
new profile now specifies the approved $25 cap; no running process is activated.
At $5,000, retained percentage limits imply $50 open portfolio exposure, $100
daily pause and $500 peak-to-trough drawdown threshold, subject to existing
definitions and any stricter controls. New-profile individual planned risk is now
min(0.5% equity, $25, any lower configured cap), including costs.

## Corrections and remaining work

The separate worker owner applied status-only source changes, then corrected a
defect identified in the first independent review: malformed or unreadable
completion metadata could terminate the expanded worker. The corrected source
passed eight owner-executed mocked tests (0.165 seconds) and the second independent
static review approved it. The reviewer did not rerun tests. Those changes
distinguish completed collection from zero additional rows and label batching
units. No running worker was restarted; deployment remains unverified.
Reviewed expanded-worker SHA256:
`aea730d9313adda53100f2a6804465eedc8fb5b1c97153f39260286fe7b773c4`;
test SHA256: `8d1d671bd8ba1c9baf4b6f86d2de3ea8132845494636c16802f0b667c6b31ce0`;
test receipt SHA256: `650fe3630255e333c176e910a24a99ac373fb1a88d790c83639565c82fa1750b`.
This paragraph supersedes the preparation-time pending-review wording in the
previous commit; it does not imply deployment or experiment authorization.

This profile is not wired into the existing runner yet. Activation must bind a
new experiment identity and reviewed effective execution inputs without replaying
old claims. Existing results remain historical; there are zero demonstrated
compliant admissions or qualified real-market strategies in the cited receipts.
No forward trades or profit claims are added by this correction.

Useful next research work: exact product/fee/calendar admission and causal quote
coverage first; then preregister a new non-overlapping evaluation. A larger-capital
re-evaluation of old validation may be exploratory only. Continue separate
source/specification research, but do not mine consumed Q3 results for a champion.
There is no defensible completion ETA from the saved collection records.

## Official sources consulted October 31, 2026 UTC

- CME MNQ specifications: https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.html
- CME micro equity fact card (MES and MNQ): https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf
- CME MCL specifications: https://www.cmegroup.com/education/courses/basic-principles-of-micro-wti-crude-oil-futures/micro-wti-crude-oil-futures-overview
- IBKR futures pricing (broker component is not all-in): https://www.interactivebrokers.com/en/pricing/commissions-futures.php
- IBKR metals pricing (product-specific applicability required): https://us1.interactivebrokers.com/en/pricing/commissions-metals.php
- IBKR margin selector, no effective contract margin established: https://www.interactivebrokers.com/en/trading/margin-requirements.php

Public pages describe current general terms, not historical/account-specific
receipts. No inferred account residence, eligibility or pricing plan is used.
