"""Independently count a complete native session and bind each credit to reviewed producer bytes.

This verifier reads evidence only. It does not rerun producers or imply a new
native execution when reviewing an archived transcript.
"""
import argparse
import copy
from pathlib import Path
import sys

from superhunter.product_native_capabilities import contracts
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.product_source_audit import SNAPSHOT, SNAPSHOT_SHA
from superhunter.safe_io import canonical, read_artifact, strict_json
from superhunter.tools.catalog_session import review_queries
from superhunter.tools import verify_review_115 as prior


def queries():
    return review_queries() + ['portable-source-proof', 'go-header-digest', 'native-capabilities']


def verify(raw, expected_hash=None):
    keys = queries()
    lines = raw.splitlines()
    if len(lines) != len(keys):
        raise EvidenceError('native session has missing or extra responses')
    report = {key: strict_json(b'{"response":' + line + b'}')['response']
              for key, line in zip(keys, lines, strict=True)}
    expected = contracts()
    native = report['native-capabilities']
    if (set(native.get('groups', {})) != set(expected) or
            native.get('original_vulnerabilities_confirmed') != 0 or
            native.get('scope') != 'fixed_owned_controls_and_pinned_local_inputs'):
        raise EvidenceError('native session group membership or scope differs')
    bindings = {}
    for group, contract in expected.items():
        if sha(canonical(native['groups'][group])) != contract['report_sha256']:
            raise EvidenceError('native session producer bytes differ from reviewed controls')
        for repository, role in contract['repositories'].items():
            wanted = {'query': 'native-capabilities', 'group': group, 'repository': repository,
                      'role': role, 'report_sha256': contract['report_sha256']}
            if report[repository].get('native_capability_receipt') != wanted:
                raise EvidenceError('native session repository has no matching producer receipt')
            bindings[repository.casefold()] = (role, wanted)
    if (native.get('repositories') != sorted(bindings) or
            native.get('functional_participations') != len(bindings)):
        raise EvidenceError('native session totals differ from producer identities')
    source = read_artifact(ROOT, SNAPSHOT)
    if sha(source) != SNAPSHOT_SHA:
        raise EvidenceError('native session source inventory pin changed')
    inventory = strict_json(source)
    if inventory['checkouts'] != 200 or inventory['remote_commit_records'] != 0:
        raise EvidenceError('native session requires all 200 direct source checkouts')
    for entry in inventory['entries']:
        row = report[entry['repository']]['source_inventory']
        if any(row.get(key) != value for key, value in entry.items()):
            raise EvidenceError('native session source record differs from the reviewed tree inventory')

    def observed(row):
        name = row['repository'].casefold()
        if name in bindings:
            role, wanted = bindings[name]
            if row.get('native_capability_receipt') != wanted:
                raise EvidenceError('native session receipt differs')
            return role, 'native_capability_receipt'
        if 'native_capability_receipt' in row:
            raise EvidenceError('unregistered native session receipt')
        return prior.observed(row)

    result = prior.verify(raw, expected_hash, queries=keys, observe=observed)
    if result['sources'] != {'complete': 200}:
        raise EvidenceError('native session source totals differ')
    return {**result, 'native_groups': sorted(expected), 'new_native_participations': len(bindings),
            'original_vulnerabilities_confirmed': 0,
            'source_inventory_sha256': SNAPSHOT_SHA}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('transcript', type=Path)
    parser.add_argument('--expect-sha256')
    parser.add_argument('--archive', action='store_true', help='read the bounded acceptance archive')
    parser.add_argument('--check-controls', action='store_true', help='reject eight altered copies of the supplied evidence')
    args = parser.parse_args()
    raw = read_artifact(args.transcript.parent, args.transcript.name)
    if args.archive:
        raw = prior.unpack(raw)
    result = verify(raw, args.expect_sha256)
    if args.check_controls:
        result['altered_evidence_rejected'] = controls(raw)
    sys.stdout.buffer.write(canonical(result))


def controls(raw):
    """Refute internally resealed claims without relying on a transcript digest alone."""
    keys = queries()
    values = [strict_json(b'{"response":' + line + b'}')['response'] for line in raw.splitlines()]
    expected = contracts()
    group = sorted(expected)[0]
    repository = sorted(expected[group]['repositories'])[0]
    bad = []
    def changed(query, update):
        rows = copy.deepcopy(values)
        update(rows[keys.index(query)])
        bad.append(b''.join(canonical(row) for row in rows))
    changed('integration-matrix', lambda row: row.update(functional=200))
    changed('native-capabilities', lambda row: row['groups'][group].update(invented_success=True))
    changed(repository, lambda row: row['native_capability_receipt'].update(report_sha256='0'*64))
    changed(repository, lambda row: row['source_inventory'].update(tree='0'*40))
    changed('native-capabilities', lambda row: row.update(original_vulnerabilities_confirmed=1))
    changed('native-capabilities', lambda row: row['groups'].pop(group))
    changed('go-header-digest', lambda row: row.update(invented_result=True))
    bad.append(b'\n'.join(raw.splitlines()[:-1]) + b'\n')
    rejected = 0
    for candidate in bad:
        try:
            verify(candidate)
        except (EvidenceError, ValueError, KeyError, TypeError):
            rejected += 1
        else:
            raise EvidenceError('altered native acceptance evidence was admitted')
    return rejected


if __name__ == '__main__':
    main()
