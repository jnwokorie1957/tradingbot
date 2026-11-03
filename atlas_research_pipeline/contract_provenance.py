"""One finite documentary audit; never connects to a broker or scores prices.

Capture time and agreeing copies cannot establish a historical contract timeline.
The discovery corpus is bounded and excludes the separate ICT study entirely.
"""
import argparse
import hashlib
import json
import subprocess
from collections import Counter
from html import escape
from pathlib import Path

from atlas_exit_research.data import sha, stamp, write
from .spread_preflight import frozen_audit


FIELDS = ('point', 'digits', 'trade_tick_size', 'trade_tick_value_profit',
          'trade_tick_value_loss', 'trade_contract_size', 'volume_min', 'volume_step')
EFFECTIVE = ('effective_from', 'effective_to', 'valid_from', 'valid_to', 'effective_date')
CAPTURE = ('captured_utc', 'captured_at', 'snapshot_utc')
SKIP = ('account', 'account_info', 'private_fills', 'curve')
REFERENCES = [
    dict(title='MetaQuotes symbol_info',
         url='https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py',
         scope='The documented call accepts a symbol name and returns its properties. It has no historical as-of parameter. This does not establish a broker revision timeline.'),
    dict(title='MetaQuotes price precision and tick properties',
         url='https://www.mql5.com/en/book/automation/symbols/symbols_point_tick',
         scope='Decimal representation, price-change step and monetary tick value are distinct properties. The documentation describes tick values as current; it does not certify this account historical settings.'),
]


def discover(root):
    command = ['rg', '-l', '--max-filesize', '500K', '"trade_tick_size"', 'outputs', 'work',
               '-g', '*.json', '-g', '!outputs/ict_mentorship_2022_v1/**',
               '-g', '!work/ict*/**', '-g', '!**/.git/**',
               '-g', '!**/site-packages/**', '-g', '!**/node_modules/**']
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
    return command, sorted(set(Path(p).as_posix() for p in result.stdout.splitlines()))


def extract(value, path=(), symbol=None, captures=(), effective=()):
    """Project only contract fields and documentary timing; never fill/account data."""
    found = []
    if isinstance(value, dict):
        symbol = value.get('name') if value.get('name') in ('NAS100', 'SPX500') else symbol
        captures = captures + tuple((k, str(value[k])) for k in CAPTURE if value.get(k))
        effective = effective + tuple((k, str(value[k])) for k in EFFECTIVE if value.get(k))
        if 'trade_tick_size' in value and symbol in ('NAS100', 'SPX500'):
            found.append(dict(symbol=symbol, json_path='/' + '/'.join(path),
                              properties={k:value[k] for k in FIELDS if k in value},
                              capture_fields=list(captures), effective_fields=list(effective),
                              historical_applicability_verified=False))
        for key, child in value.items():
            if key in SKIP:
                continue
            context = key if key in ('NAS100', 'SPX500') else symbol
            if isinstance(child, (dict, list)):
                found += extract(child, path + (key,), context, captures, effective)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            if isinstance(child, (dict, list)):
                found += extract(child, path + (str(i),), symbol, captures, effective)
    return found


def summarize(documents):
    result = {}
    for symbol in ('NAS100', 'SPX500'):
        nodes = [(d, n) for d in documents for n in d['nodes'] if n['symbol'] == symbol]
        # Equal values or identical bytes describe redundancy, not independent reads.
        captures = sorted({v for _, n in nodes for _, v in n['capture_fields']})
        property_values = {k:sorted({json.dumps(n['properties'][k], sort_keys=True)
                                    for _, n in nodes if k in n['properties']}) for k in FIELDS}
        result[symbol] = dict(documents_with_properties=len({d['file'] for d, _ in nodes}),
            property_records=len(nodes), unique_document_hashes=len({d['sha256'] for d, _ in nodes}),
            records_with_explicit_capture_time=sum(bool(n['capture_fields']) for _, n in nodes),
            explicit_capture_times=captures,
            records_with_effective_fields=sum(bool(n['effective_fields']) for _, n in nodes),
            observed_property_values={k:[json.loads(v) for v in values] for k, values in property_values.items()},
            conflicting_observed_property_values=any(len(v) > 1 for v in property_values.values()),
            historical_applicability_verified=False,
            verdict='NO_VERIFIED_HISTORICAL_CONTRACT_MAPPING_IN_BOUNDED_CORPUS')
    return result


