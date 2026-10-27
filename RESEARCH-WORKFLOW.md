# Research workflow extension — October 27, 2026

This adds governance to `trading_pipeline.journal.Journal`; it does not replace the existing backtester, data admission, risk engines, or Atlas collector. No broker transport, order submission, or data-collection loop is introduced. Live and broker-order execution stay disabled. Original Atlas/PTHHS files and frozen candidates are preserved.

## Implemented

- Immutable strategy versions, five lifecycle categories, reasoned transitions, rejected/retired history, and audit events in the existing hash-chained journal.
- Candidate screen: 300 trades, 30 days, win rate >60%, profit factor >1.5, positive net expectancy and lower confidence bound, drawdown <10%, verified causal execution/costs/margins/calendar, positive chronological windows and stress evidence. These are provisional screens, not proof of profitability.
- Champion promotion requires a candidate, independent reviewer references, bound protocol/result hashes, the current incumbent identity, comparable conditions, meaningful improvement and at least 30 reviewed forward trades with positive net expectancy and passing risk controls. This 30-trade forward floor is a conservative initial workflow choice, not statistical proof. A rollback uses the same reviewed promotion path. Evidence fields are attestations requiring external verification, not cryptographic proof or permission to trade.
- Leaderboards are grouped by evaluation protocol; no pooled ranking across incomparable conditions. Synthetic evidence cannot qualify.
- Permanent trade reviews with evidence kind, rules, expected versus observed behavior, references to similar prior reviews and a proposed hypothesis. A review never alters strategy rules automatically. Synthetic and actual forward metrics are separate.
- Durable two-hour cycle claims with no silent retry after interruption. Daily reporting uses America/Chicago dates. Weekly reports cover the previous completed Monday–Sunday week, catch up once, and do not label current observations as prior-week evidence. Committed report payloads can be exported again after a file-write interruption without rerunning research.
- The existing hosted two-hour research automation was updated rather than duplicated. It performs web discovery and invokes eligible existing jobs through the engineering task; this module is a bounded local checkpoint/report component, not a background service. A configured schedule does not prove worker uptime or a running trading process.

## Usage and recovery

Use one designated governed journal for future research; do not create alternate journals to evade consumed-data controls. Preserve the frozen historical journals and reconcile all prior exposure before admitting new market experiments. The first source-only checkpoint uses a governance journal and cannot launch experiments. Its separation from legacy study journals does not clear any consumed-data restriction.

```text
python -m unittest discover -s tests -p test_research_workflow.py -v
python -m trading_pipeline.research_workflow --journal local-results/research-governance.sqlite --input RESEARCH-CYCLE-INPUT-2026-10-27.json --output local-results/research-cycle.json
```

The CLI never overwrites an output. An existing cycle claim or interrupted registration requires inspection, not an automatic retry. Completed payloads live in `records` under `research_cycle_completed` / `research_report_completed`. Read the committed payload to recover a missing export; retain failures and original outputs. The public input is a dated snapshot, not a request to reuse its timestamp on future runs. Future jobs must provide their actual observation time and fresh source findings. Raw market/account data and local journals must stay private and out of GitHub.

## Risk and remaining work

Starting equity is $500; $10,000 is aspirational. Preserve min(0.5% current equity, $2.50, any lower configured cap), 1% open portfolio, 2% daily pause and 10% drawdown pause, plus all existing structural-stop, session, duplicate, opposite-exposure, integer-contract and margin controls. No martingale, fractional futures, automatic leverage or forced eligibility.

Gateway opened manually and the local TCP port was reachable on October 27 at 15:30:02 UTC. That is not a successful reviewed API/data handshake. The existing collector's closed review gate is unchanged. No newly admitted real next-quote dataset, effective applicable margin/cost evidence, qualified strategy or actual forward trade is available. A previous 45-second synthetic attempt remains incomplete (four finished trial records of five started); it is not a market result or a completed rerun.

The first cycle is source/admission research, not a backtest. Existing breakout/pullback and closing-continuation implementations are reused; the other deterministic cards in TEN_CANDIDATES.md remain specifications. Automatic report-to-trade-review ingestion, complete daily-return Sharpe, automatic hypothesis implementation, live quote collection and end-to-end job supervision are not implemented by this extension. Trade reviews accept explicit records and leave unknowns unknown. No claim of full autonomous trading readiness is made. Independent review is still required before activation or strategy qualification.

## Fresh source review

- [AQR original TSMOM data](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data): monthly factor returns, 1985–2009, 12-month lookback and one-month holding. Legitimate alternative research material, but not expiry-specific executable Nasdaq/1OZ quotes. No download, reconstruction, 60% win-rate verification or strategy reproduction claimed.
- [CME 1OZ FAQ](https://www.cmegroup.com/articles/faqs/faq-1-oz-gold-futures.html): public specification source; observed $0.25 minimum tick. Current venue calendar and effective dates require reconciliation with each proposed historical study. Public exchange examples do not verify account-applicable margin, fees or entitlements.
- [Gao et al. SSRN page](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866): full page access returned HTTP 403. Search metadata is not a full-paper review or independently reproduced performance. Existing closing-continuation specification uses its separately recorded source and must not be silently replaced by a different signal.

No failed or inaccessible source is treated as evidence of profitability. No internet material is executed as code. Source-derived adaptations must state their deviations.
