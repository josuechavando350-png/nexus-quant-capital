"""Independently verify current native controls or an explicit immutable checkpoint.

This reads evidence only; reviewing an archive does not rerun its producers.
"""
import argparse
import copy
from pathlib import Path
import sys

from superhunter.product_native_capabilities import HISTORICAL_CONTRACTS, contracts
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json
from superhunter.tools import verify_review_115 as prior


def verify(raw, expected_hash=None, *, contract_version=None):
    result = prior.verify(raw, expected_hash, native_contract_version=contract_version)
    keys = prior.response_keys(raw)
    if 'native-capabilities' not in keys:
        raise EvidenceError('native session has missing or extra responses')
    lines = raw.splitlines()
    report = strict_json(lines[keys.index('native-capabilities')])
    expected = contracts(contract_version)
    if (set(report['groups']) != set(expected) or report.get('blocked_groups')
            or result['sources'] != {'complete': 200}):
        raise EvidenceError('native session requires all reviewed groups and direct source records')
    inventory = strict_json(lines[keys.index('source-inventory')])
    return {**result, 'native_groups': sorted(report['groups']),
            'new_native_participations': report['functional_participations'],
            'original_vulnerabilities_confirmed': 0,
            'source_inventory_sha256': inventory['snapshot_sha256']}


def controls(raw, *, contract_version=None):
    """Refute altered evidence only after the original passes the selected policy."""
    verify(raw, contract_version=contract_version)
    keys = prior.response_keys(raw)
    values = [strict_json(b'{"response":' + line + b'}')['response'] for line in raw.splitlines()]
    expected = contracts(contract_version)
    group = sorted(expected)[0]
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
            verify(candidate, contract_version=contract_version)
        except (EvidenceError, ValueError, KeyError, TypeError):
            rejected += 1
        else:
            raise EvidenceError('altered native acceptance evidence was admitted')
    return rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('transcript', type=Path)
    parser.add_argument('--expect-sha256')
    parser.add_argument('--contract-version', type=int, choices=sorted(k for k in HISTORICAL_CONTRACTS if type(k) is int),
                        help='verify an immutable historical policy instead of the current registry')
    parser.add_argument('--archive', action='store_true', help='read the bounded acceptance archive')
    parser.add_argument('--check-controls', action='store_true', help='reject eight altered evidence copies')
    args = parser.parse_args()
    raw = read_artifact(args.transcript.parent, args.transcript.name)
    if args.archive:
        raw = prior.unpack(raw)
    result = verify(raw, args.expect_sha256, contract_version=args.contract_version)
    if args.check_controls:
        result['altered_evidence_rejected'] = controls(raw, contract_version=args.contract_version)
    sys.stdout.buffer.write(canonical(result))


if __name__ == '__main__':
    main()
