# Project Atlas — paper-only research and portfolio controller

Objective: 25–40% annualized net returns with a portfolio drawdown target below10%. These are research objectives, not demonstrated performance.

## Current approved paper account

- Initial simulated equity: $5,000.
- All-in per-trade planned risk: min(0.5% current equity, $25), including modeled entry/exit costs.
- Combined gross planned open risk: 1% current equity, initially $50. The old $25 aggregate ceiling does not apply to this book.
- Daily equity-loss entry pause: 2% of start-of-New-York-day equity. Daily pause resets on a new New York date.
- Peak-equity drawdown entry pause: 10%, latched for review. Existing positions remain managed; no guarantee of a maximum realized loss or drawdown.
- No arbitrary daily trade-count limit. Same-direction positions may coexist within aggregate gross risk and margin reserves; duplicate intents and same-symbol opposing exposure are vetoed. Correlated index risk receives no netting credit.
- Recovery entry confirmations remain. The new account does not inherit the old $10 recovery sizing ceiling.

The original $500/$25-combined benchmark remains a separate preserved configuration. Historical adapters and earlier low-capital research policies are included only as dependencies/comparators; they are not the approved new-account settings.

## Code map

`atlas_portfolio_controller.py` contains the approved constants and shared sizing/admission controller. `atlas_live_core.py` manages local virtual positions, costs and equity pauses. `atlas_forward_service.py` reads existing MT5 prices and metadata, records receipt times, freezes source identities, checkpoints virtual books, and serves the local Trade Dashboard. Its MT5 adapter has no broker order submission or authentication method.

`atlas_capture_inputs.py` reconstructs the three strategies: SPX50015m confirmed morning breakout at1.5R; NASDAQ15m long breakout at1.5R; NASDAQ5m short RSI exits with native stops. Quote replay, frequency/rejection audit, risk/metrics audit, comparison and dashboard generators are included with their transitive source dependencies. `atlas_strategy_attribution.py` independently checks original ledgers and attributes intratrade quote drawdown without changing strategy rules. Earlier tools are finite research runners, not an invitation to restart the obsolete multi-lane supervisor.

## Setup and private inputs

Use Python3.12+ and install `python -m pip install -r research_monitor/requirements-atlas.txt` in an isolated environment. MT5 observation requires Windows, an already-connected local terminal, and the MetaTrader5 package. No credentials are supplied or automated.

The research runners currently use the original workspace layout: `WORKSPACE/outputs/...` for private bar/quote archives and completed research, and `WORKSPACE/work/tradingbot` for this repository. Pass the workspace directory (not the repository directory) to `--root`. Historical runners fail rather than invent missing data and generally require a new output directory. The repository does not include private price archives, execution ledgers, account metadata, live checkpoints or generated financial reports.

The forward adapter currently targets the terminal at `C:/Program Files/MetaTrader 5/terminal64.exe`. Running its service requires the original private input layout and a prepared dashboard under `outputs/atlas_opportunity_v1/report.html`. Source publication alone does not make a fresh checkout a fully provisioned historical dataset or start a collector.

From the repository root, with required private workspace inputs available, use the command below. Inspect existing process identities and the cohort lock first; only one collector may run. Do not launch a second instance beside the existing collector or remove a lock to force startup.

```sh
python -m research_monitor.atlas_forward_service --root WORKSPACE --candidate approved5000 --candidate-capital 5000 --cohort atlas-forward-v2 --port 8878
python -m unittest discover -s research_monitor/tests -p 'test_atlas*.py' -v
```

The service binds to127.0.0.1. Its local GET routes expose read-only dashboard/status data. `stop.request` requests a graceful checkpointed stop. Frozen source changes require preserving the old cohort and freezing a new one; never silently retune an observed cohort. Publishing this source does not change the currently frozen worker.

## Evidence limits

All existing December15,2025–October30,2026 historical prices were previously exposed. Completed replays are not untouched out-of-sample evidence. Account-specific commissions and historical server-clock, contract, margin and fill conditions remain unverified. Standard/higher cost proxies use1x/1.5x spread, $6/$12 roundtrip-per-lot fees and1/2 adverse ticks. Severe scenarios use2x spread, $18 fees,4ticks,1second exit latency and2x margin. Stops may gap through planned risk.

The latest $5,000 allocation admits more trades but does not demonstrate the annual-return objective or robust higher-cost profitability. Preserve profitable earlier benchmarks. No70–75% win-rate claim is established. Collect genuinely new paper outcomes after the cohort freeze without refitting them; no live-capital execution is enabled.
