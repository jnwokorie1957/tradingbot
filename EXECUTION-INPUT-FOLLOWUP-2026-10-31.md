# Execution evidence follow-up — October 31, 2026 UTC

Read-only official-source and saved-source investigation. No orders, subscriptions,
account reads, process probes, restarts, profile activation or market experiment.

## Published fee model, conditional on applicability

For an ordinary outright futures entry and exit, one contract, first IBKR volume
tier, non-member, IBKR both executing and carrying, no special arrangement/tax:

| USD per contract per side | MNQ (CME) | MES (CME) | MCL (NYMEX) |
|---|---:|---:|---:|
| IBKR commission | 0.25 | 0.25 | 0.25 |
| Exchange recovery | 0.35 | 0.35 | 0.60 |
| Regulatory recovery | 0.01 | 0.01 | 0.01 |
| Sum per side | 0.61 | 0.61 | 0.86 |
| Two-side total | 1.22 | 1.22 | 1.72 |

These complete the listed commission/exchange/regulatory components under the
stated assumptions, not total execution cost or verified account pricing. Add
applicable give-up surcharge (published $0.05 per side, waived when IBKR is both
prime and executing broker), taxes, advisor/introducer charges and overnight/roll
charges where applicable. Never add the NFA assessment twice: regulatory recovery
already represents it here. Spread and adverse slippage still require separate
evidence. Financing, settlements and position holding horizon must be specified.

Sources retrieved October 31: [IBKR commissions](https://www.interactivebrokers.com/en/pricing/commissions-futures.php),
[CME recovery schedule](https://portal.interactivebrokers.com/en/accounts/fees/CME.php),
[NYMEX recovery schedule](https://www.interactivebrokers.com/en/accounts/fees/NYMEX.php).
[NFA's dated schedule](https://www.nfa.futures.org/faqs/members/nfa-assessment-fees.html)
states $0.01 per side effective July 1, 2026, increasing to $0.02 July 1, 2027.
IBKR pages do not provide a complete historical effective-date series here.
Do not substitute these current rates into the 2025 validation as verified costs.

At the legacy $2.50 cap, after these fees only, the stop budgets are $1.28 for
MNQ/MES and $0.78 for MCL. Whole-tick ceilings are respectively 2, 1 and 0 ticks,
before spread/slippage. This conditional MCL configuration cannot fit even one
stop tick. It is not proof of universal product infeasibility under other caps,
pricing or dates. No stop is tightened to fit, and no trade is admitted.
At 01:36 UTC the user approved $25 for the new profile, still capped at 0.5% of
current equity and any lower configured cap. With $5,000 equity, the corresponding
fee-only stop budgets are $23.78 (MNQ/MES) and $23.28 (MCL), or 47, 19 and 23 ticks.
Spread/slippage and structural geometry still matter. Larger budgets do not admit
missing quotes or margins. No running profile was changed.

## Available price evidence and exact gaps

Saved collector source requests TRADES for futures, writing OHLCV plus contract ID;
commodity source requests MIDPOINT for gold and maps missing volume to null.
These are price bars, not event-level historical bid/ask quotes. No quote-named
files were present at the inspected research directory's top level; this limited
inventory does not prove absence across all workspaces.

Saved gold product metadata identifies IBKR contract 69067924, XAUUSD, CMDTY,
SMART, tick 0.01, with an empty multiplier. This narrows identity to IBKR commodity
spot history; it does not establish CFD sizing, US spot eligibility, lot minimum
or borrow/financing rules. MCL probe metadata identifies contract 661016519,
expiry November 19, 2026, multiplier 100 and tick 0.01, using TRADES.

A fresh authorized connector lookup resolved MNQ underlying 362687422 on CME
and December 2026 contract 815824267, last trading date December 18. A single
read-only snapshot returned bid/ask and volume fields with status **FROZEN**.
No raw quote values are published. The response supplied no event timestamp for
causal historical replay. It is not admitted as a next-quote execution stream,
not proof of continuous connectivity, and not evidence that local Gateway works.
No repeated snapshots or connection retries were performed.

Minimum missing evidence: timestamped bid/ask with source/delay status and sizes,
contract/expiry and event ordering after each completed signal bar; full required
date coverage and gaps; volume semantics for VWAP; contemporaneous fees, margin,
session/holiday calendar and roll/settlement policy. A current snapshot cannot
repair a historical execution-evidence gap.

## Margin and eligibility requirements

The available connector inventory has no futures-specific margin/permission
query. Account balances are not needed and were not read; order previews are not
used as a workaround. The public margin URL redirects to a selector without
dated instrument rows. Admission needs broker-provided initial and maintenance
margin for the exact expiry/side/session, currency, timestamp/effective period,
overnight transition and house add-ons, plus non-sensitive confirmation of product
eligibility and applicable pricing category. Required collateral must fit the
simulated account after existing exposure and reserves; broker account wealth
does not substitute for the simulation budget.

If authorized read-only records cannot supply these, the minimum manual evidence
is a redacted product/margin/fee schedule or broker confirmation with those fields,
and whether the account is direct/non-member with any pricing add-ons. No account
number, balance, credentials or new permission is requested. Gold additionally
needs the exact executable product/quantity/shorting specification.

## Evidence exposure correction

During metadata inspection, prefixes of two saved October 26, 2026 instrument
probe files inadvertently displayed price bars for XAUUSD and MCL. No strategy
was evaluated or selected from them, and no observations are published here.
The owner was notified. Those probe windows must not be described as wholly unseen
to this reviewing agent. Preserve original claims; quarantine the affected windows
from future independent holdout claims pending evidence review. The wider sealed
dataset was not opened, and no consumed experiment was rerun. Subsequent metadata
inspection explicitly selected non-row fields. This incident is not a test result.
