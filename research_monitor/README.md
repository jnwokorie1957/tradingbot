# Trade Dashboard

A local, read-only view of causal research runs: candlesticks, planned market intents, simulated entries/exits, structural stop and target levels, an eased processing cursor, current balance/equity, and realized/open P&L in dollars and percentages. Green and red indicate positive and negative P&L. A new run ID automatically transitions to its market window.

## Open locally

From the repository root with Python3.10+:

```sh
python -m research_monitor.server --port 8765
```

Open `http://127.0.0.1:8765/` in Codex. The server binds only to loopback and serves a fixed allowlist of UI assets. It exposes no order submission or remote-control endpoint. There are no frontend dependencies, CDNs, build steps, cookies or external requests. The UI is responsive, supports chart zoom/hover and reduced-motion preferences.

The server reads `local-results/research-monitor/state.json` (already ignored by the repository). Price bars, snapshots and ledgers stay local. Never commit the state directory. Start the producer separately:

```sh
python -m research_monitor.local_run --data-dir private-data/mt5 --metadata private-data/symbol_metadata.json --pace 0.004
```

The `--pace` option is an explicit per-observation visualization delay; set it to0 for full-speed computation. It does not change prices, signals, outcome sequencing or the stopping condition. The batch is finite: sixteen development variations, then four later-period cost checks after selection is frozen. It does not loop or claim continuous operation. The server remains available after the batch and shows its completed status.

## Inputs

Private data folder:

- `NAS100_M1_30days.csv`, `NAS100_M5_30days.csv`
- `SPX500_M1_30days.csv`, `SPX500_M15_30days.csv`

Required columns: `time_epoch_mt5,open,high,low,close,spread,tick_volume`. `time_epoch_mt5` is the broker's raw reported time integer, not independently verified UTC. This adapter explicitly assumes UTC+3, matching the prior study's primary scenario.

The metadata JSON maps `NAS100` and `SPX500` to `trade_tick_size`, `trade_tick_value_loss`, `volume_min`, `volume_step`, and `point`. These are current symbol properties; historical applicability and margin remain unverified. Credentials and account identifiers are neither required nor read.

## What is running

The causal local adapter reuses the repository's unchanged breakout/pullback signal kernel. It compares lookback10/30, reward1/1.5R, and unfiltered/EMA50 direction+slope, on NAS100 M5 pullback and SPX500 M15 breakout. It uses completed native bars, entries at a later M1 open60 seconds after the decision, the natural signal-candle extreme as stop, legal lot steps and an isolated$25 planned-risk ceiling. Morning entries are10:00–12:00 New York, with maximum holding one hour. An entry after12:00 is rejected even if its decision occurred by12:00.

The current minute alone triggers fills. Stop/target collisions choose the stop; adverse gaps use the opening price. Historical ask prices are approximated from bid OHLC plus rounded reported spread, with one adverse tick per side (stress:1.5times spread and two ticks). No future-bar lookup chooses an exit.

The first15 observed sessions are development. The remaining sessions are a reused later-period check, **not an untouched holdout**. Selection is exploratory: highest development meanR with at least10 outcomes, otherwise the configuration with most outcomes. Neither this selector nor any displayed win rate satisfies the separate governed qualification rules. All variants and losing results remain in dated private batch JSON records.

The balance display is an **isolated cap-only simulation**, before unknown commissions and with margin unverified. It does not enforce or alter the original bot's remaining portfolio/daily/drawdown restrictions and is not a deployable account result. No broker connection, live execution, permission change or engine modification is included.

## Prioritized reruns and entry-quality follow-up

Two additional finite producers use the same local view and private inputs:

```sh
python -m research_monitor.priority_run --data-dir private-data/mt5 --metadata private-data/symbol_metadata.json --state-dir local-results/research-monitor
python -m research_monitor.review_run --data-dir private-data/mt5 --metadata private-data/symbol_metadata.json --state-dir local-results/research-monitor --after-file local-results/research-monitor/priority-results.json
```

The priority producer re-runs the prior NAS100 morning1R and SPX500 day-session2R leaders, then repeats both with higher costs. The follow-up waits for completion before taking over the snapshot; two producers must not write the same view concurrently. It compares the original1R morning rule with explicit hypotheses derived from development wins/losses: NAS directional candle-close strength and long-only entries separately/combined; SPX short-only and a1.5ATR maximum natural stop distance separately/combined. The price stop is never shrunk. The threshold is applied using only the volatility estimate and current entry quote already available.

These are tiny, post-hoc strata from previously seen prices, not established edges. Freeze choices on the development block before later-period and higher-cost checks. Keep all rejected configurations and failures. Completed/private records contain per-outcome prices and reasons for later diagnosis; none belongs in the public source folder. A transient Windows reader lock is retried before atomically replacing a snapshot.

## Attach another runner

`Reporter` provides atomic private snapshots; `EngineObserver` adapts the existing event/output/state shapes. Call it only after an event has actually been admitted and processed:

```python
from research_monitor.telemetry import EngineObserver

view = EngineObserver('local-results/research-monitor')
view.begin_trial(run_id, {
    'hypothesis': {'family': 'breakout'},
    'phase': 'development', 'scenario': {'id': 'baseline'},
    'synthetic': False,
}, total=len(admitted_events))
for event in admitted_events:
    outcome = engine.apply(event)
    view.on_event(engine, event, outcome)
view.finish_trial({'status': 'completed_exploratory', 'metrics': {}})
```

This adapter is opt-in. Other repository runners are not automatically activated or connected. The page polls the actual local snapshot every750ms. It labels an old producer as paused and a finished producer as complete. It does not manufacture progress between observations. The vertical cursor eases toward the current processed timestamp; visual easing does not move the underlying observation clock.

Historical replay support is optional through a private `replays.json` with a `runs` array. Such playback is explicitly labeled `RECORDED REPLAY`; it is separate from `OBSERVED RUN`. The page does not ship with invented prices or example balances.

## Verification

```sh
python -m unittest discover -s research_monitor/tests -v
python -m unittest discover -s tests -q
node --check research_monitor/static/app.js
```

The visible page title is **Trade Dashboard**. Browser content deliberately uses “run,” “observation,” “simulation” and “replay” terminology.