def checks():
    node = {'name':'SPX500', 'trade_tick_size':0.1, 'point':0.1, 'digits':1,
            'captured_utc':'2026-10-28T00:00:00Z', 'time':1760000000}
    a = extract(node)[0]
    assert not a['effective_fields'] and not a['historical_applicability_verified']
    assert extract({'SPX500':node})[0]['symbol'] == 'SPX500'
    assert extract({'account':node, 'symbol':node}) == extract({'symbol':node})
    explicit = extract(dict(node, effective_from='2025-12-15', effective_to='2026-10-30'))[0]
    assert len(explicit['effective_fields']) == 2 and not explicit['historical_applicability_verified']
    docs = [dict(file='a', sha256='same', nodes=[a]), dict(file='b', sha256='same', nodes=[a])]
    s = summarize(docs)['SPX500']
    assert s['documents_with_properties'] == 2 and s['unique_document_hashes'] == 1
    other = extract(dict(node, trade_tick_size=0.01))[0]
    assert summarize(docs + [dict(file='c',sha256='different',nodes=[other])])['SPX500']['conflicting_observed_property_values']
    return dict(passed=6, scope='Document projection, capture/effective-time separation, duplicate identity, conflict detection; no financial performance checks.')


def render(public):
    rows = ''.join('<tr><td>' + escape(s) + '</td><td>' + str(v['documents_with_properties']) +
        '</td><td>' + str(v['unique_document_hashes']) + '</td><td>' +
        str(v['records_with_effective_fields']) + '</td><td>UNRESOLVED</td></tr>'
        for s, v in public['instruments'].items())
    refs = ''.join('<li><a href="' + r['url'] + '">' + escape(r['title']) + '</a>: ' +
                   escape(r['scope']) + '</li>' for r in REFERENCES)
    needs = ''.join('<li>' + escape(x) + '</li>' for x in public['required_evidence'])
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trade Dashboard</title><style>body{background:#0b1320;color:#e5edf8;font:16px/1.65 Segoe UI,sans-serif;max-width:1100px;margin:auto;padding:32px}a{color:#80b7ff}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #293b53;text-align:left}.notice{border-left:3px solid #f4cf82;padding:16px;background:#142133}</style></head><body><h1>Trade Dashboard</h1><h2>Historical contract provenance</h2><p class="notice">Documentary review completed. Historical applicability remains unresolved. No new financial comparison, repaired price history or profitability claim.</p><p>' + escape(public['corpus_scope']) + '</p><table><thead><tr><th>Instrument</th><th>Documents</th><th>Distinct document hashes</th><th>Records with effective fields</th><th>Historical mapping</th></tr></thead><tbody>' + rows + '</tbody></table><p>Document counts include derived and repeated records. Different file hashes do not prove independent broker observations. Agreement among October/November snapshots cannot establish earlier settings. Capture timestamps and quote timestamps are not contract-effective dates.</p><h2>Evidence needed before reconciliation</h2><ul>' + needs + '</ul><p>The list is a review plan, not proof that a broker can supply every item. No contact or broker connection was initiated. Existing benchmarks and approved risk controls remain unchanged. Observation stays stopped by user decision.</p><h2>Primary documentation</h2><ul>' + refs + '</ul><p>Recorded ' + escape(public['completed_utc']) + '. Paper only. ICT remains separate.</p></body></html>'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve()
    folder = root / 'outputs/atlas_research_pipeline_v1/feasibility/contract_provenance_v1'
    if folder.exists():
        raise FileExistsError('Preserved finite audit already exists; do not rerun unchanged work')
    synthetic = checks()
    command, paths = discover(root)
    identities = {p:sha(root/p) for p in paths}
    frozen = frozen_audit(root)
    folder.mkdir(parents=True)
    protocol = dict(registered_utc=stamp(),purpose='Post-failure documentary provenance review, designed after initial metadata discovery; not a blind strategy experiment.',
        discovery_command=command, corpus_files=len(paths), input_identities=identities,
        method='Load matching documents only for named NAS100/SPX500 contract-field projection; retain capture and explicit effective fields separately. Equal properties and duplicate bytes never establish historical applicability. No quote paths or financial outcomes are analyzed or scored.',
        limits='Bounded to matching text JSON files at most 500K under outputs/work. Original broker documents, larger files, external computers and other locations are not claimed searched. ICT, broker connections and price/fill archives are excluded.',
        source_sha256=sha(Path(__file__)), frozen_sources=frozen, synthetic_checks=synthetic,
        references=REFERENCES, financial_cases_started=0, outcome_scoring=False,
        historical_mapping_automatic_approval=False, observation_restarted=False, ict_used=False)
    write(folder/'protocol.json',protocol)
    (folder/'source_snapshot.py').write_bytes(Path(__file__).read_bytes())
    try:
        documents = []
        for name in paths:
            assert sha(root/name) == identities[name]
            value = json.loads((root/name).read_text(encoding='utf-8'))
            documents.append(dict(file=name,sha256=identities[name],nodes=extract(value)))
        summary = summarize(documents)
        duplicates = Counter(d['sha256'] for d in documents)
        required = [
            'Dated broker-origin specification or revision evidence identifying the same symbol, server/feed and applicable historical interval.',
            'Precision, minimum price increment, monetary tick value, contract size, profit currency and legal volume increments for each applicable interval.',
            'Any conversion, symbol migration or historical-feed rescaling policy, with effective timestamps and preserved document identity.',
            'A documented bridge from those specifications to the original quote archive, plus separate fee, margin and historical server-clock evidence.',
            'An independently reviewed execution model registered as a new version before any new financial replay; all original benchmarks and failures retained.',
        ]
        result = dict(completed_utc=stamp(),status='DOCUMENTARY_AUDIT_COMPLETE_APPLICABILITY_UNRESOLVED',
            corpus_scope=protocol['limits'],matching_documents=len(documents),
            exact_duplicate_content_groups=sum(c>1 for c in duplicates.values()),
            instruments=summary,required_evidence=required,references=REFERENCES,
            historical_specification_resolved=False, financial_cases=0, profit_delta=None,
            financial_PASS=False, active_paper_changed=False, observation_restarted=False,
            independent_validation=False, ict_used=False)
        write(folder/'private_document_projection.json',documents)
        write(folder/'results.json',result)
        write(folder/'public_summary.json',result)
        (folder/'report.html').write_text(render(result),encoding='utf-8')
        assert all(sha(root/p)==v for p,v in identities.items())
        assert frozen_audit(root)==frozen
        write(folder/'completed.json',dict(completed_utc=stamp(),diagnostic_completed=True,
            financial_PASS=False,financial_cases=0,historical_specification_resolved=False,
            protocol_sha256=sha(folder/'protocol.json'),results_sha256=sha(folder/'results.json'),
            input_hashes_unchanged=True,frozen_sources_unchanged=True))
        print(json.dumps(dict(status=result['status'],documents=len(documents),
            instruments={s:{k:v[k] for k in ('documents_with_properties','records_with_effective_fields','conflicting_observed_property_values')} for s,v in summary.items()},
            synthetic_checks=synthetic['passed'],financial_cases=0,observation_restarted=False)))
    except Exception as exc:
        write(folder/'failure.json',dict(failed_utc=stamp(),error=repr(exc),financial_cases=0,preserved=True))
        raise


if __name__ == '__main__':
    main()
