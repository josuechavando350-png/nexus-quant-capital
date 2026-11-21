"""Cross-check the 218-response acceptance transcript without executing the product or native producers."""
import argparse
import base64
from collections import Counter
from pathlib import Path
import sys
import zlib

from superhunter.product_batches import FIXED_SOURCE_RECEIPTS, RECEIPTS
from superhunter.product_matrix import published_excerpts
from superhunter.product_reasoning import EvidenceError
from superhunter.product_source_audit import SNAPSHOT, SNAPSHOT_SHA
from superhunter.product_review import ROOT, sha
from superhunter.product_upstream_notices import sources
from superhunter.safe_io import MAX_BYTES, canonical, read_artifact, strict_json
from superhunter.tools.catalog_session import review_queries


def observed(row):
    name = row['repository'].casefold()
    if 'component_control_receipt' in row:
        from superhunter.product_component_controls import role_for
        return role_for(row)
    if name in FIXED_SOURCE_RECEIPTS:
        role, key, expected = FIXED_SOURCE_RECEIPTS[name]
        if key in row and row[key] != expected:
            raise EvidenceError('fixed product result changed')
    elif name in RECEIPTS:
        role, key = 'executable', RECEIPTS[name]
    elif name in ('ethereum/eips', 'ethereum/execution-specs'):
        role, key = 'reference_data', 'census_header_reference'
    elif name in ('owasp/asvs', 'owasp/cheatsheetseries', 'in-toto/in-toto'):
        supply = row.get('supply_role') or {}
        if supply and (supply.get('role') == 'executable' or row.get('controls')):
            return supply['role'], supply['artifact']
        return 'pending', None
    else:
        return 'pending', None
    return (role, key) if row.get(key) else ('pending', None)


def response_keys(raw):
    keys = review_queries()
    extra = len(raw.splitlines()) - len(keys)
    if extra in (2, 3):
        keys.extend(['portable-source-proof', 'go-header-digest'])
    if extra in (1, 3):
        keys.append('component-controls')
    return keys


