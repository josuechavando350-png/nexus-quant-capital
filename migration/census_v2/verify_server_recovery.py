#!/usr/bin/env python3
"""Authenticate the completed portion of original-server recovery, not Census."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


D15B_SHA = 'aff472236ff5177f123e4a6ccc95d4dae5fb37833f8645984116c407c179d790'
LEGS_SHA = '51dfc4c9c3031a7bf3bb6ce019eb3a9184a1f2327f1accedcc2c6e165af91acb'
LINKS = {
    'candidate-state-transition-replay-summary.json': 'candidate_state_replay_sha256',
    'interest-only-crossing-candidate-envelope-summary.json': 'candidate_envelope_sha256',
    'pool-trigger-dual-provider-summary.json': 'pool_trigger_sha256',
    'full-block-oracle/drpc/provider-summary.json': 'full_block_oracle_summary_sha256',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def archive_member(path, expected, member):
    raw = path.read_bytes()
    require(sha(raw) == expected, 'original archive SHA-256 mismatch')
    with zipfile.ZipFile(path) as z:
        require(z.namelist().count(member) == 1, 'archive member uniqueness')
        return z.read(member)


def event_key(row):
    return row['transaction_hash'], row['log_index']


def reconcile_events(source, later):
    originals = {event_key(x): x for x in source}
    decoded = {event_key(x): x for x in later}
    require(len(originals) == len(source) == 139, 'original event cardinality/uniqueness')
    require(len(decoded) == len(later) == 139, 'later event cardinality/uniqueness')
    require(originals.keys() == decoded.keys(), 'event set differs')
    fields = {
        'transaction_hash': 'transaction_hash', 'log_index': 'log_index',
        'block_number': 'block_number', 'block_hash': 'block_hash',
        'transaction_index': 'transaction_index', 'collateral_asset': 'collateral_asset',
        'debt_asset': 'debt_asset', 'debt_to_cover': 'debt_to_cover_raw',
        'liquidated_collateral_amount': 'collateral_liquidated_raw',
        'receive_atoken': 'receive_a_token',
    }
    for key, row in originals.items():
        other = decoded[key]
        require(type(row['receive_atoken']) is bool, 'boolean required')
        for source_key, target_key in fields.items():
            require(type(row[source_key]) is type(other[target_key]) and
                    row[source_key] == other[target_key], 'event field differs: ' + source_key)
        topic = '0x' + row['user'][2:].rjust(64, '0')
        require(sha(topic.encode()) == other['borrower_identity_sha256'], 'borrower identity differs')
        require(sha(row['liquidator'].encode()) == other['liquidator_identity_sha256'], 'liquidator identity differs')
    txs = {x['transaction_hash'] for x in source}
    require(len(txs) == 127, 'transaction conservation')
    return {'event_count': len(source), 'transaction_count': len(txs),
            'event_identity_and_integer_legs_match': True,
            'borrower_and_liquidator_identities_match': True,
            'additional_winner_transactions': 0}


def verify(root, d15b, legs):
    aggregate = parse(archive_member(d15b, D15B_SHA, 'rmc015b-production-evidence.json'))
    inventory = {}
    for name, link in LINKS.items():
        raw = (root / name).read_bytes()
        require(sha(raw) == aggregate['inputs'][link], 'D15B input binding: ' + name)
        inventory[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    pool = parse((root / 'pool-trigger-dual-provider-summary.json').read_bytes())
    first = (root / 'liquidation-calls.jsonl').read_bytes()
    second = (root / 'liquidations-tenderly.jsonl').read_bytes()
    require(sha(first) == pool['liquidation_sha256'], 'liquidation ledger binding')
    require(first == second, 'source-labeled liquidation files differ')
    for name, raw in [('liquidation-calls.jsonl', first), ('liquidations-tenderly.jsonl', second)]:
        inventory[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    source = [parse(x) for x in first.splitlines()]
    later = [parse(x) for x in archive_member(legs, LEGS_SHA, 'decoded-liquidation-legs.jsonl').splitlines()]
    comparison = reconcile_events(source, later)
    for row in source:
        require(aggregate['window']['start_block'] <= row['block_number'] <= aggregate['window']['end_block'], 'event outside window')
    return {
        'schema': 'nqc-original-server-partial-recovery-v1',
        'status': 'FOUR_PINNED_INPUT_SUMMARIES_AND_139_ORIGINAL_EVENT_LEGS_VERIFIED',
        'source_device_id': '97869e36-ef95-481f-ac75-85ab90bce0e7',
        'source_root': '/root/workspace/RMC015_REPLAY_30D',
        'source_d15b_run': 37669899465,
        'source_d15b_commit': 'cb413ee9747e83be2bf5e05b8270edabf4f6e221',
        'source_d15b_archive_sha256': D15B_SHA,
        'later_integer_legs_archive_sha256': LEGS_SHA,
        'window': aggregate['window'], 'verified_files': inventory,
        'event_reconciliation': comparison,
        'recovery_archive_complete': False,
        'episode_censored_and_economic_ledgers_materialized': False,
        'whole_trigger_history_replayed': False,
        'whole_oracle_scan_replayed': False,
        'provider_infrastructure_independence_proven': False,
        'decision_time_availability_proven': False,
        'material_unknown_count': None,
        'independent_certification': False,
        'real_market_census_closed': False,
        'non_claims': ['NO_NEW_RPC_ACQUISITION', 'NO_NEW_CAPTURE_OR_PROFIT',
                       'NO_TRANSFER_OF_HISTORICAL_ZERO_UNKNOWN_CLAIM',
                       'NO_COMPLETE_ARCHIVE_HASH_VERIFICATION'],
        'verifier_sha256': sha(Path(__file__).read_bytes()),
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'd15b', 'legs', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    result = verify(args.root, args.d15b, args.legs)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write('\n')
    print(result['status'])
