# Separate short-horizon discovery

Paper-only NAS100/SPX500 **broker-index proxy** research on closed 1m and 5m candles. This namespace does not import, alter, or execute the existing Atlas strategies or risk controller. It contains no broker connection or order API. Genuine MNQ/MES comparisons are a later, separate validation exercise: these MT5 instruments are not CME Micro E-mini contracts.

## Scope and risk

Each configuration has an isolated $5,000 simulated account, legal current lot increments, natural price stops, and all-in planned risk capped at the lower of 0.5% equity or $25. Gross open risk is capped at 1%; only one position is held in each isolated candidate account. Daily 2% loss and peak-equity 10% drawdown pauses block subsequent entries, not exits. There is no daily trade-count quota. A gap or adverse fill can exceed planned stop risk and pause thresholds. Individual results must not be summed into a portfolio.

Standard costs: recorded bid/ask, one adverse tick at entry and exit, $6/full-lot round-trip commission proxy. Higher costs: 1.5 times recorded spread, two adverse ticks per side, $12/full-lot round trip. Commission and margin are unverified estimates; margin is based on a current contract snapshot. Historical broker clock is uncertain: primary New York DST-linked UTC+2/+3 inference and fixed UTC+3 sensitivity are separate cases. Neither is asserted to be verified historic server policy. Model liquidity is not actual fill evidence.

## Data limits

MT5 minute-resolution adjacency audit found native 1m/5m coverage beginning December 12, 2025 through October 30, 2026, approximately 10.5 months. Older returned records are hourly/daily and are excluded. The one-/two-year request therefore does not establish one or two years of usable minute history. Quote archives provide bid/ask execution paths and derived complete 5m candles; missing minutes are never interpolated. Original raw exports and all previous research remain unchanged.

Expected local archives, outside Git:

- `outputs/nas100_quote_data_v1/{manifest.json,quotes/*.npz}`
- `outputs/spx15_canonical_quote_data_v1/{manifest.json,quotes/*.npz}`
- `outputs/spx15_direction_later_v1/data/{manifest.json,quotes/*.npz}`

Paths are relative to the root above `work/tradingbot`. Reduced quote copies, probes, contract snapshots and ledgers live in new `outputs/short_horizon_mt5_v*` directories. Original archive hashes are verified when making each reduced copy. No terminal connection is opened by these evaluators.

## Finite batches and selection

1. `run.py`: three initial families (band reentry, opening-range failure, close-confirmed inside-bar trap), two markets, two timeframes and 1R/1.5R targets. Each runs at both costs: 48 development cases. Signals deliberately delay entry by 60 seconds. Version 1 failed on a holiday liquidation path and is preserved with source and protocol; version 2 applies the published cash-market holiday/early-close calendar. It changes no family thresholds. No version-2 configuration passed development selection.
2. `extension.py`: separately registered trend EMA reclaim, 20-bar channel retest and RSI2 trend-reclaim adaptations. These are hypotheses, not replications or evidence for the performance of published daily-stock methods. A one-second modeled execution delay is assumed; selections also face a five-second delay sensitivity. This is a changed, explicit execution assumption, not measured historical receipt latency. The 60-second version-2 failures remain recorded.

For each batch, December 15, 2025–May 31, 2026 is development. At most one candidate per market/timeframe is frozen before reading June–October financial outcomes. All strategies/thresholds/costs/risk rules are fixed before financial replay. Target-qualified selections require at least 100 development trades, >=60% net-positive trades, PF>=1.2, positive net and quote-equity drawdown <10% at both costs. A diagnostic selection may be retained with >=30 trades, positive net and drawdown <10% at both costs; it is explicitly not a qualifying system. If no candidate passes either selection tier, no later financial replay is performed.

Selections require at least 30 later trades, the same financial thresholds, full-history qualification and fixed-clock sensitivity. Extension selections also face five-second latency sensitivity. Later-period drawdown is conservatively the continuous account drawdown since the development start; later net and win rate use only later fills. All failed cases and veto reasons remain available. Initial equity, arithmetic reconciliation and causal signal prefixes are checked.

**The historical price period was previously exposed in other projects. These chronological checks are not untouched out-of-sample evidence.** Repeated discovery on it cannot establish independent repeatability. No candidate is promoted without a genuinely new, frozen prospective block or actual Micro E-mini validation. Multiple comparison counts must remain visible, including failed batches. Do not repeatedly refit to June–October outcomes.

## Commands

Run from the repository root with the existing Python environment:

```powershell
../mt5-venv/Scripts/python.exe -m short_horizon_research.checks_extension
../mt5-venv/Scripts/python.exe -m short_horizon_research.run --root C:/Users/IraLaptop/Documents/Codex/2026-10-27/he
../mt5-venv/Scripts/python.exe -m short_horizon_research.extension --root C:/Users/IraLaptop/Documents/Codex/2026-10-27/he
```

Each financial command is deliberately single-use for its registered output version; it refuses to overwrite an existing protocol. Before a new run, its directory must already contain the acquired contract snapshot and preserved-research hash map. Do not delete an old protocol to bypass the guard. Register a new version for a justified hypothesis or fix and retain the old failure. Monitor `progress.json` together with real process identity; a completed finite batch is not a running optimizer.

The local HTML title is **Trade Dashboard**. Financial results, raw prices and runtime identities remain local; this source package can be published without them.

## Primary references

- [John Bollinger's rules](https://www.bollingerbands.com/bollinger-band-rules): band contacts alone are not signals. The reentry hypothesis adds a directional close and known target room.
- [TA-Lib Hikkake implementation](https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_CDLHIKKAKE.c): an original implementation reference, not a profitability claim for our close-confirmed adaptation.
- [Cesar Alvarez's RSI2 research](https://alvarezquanttrading.com/blog/rsi2-strategy-double-returns-with-a-simple-rule-change/): daily equity research; our intraday rules and stopped exits differ substantially.
- [NYSE calendar](https://www.nyse.com/trade/hours-calendars): pre-known full holidays and early closes, not a financial outcome filter.

No website's advertised win rate is accepted as local or independent validation.
