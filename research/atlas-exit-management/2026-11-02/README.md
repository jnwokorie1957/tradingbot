# Atlas existing-strategy exit comparison

Open index.html directly. The report embeds aggregate data and works offline. Raw prices, individual fills, decisions and running account files remain local.

Scope: unchanged SPX50015m confirmed long breakout, NAS10015m selective long breakout/recovery filter, NAS1005m short RSI2 pullback. Eight exits,3cost settings;72full rows represent66unique lane/cost replays because breakout fixed1.5R equals the original. An additional3shared-account diagnostic replays use one unchanged approved5000 controller. No new entry strategy, live execution or automatic promotion.

Dates:2025-12-15 through2026-10-30. All historical prices previously exposed. Development ends2026-05-31; later replay is descriptive continuation,not untouched validation. Selection frozen before each lane later outcomes. No parameter search is repeated after outcomes.

Approved risk: min(0.5percent currentequity,25USD) all-in planned pertrade;1percent grosscombinedopen;2percent daily-loss entrypause;10percent peakDD entrypause;no daily trade-countquota. Initial5000USD. Existing500USD reports and risk budgets remain intact. Stops and pauses do not guarantee realized loss limits.

Arithmetic verification is distinct from predictive validity. Costs, historical clock and margins remain uncertain;see dashboard. No candidate qualifies as independently validated. Prospective protocol is frozen but not activated. Existing observer remains separate and unchanged.

Commands from repository root, with local archives present:

- ../mt5-venv/Scripts/python.exe -m atlas_exit_research.checks
- ../mt5-venv/Scripts/python.exe -m atlas_exit_research.baseline --root WORKSPACE
- ../mt5-venv/Scripts/python.exe -m atlas_exit_research.control_check --root WORKSPACE --version control_parity_v3
- ../mt5-venv/Scripts/python.exe -m atlas_exit_research.run --root WORKSPACE
- ../mt5-venv/Scripts/python.exe -m atlas_exit_research.audit --root WORKSPACE
- ../mt5-venv/Scripts/python.exe -m atlas_exit_research.report --root WORKSPACE

Completed output guards intentionally prevent overwriting benchmarks or rerunning completed work. Failed control revisions are retained locally. Original engine sources are never edited.
