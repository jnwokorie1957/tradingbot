# Atlas continuous research ledger

Paper-only. Original three-strategy500USD benchmarks remain the baseline. New5000USD research retains min(0.5percent equity,25USD)all-in pertrade,1percentgrossopen,2percentdaily-loss entrypause,10percentpeak-DD entrypause,no countquota.15/20/25percent MONTHLY is an unproven stretchhypothesis,not a sizinginstruction.

index.html embeds aggregate monthly statistics, original lane identities, all registered experiment folders/results identities,12new development cases and failure reasons. Private quote/trade archives remain local. Partial December is visible but excluded from full-month averages;all funded full weekday months include no-trade months. Currentindependentthresholdfrequencies are unavailable,not0percent.

Newcycle001: late-session momentum and gapreversal, each NAS100/SPX500,threecosts. All four fixed adaptations failed. No parameter refitting or later financial replay, no promotion. Prior eight short-horizon families and all failures remain preserved.

Entrypoints fromrepositoryroot:
- python -m atlas_research_pipeline.workflow --root WORKSPACE --trigger heartbeat
- python -m atlas_research_pipeline.cycle --root WORKSPACE --status
- python -m atlas_research_pipeline.ledger --root WORKSPACE
- python -m atlas_research_pipeline.dashboard --root WORKSPACE
- python -m atlas_research_pipeline.checks

The native heartbeat is the scheduled agent workflow;the CLI orchestrator logs its actual invocations and blocks duplicate workflow locks. It does not claim a future invocation occurred or start duplicate collectors. A completed financial cycle cannot be rerun. Everynew cycle requires preregistered rules, semantic duplicate review, source/dataidentity and retained failure history.

NewIBKR observations remain quarantined. Theconnector rejects one-year1m requests beyond3500points and cannot date-page. Othercomputerroute is needed for longer history. CFD/futures execution models are distinct. No unseen financial validation is claimed.