def verify(raw, expected_hash=None):
    digest = sha(raw)
    if expected_hash is not None and digest != expected_hash:
        raise EvidenceError('transcript digest differs from the acceptance record')
    keys = response_keys(raw)
    lines = raw.splitlines()
    if len(lines) != len(keys):
        raise EvidenceError('acceptance transcript has missing or extra responses')
    report = {}
    for key, line in zip(keys, lines, strict=True):
        value = strict_json(b'{"response":' + line + b'}')['response']
        expected = list if key == 'notice-overlaps:upstream-002-license.txt' else dict
        if not isinstance(value, expected):
            raise EvidenceError('unexpected response type at ' + key)
        report[key] = value
    archive = read_artifact(ROOT, 'superhunter/product_supply/coverage-d94b58f.json')
    if sha(archive) != 'b47f69c24ee583c5e8ef61954439b56818bccf6e3fa35a60bf099381d10bc1bd':
        raise EvidenceError('historical index changed')
    history = {doc['catalog_id']: doc for doc in strict_json(archive)['receipts']}
    matrix = report['integration-matrix']
    rows = matrix['rows']
    if 'component-controls' in report and 'published_excerpts' not in matrix:
        raise EvidenceError('component profile is missing its published excerpt inventory')
    excerpts = {}
    if 'published_excerpts' in matrix:
        actual = published_excerpts()
        if matrix['published_excerpts'] != actual:
            raise EvidenceError('published excerpt inventory differs from its source bytes')
        excerpts = {r['id']: r for r in actual}
    snapshot = read_artifact(ROOT, SNAPSHOT)
    if sha(snapshot) != SNAPSHOT_SHA:
        raise EvidenceError('source audit differs from the reviewed snapshot')
    acquired = {r['id']: r for r in strict_json(snapshot)['entries']}
    if len(rows) != 200 or any(row['id'] != n for n, row in enumerate(rows, 1)):
        raise EvidenceError('incomplete or disordered acceptance matrix')
    actual_roles, actual_sources, cumulative_roles, pending_sources = Counter(), Counter(), Counter(), Counter()
    credits = []
    for official, summary in zip(sources(), rows, strict=True):
        name, number = official['repository'], official['id']
        row = report[name]
        audited = row['source_inventory']
        if ((row['repository'], row['catalog_id'], audited['revision'], audited['tree']) !=
                (name, number, official['revision'], summary['tree']) or
                (summary['repository'], summary['id'], summary['commit']) != (name, number, official['revision'])):
            raise EvidenceError('matrix and source revisions disagree')
        fixed = acquired[number]
        if any(audited.get(k) != fixed.get(k) for k in ('id', 'repository', 'revision', 'tree', 'contents', 'evidence')):
            raise EvidenceError('source revisions or checkout inventory differ from the pinned audit')
        role, receipt = observed(row)
        previous = history.get(number)
        cumulative = previous['role'] if previous else role
        if audited['contents'] is not None:
            source = 'complete'
        elif excerpts:
            excerpt = excerpts.get(number)
            if excerpt and (name, audited['revision'], audited['tree']) != (
                    excerpt['repository'], excerpt['revision'], excerpt['tree']):
                raise EvidenceError('published excerpt belongs to a different Git source')
            source = 'excerpt' if excerpt else 'metadata'
        else:
            # The archived PR 115/117 format linked its two extract proofs to the owned review.
            source = 'excerpt' if number in (179, 191) and row.get('owned_source_receipt') else 'metadata'
        if ((source, role, cumulative) != (summary['source'], summary['session'], summary['role']) or
                summary['historical_line_sha256'] != (previous['line_sha256'] if previous else None)):
            raise EvidenceError('matrix status differs from the original evidence')
        actual_sources[source] += 1
        actual_roles[role] += 1
        cumulative_roles[cumulative] += 1
        if cumulative == 'pending':
            pending_sources[source] += 1
        if summary['commercial_review'] != 'pending':
            raise EvidenceError('unsupported commercial license decision')
        if source == 'complete':
            content = fixed['contents']
            scope = 'checked_out_contents'
            nested = len(content['nested_gitlinks'])
            manifests = sum(content['manifest_counts_by_filename'].values())
        else:
            remote = row['recursive_tree_inventory']
            if (remote['root'], remote['commit'], remote['repository']) != (fixed['tree'], fixed['revision'], name):
                raise EvidenceError('missing or inconsistent remote tree evidence')
            scope = 'recursive_tree_objects'
            nested = remote['nested_gitlinks']
            manifests = sum(remote['manifest_counts'].values())
        if (summary['verification_scope'], summary['nested_gitlinks'], summary['recognized_manifest_paths'],
                summary['nature']) != (scope, nested, manifests, audited['nature']):
            raise EvidenceError('source scope or inventory summary differs from inspected evidence')
        notice = audited.get('resolved_notice_scan') or audited['notice_scan']
        if (summary['license'] != {'document': audited['notice_path'],
                'detected_expression': notice['detected_expression'], 'effective_text_sha256': notice['sha256']} or
                notice != (fixed.get('resolved_notice_scan') or fixed['notice_scan'])):
            raise EvidenceError('license evidence digest or description differs')
        if summary['session'] == 'pending':
            if summary['session_evidence_sha256'] is not None:
                raise EvidenceError('pending identity attributed a session result')
            continue
        if receipt != summary['receipt']:
            raise EvidenceError('live receipt points to the wrong producer field')
        if receipt in ('supply.link', 'asvs.csv', 'asvs-guides.md'):
            evidence = {k: row[k] for k in ('supply_role', 'controls') if k in row}
        else:
            evidence = row[receipt]
        if sha(canonical(evidence)) != summary['session_evidence_sha256']:
            raise EvidenceError('session credit differs from its producer bytes')
        credits.append([number, name, summary['session'], receipt])
    live = {name for name in (r['repository'] for r in rows) if 'component_control_receipt' in report[name]}
    if 'component-controls' in report:
        from superhunter.product_component_controls import DOMAINS, contracts, reconcile_digest
        controls = report['component-controls']
        names = controls['requested']
        failures = controls['blocked']
        if (not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names)
                or len(names) != len(set(names)) or set(names) - DOMAINS.keys() or not isinstance(failures, dict)
                or not all(isinstance(cause, str) and cause.strip() for cause in failures.values())
                or set(failures) - set(names)):
            raise EvidenceError('component selection or blocked domains differ')
        blocked = set(failures)
        expected = {name for name, rule in contracts().items() if rule['domain'] in set(names) - blocked}
        if set(controls['observations']) != expected or live != expected:
            raise EvidenceError('component evidence does not cover the selected producers')
        if controls['digest_corroboration'] != reconcile_digest(controls['observations'], report.get('go-header-digest')):
            raise EvidenceError('cross-domain source corroboration differs from original observations')
        for name, observation in controls['observations'].items():
            claim = report[name]['component_control_receipt']
            if (observation.get('revision') != claim['revision'] or
                    sha(canonical(observation)) != claim['result_sha256']):
                raise EvidenceError('individual component result differs from the shared evidence')
    elif live:
        raise EvidenceError('component receipts have no shared evidence')
    if 'portable-source-proof' in report:
        source_report = report['portable-source-proof']
        records = [report[r['repository']]['offline_source_proof'] for r in rows if r['source'] != 'complete']
        if (source_report['commits'] != len(records) or source_report['receipt_sha256'] != sha(canonical(records)) or
                source_report['root_declarations'] != sum(len(r['manifest_blobs']) for r in records)):
            raise EvidenceError('portable Git evidence differs from product rows')
        go = report['securego/gosec']['go_source_receipt']
        if go['report_sha256'] != sha(canonical(report['go-header-digest'])):
            raise EvidenceError('Go source audit report differs from the producer receipt')
    counts = {'catalog': len(rows), 'sources': dict(actual_sources), 'verified_notices': len(rows),
              'session': len(credits), 'functional': 200 - cumulative_roles['pending'],
              'pending': cumulative_roles['pending'], 'executables': actual_roles['executable'],
              'reference_data': actual_roles['reference_data']}
    expected = {'catalog': len(rows), 'sources': dict(actual_sources), 'pending_by_source': dict(pending_sources),
                'functional': counts['functional'], 'end_to_end': counts['session'], 'pending': counts['pending'],
                'executable': cumulative_roles['executable'], 'references': cumulative_roles['reference_data'],
                'notices_reviewed': len(rows), 'verified_trees': len(acquired), 'commercial_reviews_completed': 0,
                'remote_roots': len(rows)-actual_sources['complete']}
    if (any(canonical(matrix.get(k)) != canonical(v) for k, v in expected.items()) or
            report['root-declarations']['remote_roots_verified'] != expected['remote_roots']):
        raise EvidenceError('claimed totals differ from independently counted rows')
    return {'transcript_sha256': digest, 'credits_sha256': sha(canonical(credits)),
            'responses': len(keys), **counts}


