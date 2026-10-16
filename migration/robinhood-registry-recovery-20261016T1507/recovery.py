"""Recover two fixed real prefixes; one gate/session/budget, tail reads only."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent/'robinhood-paced-history-20261016T1222'))
from history_acquisition import Reader, Journal, need, canonical, qty, safe_stop
from collect import get_header, canonical_check, authenticate
import capacity_registry as registry
from merge import merge
from tail import update_registry
from observe import observe


def sources(policy, raw, older_raw):
    states = []
    for prefix, payload in [('source', raw), ('older_source', older_raw)]:
        need(hashlib.sha256(payload).hexdigest() == policy[prefix+'_file_sha256'], 'SOURCE_FILE_HASH')
        value = json.loads(payload)
        need(set(value) == {'state','sha256'} and
             registry.digest(value['state']) == value['sha256'] == policy[prefix+'_root'], 'SOURCE_ROOT')
        state = value['state']
        registry.validate(state, policy)
        need(state['status'] == 'valid_prefix' and state['segments'], 'INVALID_SOURCE')
        states.append(state)
    existing, older = states
    need(older['through_block']+1 == existing['from_block'], 'RECOVERY_GAP_OR_OVERLAP')
    need(older['checkpoint'] == existing['segments'][0]['start'], 'RECOVERY_BOUNDARY_HASH')
    need(policy['rounds'] == 3, 'RECOVERY_ROUNDS')
    return existing, older


def run(reader, journal, policy, registration, raw, older_raw):
    existing, older = sources(policy, raw, older_raw)
    journal.append('registered', {'policy':policy, 'registration_commit':registration,
                   'source_root':registry.digest(existing), 'older_source_root':registry.digest(older),
                   'run_started_ns':reader.started_ns})
    path = reader.output_folder/'registry.json'
    registry.save(path, existing)
    # Preserve original bytes, not a reserialized synthetic source.
    (reader.output_folder/'older-registry.json').write_bytes(older_raw)
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    canonical_check(reader, existing['checkpoint'], 'source-checkpoint')
    canonical_check(reader, older['segments'][0]['start'], 'older-start')
    canonical_check(reader, older['checkpoint'], 'shared-boundary')
    combined = merge(older, existing, policy)
    canonical_check(reader, existing['checkpoint'], 'source-after-merge')
    registry.save(reader.output_folder/'merged-before-catchup.json', combined)
    registry.save(path, combined)
    journal.append('history_recovered', {'older_registry_sha256':registry.digest(older),
                   'merged_registry_sha256':registry.digest(combined),
                   'source_registry_sha256':registry.digest(existing)})
    reader.phase = 'catchup'
    head = get_header(reader, 'latest', 'index-head')
    anchor = get_header(reader, head['number']-policy['confirmation_buffer_blocks'], 'index-anchor')
    journal.append('catchup_started', {'anchor':anchor, 'prior_through_block':existing['through_block']})
    state = update_registry(reader, journal, policy, path, combined, anchor)
    registry.save(path, state)
    reader.phase = 'authenticate'
    authenticate(reader, anchor)
    cohort = registry.freeze(state, anchor['number'], policy)
    (reader.output_folder/'cohort.json').write_bytes(canonical(cohort))
    journal.append('cohort_frozen', cohort)
    observe(reader, journal, policy, state, anchor, cohort)


def verify_registration():
    requirements = HERE.parent/'robinhood-transport-benchmark-20261016T0821/requirements.txt'
    for line in requirements.read_text().splitlines():
        name, expected = line.split('==')
        need(version(name) == expected, 'DEPENDENCY_VERSION')
    lock = json.loads((HERE/'registration-sources.json').read_text())
    for name, digest in lock['files'].items():
        need(hashlib.sha256((HERE/name).read_bytes()).hexdigest() == digest, 'REGISTERED_SOURCE_CHANGED')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--registration-commit', required=True)
    args = parser.parse_args()
    need(re.fullmatch('[0-9a-f]{40}', args.registration_commit), 'REGISTRATION_COMMIT')
    verify_registration()
    policy = json.loads((HERE/'policy.json').read_text())
    raw = (ROOT/policy['source_path']).read_bytes()
    older_raw = (ROOT/policy['older_source_path']).read_bytes()
    sources(policy, raw, older_raw)
    reader = Reader(args.out, policy)
    journal = Journal(reader.folder)
    (reader.folder/'source-registry.json').write_bytes(raw)
    (reader.folder/'older-source-registry.json').write_bytes(older_raw)
    status = 'completed'
    try:
        run(reader, journal, policy, args.registration_commit, raw, older_raw)
    except Exception as error:
        reader.stopped = True
        safe_stop(reader, journal, error)
        status = 'stopped'
    finally:
        reader.transports.close()
    print(json.dumps({'status':status,'rpc_calls':reader.count,'http_requests':len(reader.records),
                     'elapsed_seconds':(time.monotonic_ns()-reader.started_ns)/1e9}), flush=True)
    return int(status != 'completed')


if __name__ == '__main__':
    raise SystemExit(main())
