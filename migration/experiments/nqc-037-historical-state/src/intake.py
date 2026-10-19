"""Minimal read-only historical acquisition and identical offline export intake.

`plan` and `verify` never use the network. `collect` requires NQC_ARCHIVE_RPC.
Eight calls at most; no retries, redirects, fallback block tags or write methods.
The accepted package is still not a complete Nitro witness or exact tx1 prestate.
"""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from verify import (ROOT, CHAIN_ID, PARENT_HASH, PARENT_NUMBER, PARENT_ROOT,
                    ANCHOR_HASH, ANCHOR_NUMBER, TARGET_NUMBER, PRIORITY_ADDRESS,
                    PRIORITY_SLOTS, ARBOS_ADDRESS, ARBOS_FIELDS, HISTORY_ADDRESS,
                    HISTORY_WINDOW, EMPTY_CODE_HASH, require, data_hex, quantity,
                    slot, arbos_slot, read_json, validate_header, account_proof,
                    history_bridge, closed_gates, no_duplicate_keys, ValidationError)


def plan():
    parent = {'blockHash': PARENT_HASH, 'requireCanonical': True}
    anchor = {'blockHash': ANCHOR_HASH, 'requireCanonical': True}
    operations = [
        ('chain', 'eth_chainId', []),
        ('parent', 'eth_getBlockByHash', [PARENT_HASH, False]),
        ('priority_proof', 'eth_getProof', [PRIORITY_ADDRESS, [slot(s) for s in PRIORITY_SLOTS], parent]),
        ('priority_code', 'eth_getCode', [PRIORITY_ADDRESS, parent]),
        ('arbos_proof', 'eth_getProof', [ARBOS_ADDRESS, [arbos_slot(s) for s in ARBOS_FIELDS.values()], parent]),
        ('anchor', 'eth_getBlockByHash', [ANCHOR_HASH, False]),
        ('history_proof', 'eth_getProof', [HISTORY_ADDRESS,
            [slot(s % HISTORY_WINDOW) for s in [TARGET_NUMBER, PARENT_NUMBER]], anchor]),
        ('history_code', 'eth_getCode', [HISTORY_ADDRESS, anchor]),
    ]
    return [{'purpose': purpose, 'request': {'jsonrpc': '2.0', 'id': i,
            'method': method, 'params': params}} for i, (purpose, method, params) in enumerate(operations, 1)]


def envelope(response, request_id):
    require(isinstance(response, dict) and response.get('jsonrpc') == '2.0', 'Invalid RPC envelope')
    require(type(response.get('id')) is int and response['id'] == request_id, 'RPC id mismatch')
    if 'error' in response:
        err = response['error']
        code = err.get('code') if isinstance(err, dict) else None
        raise ValidationError('RPC error code ' + (str(code) if type(code) is int else 'unknown'))
    require('result' in response and response['result'] is not None, 'Missing RPC result')
    return response['result']


def validate_step(operation, response, state):
    result = envelope(response, operation['request']['id'])
    purpose = operation['purpose']
    if purpose == 'chain':
        require(quantity(result) == CHAIN_ID, 'Wrong chain')
    elif purpose == 'parent':
        validate_header(result, PARENT_HASH, PARENT_NUMBER)
        require(result['stateRoot'] == PARENT_ROOT, 'Parent state root mismatch')
    elif purpose == 'priority_proof':
        checked = account_proof(PARENT_ROOT, PRIORITY_ADDRESS, [slot(s) for s in PRIORITY_SLOTS], result)
        require(checked['code_hash'] != '0x' + EMPTY_CODE_HASH.hex(), 'Priority contract has no code')
        state['priority_checked'] = checked
    elif purpose == 'priority_code':
        account_proof(PARENT_ROOT, PRIORITY_ADDRESS, [slot(s) for s in PRIORITY_SLOTS],
                      state['priority_proof'], result)
    elif purpose == 'arbos_proof':
        checked = account_proof(PARENT_ROOT, ARBOS_ADDRESS, [arbos_slot(s) for s in ARBOS_FIELDS.values()], result)
        values = {name: int(checked['storage_values'][arbos_slot(s)]) for name, s in ARBOS_FIELDS.items()}
        require(values['version'] == 61 and values['chain_id'] == CHAIN_ID and values['genesis_block_number'] == 0,
                'ArbOS context differs from captured context')
        require(all(values[k] < 2**64 for k in ['version', 'upgrade_version', 'upgrade_timestamp', 'genesis_block_number']),
                'ArbOS uint64 overflow')
        state['arbos_checked'] = values
    elif purpose == 'anchor':
        validate_header(result, ANCHOR_HASH, ANCHOR_NUMBER)
        observed = read_json(ROOT / 'inputs/l1-observations.json')['confirmation']
        require(result['extraData'].lower() == observed['confirmed_send_root_field'], 'Anchor send root mismatch')
    elif purpose == 'history_proof':
        account_proof(state['anchor']['stateRoot'], HISTORY_ADDRESS,
                      [slot(s % HISTORY_WINDOW) for s in [TARGET_NUMBER, PARENT_NUMBER]], result)
    elif purpose == 'history_code':
        target = read_json(ROOT / 'inputs/target-header.json')['result']
        state['history_checked'] = history_bridge(state['anchor'], target, state['parent'],
                                                   state['history_proof'], result)
    else:
        raise ValidationError('Unknown acquisition purpose')
    state[purpose] = result


