"""Cross-check the 218-response acceptance transcript without executing the product or native producers."""
import argparse
import base64
from collections import Counter
from pathlib import Path
import sys
import zlib

from superhunter.product_batches import FIXED_SOURCE_RECEIPTS, RECEIPTS
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.product_upstream_notices import sources
from superhunter.safe_io import MAX_BYTES, canonical, read_artifact, strict_json
from superhunter.tools.catalog_session import review_queries


def observed(row):
    name = row['repository'].casefold()
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


def verify(raw, expected_hash=None):
    digest = sha(raw)
    if expected_hash is not None and digest != expected_hash:
        raise EvidenceError('transcript digest differs from the acceptance record')
    keys = review_queries()
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
    if len(rows) != 200 or any(row['id'] != n for n, row in enumerate(rows, 1)):
        raise EvidenceError('incomplete or disordered acceptance matrix')
    actual_roles, actual_sources, cumulative_roles = Counter(), Counter(), Counter()
    credits = []
    for official, summary in zip(sources(), rows, strict=True):
        name, number = official['repository'], official['id']
        row = report[name]
        audited = row['source_inventory']
        if ((row['repository'], row['catalog_id'], audited['revision'], audited['tree']) !=
                (name, number, official['revision'], summary['tree']) or
                (summary['repository'], summary['id'], summary['commit']) != (name, number, official['revision'])):
            raise EvidenceError('matrix and source revisions disagree')
        role, receipt = observed(row)
        previous = history.get(number)
        cumulative = previous['role'] if previous else role
        source = ('complete' if audited['contents'] is not None else
                  'excerpt' if number in (179, 191) and row.get('owned_source_receipt') else 'metadata')
        if ((source, role, cumulative) != (summary['source'], summary['session'], summary['role']) or
                summary['historical_line_sha256'] != (previous['line_sha256'] if previous else None)):
            raise EvidenceError('matrix status differs from the original evidence')
        actual_sources[source] += 1
        actual_roles[role] += 1
        cumulative_roles[cumulative] += 1
        if summary['source'] == 'complete':
            if audited['contents'] is None:
                raise EvidenceError('missing checkout evidence')
        else:
            if row['recursive_tree_inventory']['root'] != summary['tree'] or audited['contents'] is not None:
                raise EvidenceError('missing or inconsistent remote tree evidence')
        notice = audited.get('resolved_notice_scan') or audited['notice_scan']
        if summary['license']['effective_text_sha256'] != notice['sha256']:
            raise EvidenceError('license evidence digest differs')
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
    counts = {'catalog': len(rows), 'sources': dict(actual_sources), 'verified_notices': len(rows),
              'session': len(credits), 'functional': 200 - cumulative_roles['pending'],
              'pending': cumulative_roles['pending'], 'executables': actual_roles['executable'],
              'reference_data': actual_roles['reference_data']}
    if ((counts['session'], counts['functional'], counts['sources'], counts['pending']) !=
            (matrix['end_to_end'], matrix['functional'], matrix['sources'], matrix['pending'])):
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
    keys = review_queries()
    cases = [
        ('inflated_count', 'integration-matrix', ('end_to_end',), 200, 'claimed totals'),
        ('unsupported_credit', 'integration-matrix', ('rows', 2, 'session'), 'executable', 'matrix status'),
        ('replaced_historical_digest', 'integration-matrix', ('rows', 24, 'historical_line_sha256'), '0'*64,
         'matrix status'),
        ('changed_native_result', 'PyCQA/bandit', ('owned_source_receipt', 'sha256'), '0'*64, 'fixed product result'),
        ('changed_license', 'integration-matrix', ('rows', 0, 'license', 'effective_text_sha256'), '0'*64,
         'license evidence'),
        ('changed_git_tree', 'integration-matrix', ('rows', 3, 'tree'), '0'*40, 'source revisions')]
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
    parser.add_argument('--expect-sha256', help='trusted digest for a specific, published run')
    args = parser.parse_args()
    raw = read_artifact(args.transcript.parent, args.transcript.name)
    if args.archive:
        raw = unpack(raw)
    result = verify(raw, args.expect_sha256)
    if args.check_controls:
        result['rejected_controls'] = negative_controls(raw)
    sys.stdout.buffer.write(canonical(result))


if __name__ == '__main__':
    main()
