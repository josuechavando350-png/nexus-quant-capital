"""Fixed-cohort, same-hash, six counterbalanced transport triads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from transport import HERE, need, canonical, qty, registry, Journal, Reader, lens
from collect import get_header, canonical_check, authenticate


def source(policy, raw):
    need(hashlib.sha256(raw).hexdigest() == policy['source_file_sha256'], 'SOURCE_FILE_HASH')
    value = json.loads(raw)
    need(set(value) == {'state', 'sha256'} and registry.digest(value['state']) == value['sha256'] == policy['source_root'], 'SOURCE_ROOT')
    state = value['state']
    registry.validate(state, policy)
    return state, registry.freeze(state, state['through_block'], policy)


def run(reader, emit, policy, registration, raw):
    state, cohort = source(policy, raw)
    emit('registered', {'policy': policy, 'registration_commit': registration, 'cohort': cohort,
                        'run_started_ns': reader.started_ns})
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    canonical_check(reader, state['segments'][0]['start'], 'source-start')
    canonical_check(reader, state['checkpoint'], 'source-checkpoint')
    # No rescan/catch-up: old fixed cohort is intentional for transport, not discovery.
    emit('cohort_frozen', cohort)
    prior = state['through_block']
    for index, order in enumerate(policy['orders']):
        reader.mode = 'legacy'
        block = get_header(reader, 'latest', f'r{index}-head')
        head_row = reader.records[-1]
        need(block['number'] > prior, 'REPEATED_OR_OLD_HEAD')
        prior = block['number']
        if index == 0:
            authenticate(reader, block)
        emit('triad_started', {'round': index, 'block': block, 'order': order,
                             'unindexed_tail_blocks': block['number']-state['through_block']})
        reference = None
        for mode in order:
            reader.mode = mode
            output = reader.creation(block, cohort['addresses'], f'r{index}-{mode}-view')
            view_row = reader.records[-1]
            derived = lens.parse(block, cohort['addresses'], output, policy)
            canonical_check(reader, block, f'r{index}-{mode}-canonical')
            verified = reader.verified()
            data = {'round': index, 'mode': mode, 'block': block, 'state': derived,
                    'input_ms': (view_row['received_ns']-view_row['started_ns'])/1e6,
                    'verified_ms': (verified-view_row['started_ns'])/1e6,
                    'head_to_verified_ms': (verified-head_row['received_ns'])/1e6,
                    'header_request_to_verified_ms': (verified-head_row['started_ns'])/1e6,
                    'view_transport': view_row['transport']}
            emit('read_completed', data)
            if reference is None:
                reference = (output, derived)
            else:
                need((output, derived) == reference, 'EXACT_SAME_HASH_PARITY')
        emit('triad_completed', {'round': index, 'exact_raw_and_derived_parity': True})
    emit('completed', {'rpc_calls': reader.count, 'http_requests': len(reader.records),
                       'route_simulations': 0, 'live_broadcasts': 0, 'realized_profit': None})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--registration-commit', required=True)
    args = parser.parse_args()
    need(re.fullmatch('[0-9a-f]{40}', args.registration_commit), 'REGISTRATION_COMMIT')
    from importlib.metadata import version
    for requirement in (HERE/'requirements.txt').read_text().splitlines():
        name, expected = requirement.split('==')
        need(version(name) == expected, 'DEPENDENCY_VERSION_'+name.upper().replace('-', '_'))
    lock = json.loads((HERE/'registration-sources.json').read_text())
    for path, sha in lock['files'].items():
        need(hashlib.sha256((HERE/path).read_bytes()).hexdigest() == sha, 'REGISTERED_SOURCE_CHANGED_'+path)
    policy = json.loads((HERE/'policy.json').read_text())
    raw = (HERE.parent.parent/policy['source_path']).read_bytes()
    source(policy, raw)
    reader = Reader(args.out, policy)
    journal = Journal(reader.folder)
    (reader.folder/'source-registry.json').write_bytes(raw)
    try:
        run(reader, journal.append, policy, args.registration_commit, raw)
        status = 'completed'
    except Exception as error:
        # Exception text may include proxy URLs/credentials. Keep type and safe reason only.
        reason = str(error) if isinstance(error, ValueError) and re.fullmatch('[A-Z0-9_]+', str(error)) else type(error).__name__
        journal.append('stopped', {'exception': type(error).__name__, 'reason': reason,
                                  'rpc_calls': reader.count, 'http_requests': len(reader.records), 'realized_profit': None})
        status = 'stopped'
    finally:
        reader.transports.close()
    print(json.dumps({'status': status, 'rpc_calls': reader.count, 'http_requests': len(reader.records),
                      'elapsed_seconds': (time.monotonic_ns()-reader.started_ns)/1e9}), flush=True)
    return int(status != 'completed')


if __name__ == '__main__':
    raise SystemExit(main())
