# Read-only forward evidence audit

This package audits the **existing** Atlas paper observer. It does not connect to MT5, call a broker API, alter a strategy, change risk limits, restart the worker, or create another collector. It stays separate from short-horizon strategy discovery.

The audit:

- Checks actual Windows process identity, creation time and wrapper/worker ancestry rather than trusting a lock or status file alone.
- Verifies status freshness, the paper-only flag and zero reported broker execution calls.
- Compares every frozen financial source file with both its registered SHA-256 and archived source snapshot.
- Reads the active SQLite database in read-only mode and creates a consistent local backup for reproducibility.
- Verifies current lot increments, P&L/commission arithmetic, SPX 1.5R target identity and cash reconciliation; compares checkpoint closed-trade identities with the database event ledger. A synchronization difference is reported separately from a mathematical failure.
- Measures actual incoming complete hours and New York weekday clock-window minute coverage. An unfinished session never counts toward completed observations. Historical warmup does not become new financial evidence.
- Reports current source-versus-first-receipt clock alignment and preserves recorded collection gaps. Delayed/backfilled quotes are explicitly distinguished from executable fresh quotes.

The reported quote drawdown comes from the existing checkpoint; this audit does **not** independently reconstruct the observer's entire floating equity path. A clean audit with zero closed trades is not evidence of profitability or repeatability. The full objective remains incomplete until after-cost performance, drawdown and independent multiple-period consistency are established.

## Commands

From repository root:

```powershell
../mt5-venv/Scripts/python.exe -m research_audits.checks_forward_evidence
../mt5-venv/Scripts/python.exe -m research_audits.forward_evidence --root C:/Users/IraLaptop/Documents/Codex/2026-10-27/he --out C:/Users/IraLaptop/Documents/Codex/2026-10-27/he/outputs/spx15_forward_receipt_audit_v2
```

The output directory must be new. Existing evidence is not overwritten. Subsequent audits require genuinely new observations and a new output identity; do not repeatedly run unchanged snapshots just to show activity. On Windows the process check invokes `Get-CimInstance` read-only.

The first audit attempt is preserved in `outputs/spx15_forward_receipt_audit_v1`: strict JSON reserialization rejected the checkpoint's internal Infinity sentinels. The corrected reader archives checkpoint bytes verbatim rather than rewriting them; report metrics still reject nonfinite values. The collector and its financial state were unaffected. Version 2 completed successfully.

## Current limitations

The November 2 receipt sample supports a current UTC+3 raw-clock offset. This does not certify historical server-time/DST policy. Fees remain the explicit $6/$12 per full-lot round-trip proxies; current contract/margin terms are historically unverified. Quote availability does not prove executable liquidity, and stops/pauses do not guarantee a maximum realized loss.

Pre-open missing observations can make a completed-hour confirmation unavailable. Preserve that restriction and the gap evidence; do not reconstruct missing financial receipts, override the frozen gate or claim unobserved setups were missed winners.

Raw snapshots, process metadata, checkpoints and individual financial ledgers remain local and are not published with this package.

## Scoped availability helper

`power_lease.py` provides a temporary Windows idle-sleep request **only while plugged into AC power**, bound to the existing worker's PID and process-creation identity. A named mutex prevents duplicate helpers for that worker. It opens no broker connection and changes no global power plan or display timer. It releases the request when the worker exits, its own `stop.request` appears, or the configured lease expires. Manual sleep and lid closure remain effective.

```powershell
../mt5-venv/Scripts/python.exe -m research_audits.checks_power_lease
../mt5-venv/Scripts/python.exe -m research_audits.power_lease --worker 14228 --state C:/Users/IraLaptop/Documents/Codex/2026-10-27/he/work/tradingbot/local-results/atlas-power-lease-v1 --hours 8
```

The deployed helper is started with a hidden window. Inspect its actual process plus `status.json` in that separate helper directory. Do not launch a duplicate or use a stale PID. To stop it, create `stop.request` in **the helper directory**, not the observer directory. On battery or unknown power, its status is `waiting_for_AC_power` and it holds no keep-awake request. A running helper in that state is not a fix for missing observations.

System logs on November 2 recorded Modern Standby Idle Timeout entries and matching user-presence resumes. A 14:38–14:46 UTC standby interval coincided with the observer's receipt gap and about 166 seconds of unretrieved source quotes. The actual power plan had 300-second AC / 180-second battery idle-sleep timers; the laptop was on battery. The plan was left unchanged. Keep the computer plugged in and awake for reliable observation; existing gaps must stay missing, not be backdated.

Microsoft references: [SetThreadExecutionState](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate), [power requests and Modern Standby limitations](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powersetrequest). The request is not a guarantee against disconnection, manual sleep, broker outages or data loss. Verify actual subsequent minute coverage before declaring availability restored.
