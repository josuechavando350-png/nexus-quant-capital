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
from superhunter.safe_io import canonical, read_artifact, strict_json
from superhunter.tools import verify_review_115 as prior


def verify(raw, expected_hash=None):
    result = prior.verify(raw, expected_hash)
    keys = prior.response_keys(raw)
    if 'native-capabilities' not in keys:
        raise EvidenceError('native session has missing or extra responses')
    lines = raw.splitlines()
    report = strict_json(lines[keys.index('native-capabilities')])
    # This command preserves the historical PR 119 acceptance scope.
    if (result['transcript_sha256'] != prior.NATIVE_SESSION_70
            or set(report['groups']) != set(contracts(version=70)) or report.get('blocked_groups')
            or result['sources'] != {'complete': 200}):
        raise EvidenceError('native session requires all reviewed groups and direct source records')
    inventory = strict_json(lines[keys.index('source-inventory')])
    return {**result, 'native_groups': sorted(report['groups']),
            'new_native_participations': report['functional_participations'],
            'original_vulnerabilities_confirmed': 0,
            'source_inventory_sha256': inventory['snapshot_sha256']}


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
    keys = prior.response_keys(raw)
    values = [strict_json(b'{"response":' + line + b'}')['response'] for line in raw.splitlines()]
    expected = contracts(version=70)
    active = values[keys.index('native-capabilities')]['groups']
    group = sorted(active)[0]
    repository = sorted(expected[group]['repositories'])[0]
    bad = []
    def changed(query, update):
        rows = copy.deepcopy(values)
        update(rows[keys.index(query)])
        bad.append(b''.join(canonical(row) for row in rows))
    changed('integration-matrix', lambda row: row.update(functional=201))
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