def unpack(raw):
    archive = strict_json(raw)
    if archive.get('format') != 'gzip-base64-jsonl-v1' or type(archive.get('raw_size')) is not int:
        raise EvidenceError('unrecognized acceptance archive')
    size = archive['raw_size']
    if not 0 < size <= MAX_BYTES:
        raise EvidenceError('unbounded acceptance archive')
    inflater = zlib.decompressobj(wbits=31)
    decoded = inflater.decompress(base64.b64decode(archive['gzip_base64'], validate=True), size + 1)
    if (len(decoded) != size or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail or
            sha(decoded) != archive['raw_sha256']):
        raise EvidenceError('acceptance archive content differs')
    return decoded


def negative_controls(raw):
    keys = response_keys(raw)
    lines = raw.splitlines()
    matrix = strict_json(lines[keys.index('integration-matrix')])
    old_role = matrix['rows'][2]['session']
    cases = [
        ('inflated_count', 'integration-matrix', ('end_to_end',), len(matrix['rows'])+1, 'claimed totals'),
        ('unsupported_credit', 'integration-matrix', ('rows', 2, 'session'),
         'executable' if old_role == 'pending' else 'pending', 'matrix status'),
        ('replaced_historical_digest', 'integration-matrix', ('rows', 24, 'historical_line_sha256'), '0'*64,
         'matrix status'),
        ('changed_native_result', 'PyCQA/bandit', ('owned_source_receipt', 'sha256'), '0'*64, 'fixed product result'),
        ('changed_license', 'integration-matrix', ('rows', 0, 'license', 'effective_text_sha256'), '0'*64,
         'license evidence'),
        ('changed_git_tree', 'integration-matrix', ('rows', 3, 'tree'), '0'*40, 'source revisions')]
    if 'component-controls' in keys:
        controls = strict_json(lines[keys.index('component-controls')])
        observed = controls['observations']
        cases.extend([
            ('erased_domain_selection', 'component-controls', ('requested',), [], 'component selection'),
            ('erased_shared_results', 'component-controls', ('observations',), {} if observed else {'unexpected': {}},
             'component evidence'),
            ('erased_corroboration', 'component-controls', ('digest_corroboration',),
             {} if controls['digest_corroboration'] else {'unexpected': True}, 'cross-domain'),
            ('changed_role_totals', 'integration-matrix', ('references',), -1, 'claimed totals'),
            ('changed_source_distribution', 'integration-matrix', ('pending_by_source',), {'metadata': -1}, 'claimed totals'),
            ('changed_commercial_total', 'integration-matrix', ('commercial_reviews_completed',), 1, 'claimed totals'),
            ('erased_excerpt_inventory', 'integration-matrix', ('published_excerpts',), [], 'excerpt inventory')])
        if observed:
            name = sorted(observed)[0]
            cases.append(('changed_group_result', 'component-controls', ('observations', name, 'operation'),
                          'unchecked', 'individual component result'))
    rejected = {}
    for name, key, path, replacement, reason in cases:
        lines = raw.splitlines()
        position = keys.index(key)
        record = strict_json(lines[position])
        node = record
        for member in path[:-1]:
            node = node[member]
        node[path[-1]] = replacement
        lines[position] = canonical(record).rstrip(b'\n')
        try:
            verify(b'\n'.join(lines) + b'\n')
        except EvidenceError as exc:
            if reason not in str(exc):
                raise
            rejected[name] = str(exc)
        else:
            raise EvidenceError('negative control accepted: ' + name)
    return rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('transcript', type=Path)
    parser.add_argument('--check-controls', action='store_true', help='run six independent corruptions in memory')
    parser.add_argument('--archive', action='store_true', help='read a published gzip/base64 evidence envelope')
    parser.add_argument('--require-complete-controls', action='store_true', help='require all defensive domains and zero blocked producers')
    parser.add_argument('--expect-sha256', help='trusted digest for a specific, published run')
    args = parser.parse_args()
    raw = read_artifact(args.transcript.parent, args.transcript.name)
    if args.archive:
        raw = unpack(raw)
    result = verify(raw, args.expect_sha256)
    if args.require_complete_controls:
        from superhunter.product_component_controls import DOMAINS
        session = strict_json(raw.splitlines()[-1])
        if (set(session.get('requested', [])) != DOMAINS.keys() or session.get('blocked') != {}
                or not session.get('digest_corroboration')):
            raise EvidenceError('incomplete defensive control session')
    if args.check_controls:
        result['rejected_controls'] = negative_controls(raw)
    sys.stdout.buffer.write(canonical(result))


if __name__ == '__main__':
    main()
