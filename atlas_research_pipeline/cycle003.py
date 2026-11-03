"""One frozen capped-variance sizing comparison, six development cases only."""
import argparse
import json
import os
import shutil
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path

from atlas_exit_research.audit import reconcile
from atlas_exit_research.control_check import inputs
from atlas_exit_research.data import Market, NY, sha, stamp, write
from atlas_exit_research.run import describe, entry_identity, SPLIT
from research_monitor.atlas_opportunity_study import COSTS
from research_monitor.atlas_portfolio_controller import APPROVED
from .variance_budget import VarianceBook


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    repo = root / 'work/tradingbot'
    out = root / 'outputs/atlas_research_pipeline_v1/cycles/003'
    if out.exists():
        raise ValueError('Cycle003 exists; preserve completed work and failures, never rerun.')
    prep = root / 'outputs/atlas_research_pipeline_v1/feasibility/variance_budget_v1'
    feasibility = json.loads((prep / 'results.json').read_text())
    assert feasibility['status'] == 'FEASIBLE_FOR_SEPARATE_FINANCIAL_PROTOCOL'
    checks = subprocess.run([os.sys.executable, '-m', 'atlas_research_pipeline.checks_variance'],
                            cwd=repo, capture_output=True, text=True, check=True)
    state = repo / 'local-results/atlas-research-pipeline'
    lock = state / 'cycle.lock.json'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, json.dumps(dict(pid=os.getpid(), started_utc=stamp(), cycle='003')).encode())
    os.close(fd)
    out.mkdir(parents=True)
    try:
        original = json.loads((repo / 'local-results/atlas-forward-v2/freeze.json').read_text())
        sources = list((repo / 'atlas_exit_research').glob('*.py'))
        sources += [repo / ('trading_pipeline' if n == 'engine_v4.py' else 'research_monitor') / n
                    for n in original['source_hashes']]
        sources += [Path(__file__).parent / n for n in ['variance_preflight.py', 'variance_budget.py', 'checks_variance.py', 'cycle003.py']]
        frozen = {str(p.relative_to(root)): sha(p) for p in sources}
        protected_paths = [root / 'outputs/atlas_pair_holding_v1/results.json',
                           root / 'outputs/atlas_pair_holding_v1/protocol.json',
                           root / 'outputs/atlas_pair_prospective_v1/protocol.json',
                           root / 'outputs/atlas_nas15_prospective_v1/protocol.json',
                           root / 'outputs/atlas_exit_management_v1/data_identity.json']
        protected_paths += list(prep.glob('*.json'))
        protected = {str(p.relative_to(root)): sha(p) for p in protected_paths}
        for name, identity in original['source_hashes'].items():
            assert sha(repo / ('trading_pipeline' if name == 'engine_v4.py' else 'research_monitor') / name) == identity
        protocol = dict(registered_utc=stamp(), cycle='003', hypothesis='Reduce only new-entry risk after an elevated previous complete reference-session realized variance; keep every original signal and exit.',
            profiles=['control', 'capped_prior_variance'], cases=6,
            pre_registered_data_feasibility_protocol=sha(prep / 'protocol.json'),
            formula='When available: scale=min(1,median60/priorVariance), normalizer uses60 complete sessions strictly before the immediately preceding weekday. No leverage or risk increases.',
            unavailable_feature='Leave original allocation unchanged; record feature unavailable, never impute variance, carry a stale variance or shorten warmup. Include these unchanged trades in the full development ledger, distinguish feature-available and actually-reduced exposure.',
            allocation='Take original legal allocator output; quantity=min(original quantity,floor_to_legal_step(scaled original per-trade budget/all-in perlot risk)). Preserve every original veto. Add a separate veto when scaled budget cannot cover a legal minimum. Gross exposure, margins, duplicates, pauses and recovery gates remain enforced.',
            fixed_entries_exits='SPX15 original1.5R60minutes plus NAS15 fixed2R90minutes capped16NY; unchanged60second entry delay, natural initialstops, recovery rules and signal universe.',
            risk=APPROVED, costs=COSTS, development=['2025-12-15', '2026-05-31'],
            later='Not scored. All historical data already exposed; no walk-forward or untouched validation claim.',
            selection='Single fixed candidate; require EACHcost portfolio>=30 and EACHlane>=20 closedtrades, >=20 actually-reduced closedtrades total and>=10 in EACHlane, >=75% control trade capture, positive net,PF>=1.1, portfolio and EACHlane net>=control, portfolio and EACHlane contribution fullquoteDD<=control and<10%. Lower95% weekly bootstrap netR must be positive. No sensitivity fallback, threshold adjustment, later continuation or automatic deployment.',
            data_feasibility=feasibility, source_sha256=frozen, protected_sha256=protected,
            all_prices_reused=True, independent_validation=False, active_paper_changed=False,
            observation_restarted=False, ict_source_used=False, deployment=False)
        write(out / 'protocol.json', protocol)
        write(out / 'preflight.json', dict(exit_code=0, synthetic_checks=10, output=checks.stdout + checks.stderr))
        snapshot = out / 'source'
        for path in sources:
            dest = snapshot / path.relative_to(repo)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        features = {s: {r['date']: r for r in json.loads((prep / f'private_features_{s}.json').read_text())['features']}
                    for s in ['NAS100', 'SPX500']}
        archive = root / 'outputs/atlas_exit_management_v1'
        identity = json.loads((archive / 'data_identity.json').read_text())
        assert all(sha(root / v['cache']) == v['sha256'] for v in identity.values())
        write(out / 'data_identity_audit.json', dict(cache_sha256={s: v['sha256'] for s, v in identity.items()}, all_match=True))
        all_lanes, meta = inputs(root)
        lanes = {n: v for n, v in all_lanes.items() if n in ['SPX15', 'NAS15']}
        signals = entry_identity(lanes)
        market = Market(root, archive)
        rows, audits, parity = [], {}, {}
        for profile in ['control', 'capped_prior_variance']:
            for cost in COSTS:
                write(out / 'progress.json', dict(status='running', pid=os.getpid(), completed=len(rows), total=6, profile=profile, cost=cost))
                book = VarianceBook(market, lanes, meta, COSTS[cost], {'SPX15': 'original', 'NAS15': 'fixed_2'},
                                    durations={'NAS15': 90}, variance_features=features, enabled=profile != 'control')
                book.run_to(SPLIT)
                account = book.result()
                assert not account['open_positions'] and not account['incomplete_paths']
                audit = reconcile(market, book.fills, meta, COSTS[cost], account)
                if profile == 'control':
                    old = json.loads((root / f'outputs/atlas_pair_holding_v1/private_fills_{cost}.json').read_text())
                    prefix = [f for f in old if datetime.fromtimestamp(f['exit_at'], timezone.utc).astimezone(NY).date().isoformat() < SPLIT]
                    assert book.fills == prefix, 'Frozen control parity failed'
                    parity[cost] = True
                executed = {r['id']: r for r in book.decisions if r['status'] == 'EXECUTED'}
                exposure = {n: dict(feature_available_closed=sum(f['strategy'] == n and executed[f['id']].get('variance_feature_status') == 'feature_available' for f in book.fills),
                                   reduced_closed=sum(f['strategy'] == n and executed[f['id']].get('variance_budget_scale', 1.) < 1 and executed[f['id']].get('quantity', 0) < executed[f['id']].get('unscaled_quantity', 0) - 1e-9 for f in book.fills)) for n in lanes}
                row = dict(profile=profile, cost=cost, account=account, metrics=describe(book, end=SPLIT),
                           strategies={n: describe(book, end=SPLIT, fills=[f for f in book.fills if f['strategy'] == n]) for n in lanes},
                           contribution_drawdown=audit['contribution_quote_drawdown'], exposure=exposure, independent_validation=False)
                rows.append(row)
                audits[profile + '_' + cost] = {k: v for k, v in audit.items() if k != 'curve'}
                write(out / f'private_fills_{profile}_{cost}.json', book.fills)
                write(out / f'private_decisions_{profile}_{cost}.json', book.decisions)
                write(out / 'results.json', rows)
        decisions = {}
        for cost in COSTS:
            a = next(r for r in rows if r['profile'] == 'control' and r['cost'] == cost)
            b = next(r for r in rows if r['profile'] != 'control' and r['cost'] == cost)
            ci = b['metrics']['weekly_block_bootstrap_net_R_95pct']
            gates = dict(portfolio_sample=b['metrics']['trades'] >= 30,
                         lane_samples=all(b['strategies'][n]['trades'] >= 20 for n in lanes),
                         reduced_sample=sum(r['reduced_closed'] for r in b['exposure'].values()) >= 20 and all(r['reduced_closed'] >= 10 for r in b['exposure'].values()),
                         capture=b['metrics']['trades'] >= .75 * a['metrics']['trades'],
                         positive=b['metrics']['net_pnl'] > 0, PF=(b['metrics']['profit_factor'] or 0) >= 1.1,
                         portfolio_profit_no_lower=b['metrics']['net_pnl'] >= a['metrics']['net_pnl'] - 1e-7,
                         lane_profits_no_lower=all(b['strategies'][n]['net_pnl'] >= a['strategies'][n]['net_pnl'] - 1e-7 for n in lanes),
                         portfolio_DD_no_higher=b['account']['quote_drawdown_pct'] <= a['account']['quote_drawdown_pct'] + 1e-8,
                         lane_DDs_no_higher=all(b['contribution_drawdown'].get(n, 0) <= a['contribution_drawdown'].get(n, 0) + 1e-8 for n in lanes),
                         DD_below10=max([b['account']['quote_drawdown_pct']] + list(b['contribution_drawdown'].values())) < 10,
                         uncertainty_lower_positive=bool(ci and ci[0] > 0))
            decisions[cost] = dict(checks=gates, passed=all(gates.values()), old_net=a['metrics']['net_pnl'], new_net=b['metrics']['net_pnl'],
                                   delta=b['metrics']['net_pnl'] - a['metrics']['net_pnl'], old_quoteDD=a['account']['quote_drawdown_pct'], new_quoteDD=b['account']['quote_drawdown_pct'])
        assert signals == entry_identity(lanes)
        assert all(sha(root / p) == h for p, h in frozen.items())
        assert all(sha(root / p) == h for p, h in protected.items())
        write(out / 'independent_audit.json', dict(all_pass=True, control_prefix_matches=parity, records=audits, verification='Arithmetic and full quote paths under estimated inputs; not independent financial validation.'))
        write(out / 'decisions.json', dict(costs=decisions, all_costs_pass=all(r['passed'] for r in decisions.values()), later_cases=0, promotion=False))
        write(out / 'completed.json', dict(at_utc=stamp(), cases=6, later_cases=0, originals_preserved=True, active_paper_changed=False, independent_validation=False))
        write(out / 'progress.json', dict(status='completed', completed=6, total=6))
        print(json.dumps(decisions, allow_nan=False))
    except BaseException:
        write(out / 'failure.json', dict(at_utc=stamp(), traceback=traceback.format_exc(), automatic_restart=False))
        write(out / 'progress.json', dict(status='failed', pid=os.getpid()))
        raise
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