def result_report(state):
    expected = read_json(ROOT / 'inputs/TARGET.json')['priority_slots']
    comparisons = []
    for row in expected:
        actual = int(state['priority_checked']['storage_values'][row['slot']])
        comparisons.append({'slot': row['slot'], 'proven_parent_value': slot(actual),
                            'event_derived_value': row['expected_event_derived_value'],
                            'equal_to_event_derived_value': actual == int(row['expected_event_derived_value'], 16)})
    return {'status': 'PARTIAL_STATE_PACKAGE_VERIFIED_RELATIVE_TO_OBSERVED_ROOTS',
            'scope': 'parent poststate and conditional history link; not txIndex=1 prestate',
            'requests_verified': 8, 'parent_priority_slots_verified_relative_to_captured_root': 11,
            'parent_priority_code_verified': True, 'arbos_parent_fields': state['arbos_checked'],
            'event_comparisons': comparisons, 'history_link': state['history_checked'],
            'gates': closed_gates()}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValidationError('Redirect refused')


class Transport:
    def __init__(self, endpoint):
        uri = urllib.parse.urlsplit(endpoint)
        require(uri.scheme == 'https' or (uri.scheme == 'http' and uri.hostname in {'localhost', '127.0.0.1', '::1'}),
                'HTTPS or loopback HTTP required')
        require(uri.hostname and not uri.username and not uri.password and not uri.fragment, 'Invalid endpoint')
        self.endpoint = endpoint
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, request):
        # Exact fixed requests, not just an allowlist of method names.
        require(any(request == row['request'] for row in plan()), 'Unapproved request')
        req = urllib.request.Request(self.endpoint, data=json.dumps(request).encode(),
                                     headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            raise ValidationError('HTTP ' + str(exc.code) + '; no retry') from None
        except (urllib.error.URLError, TimeoutError):
            raise ValidationError('Transport unavailable; no retry') from None
        require(len(raw) <= 16 * 1024 * 1024, 'Response byte limit')
        parsed = json.loads(raw, object_pairs_hook=no_duplicate_keys)
        envelope(parsed, request['id'])  # Do not persist provider error text or endpoint.
        return parsed


def execute(fetch, out):
    require(not out.exists(), 'Fresh output directory required')
    out.mkdir(parents=True)
    save(out / 'REQUESTS.json', plan())
    state = {}
    completed = 0
    operation = None
    try:
        for operation in plan():
            response = fetch(operation)
            envelope(response, operation['request']['id'])
            # Preserve received successful envelopes even if their proof is rejected.
            # Presence of this file is not acceptance; RESULTS/FAILURE is authoritative.
            save(out / f"{operation['request']['id']:02d}-{operation['purpose']}.json", response)
            validate_step(operation, response, state)
            completed += 1
        report = result_report(state)
        save(out / 'RESULTS.json', report)
        return report
    except Exception as exc:
        # Never write third-party error messages, URLs, credentials, or a traceback.
        report = {'status': 'BLOCKED_OR_REJECTED', 'responses_verified': completed,
                  'failed_purpose': operation['purpose'] if operation else None,
                  'error_type': type(exc).__name__,
                  'reason': str(exc) if isinstance(exc, ValidationError) else 'Input, proof or transport rejected; see failed_purpose',
                  'gates': closed_gates()}
        save(out / 'FAILURE.json', report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['plan', 'verify', 'collect'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    if args.mode == 'plan':
        require(not args.out.exists(), 'Fresh output file required')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        save(args.out, plan())
        print('OFFLINE_PLAN_ONLY: 8 requests; no network access')
        return
    if args.mode == 'verify':
        require(args.bundle is not None and args.bundle.is_dir(), 'Export directory required')
        def fetch(operation):
            return read_json(args.bundle / f"{operation['request']['id']:02d}-{operation['purpose']}.json")
    else:
        endpoint = os.environ.get('NQC_ARCHIVE_RPC', '')
        require(endpoint, 'NQC_ARCHIVE_RPC is not configured')
        transport = Transport(endpoint)
        def fetch(operation):
            return transport(operation['request'])
    report = execute(fetch, args.out)
    print(json.dumps({'status': report['status'], 'commercial_admission': False}))
    if report['status'] == 'BLOCKED_OR_REJECTED':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
