#!/usr/bin/env python3
"""Bounded read-only Nitro archive capture for ONE already-mined transaction.

No signer, broadcast, deployment, state override, fork-funding or endpoint fallback.
Needs an explicitly configured NQC_ROBINHOOD_ARCHIVE_RPC. Does not run by default.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from fee_accounting import route, receipt_fee

NODE_INTERFACE = '0x00000000000000000000000000000000000000c8'
SELECTOR = 'c94e6eeb'  # gasEstimateComponents(address,bool,bytes), verified with cast.
METHODS = {'eth_chainId', 'web3_clientVersion', 'eth_getTransactionByHash',
           'eth_getTransactionReceipt', 'eth_getBlockByHash', 'eth_getBlockByNumber',
           'debug_traceTransaction', 'eth_call'}
MAX_REQUESTS = 12
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CAPTURE_BYTES = 32 * 1024 * 1024
CORE = {route.MORPHO, route.WSNET, route.SNET, route.NET, route.STAKING, route.USDG, route.POOL}


class CaptureError(Exception):
    pass


class RpcError(CaptureError):
    pass


def encode_components(target, calldata):
    target = route.data_hex(target, 20)[2:]
    raw = bytes.fromhex(route.data_hex(calldata)[2:])
    route.require(4 <= len(raw) <= 131072, 'invalid complete calldata length')
    word = lambda value: format(value, '064x')
    return '0x' + SELECTOR + target.rjust(64, '0') + word(0) + word(96) + word(len(raw)) + raw.hex().ljust(((len(raw) + 31) // 32) * 64, '0')


def decode_components(value):
    total, parent, base, l1_base = route.words(value, 4)
    route.require(0 < total < 2**64 and 0 <= parent <= total and parent < 2**64 and base > 0,
                  'invalid NodeInterface component values')
    return {'estimate_total_gas': total, 'estimate_l1_gas_in_l2_units': parent,
            'estimate_execution_gas': total - parent, 'base_fee_wei': base,
            'l1_base_fee_estimate_wei': l1_base, 'estimated_total_fee_wei': total * base,
            'estimated_l1_fee_wei': parent * base,
            'estimated_execution_fee_wei': (total - parent) * base,
            'state_context': 'PREVIOUS_BLOCK_END_NOT_PRE_TRANSACTION',
            'is_nqc_transaction': False, 'is_actual_fee_receipt': False}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CaptureError('HTTP_REDIRECT_REQUIRES_EXPLICIT_ENDPOINT')


class Client:
    def __init__(self, endpoint, out):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise CaptureError('REQUIRE_HTTPS_ENDPOINT_WITHOUT_USERINFO_OR_FRAGMENT')
        self.endpoint, self.out = endpoint, out
        self.host = parsed.hostname  # Never record URL paths, query strings or credentials.
        self.opener = urllib.request.build_opener(NoRedirect())
        self.records, self.bytes_read = [], 0

    def ask(self, label, method, params):
        if method not in METHODS:
            raise CaptureError('RPC_METHOD_NOT_READ_ALLOWED')
        if len(self.records) >= MAX_REQUESTS:
            raise CaptureError('REQUEST_BUDGET_EXHAUSTED')
        identity = len(self.records) + 1
        payload = {'jsonrpc': '2.0', 'id': identity, 'method': method, 'params': params}
        record = {'label': label, 'request': payload}
        self.records.append(record)
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            self.bytes_read += len(raw)
            if len(raw) > MAX_RESPONSE_BYTES or self.bytes_read > MAX_CAPTURE_BYTES:
                raise CaptureError('RESPONSE_SIZE_BUDGET_EXHAUSTED')
            message = json.loads(raw)
            if not isinstance(message, dict) or message.get('id') != identity or message.get('jsonrpc') != '2.0':
                raise CaptureError('RPC_ENVELOPE_MISMATCH')
            if 'error' in message:
                code = message['error'].get('code') if isinstance(message['error'], dict) else None
                record['rpc_error_code'] = code if isinstance(code, int) else None
                raise RpcError('RPC_ERROR_' + str(record['rpc_error_code']))
            if message.get('result') is None:
                raise CaptureError('NULL_RPC_RESULT')
            # Successful responses contain only public chain data. Failed response text
            # is not persisted because some services echo credentials in errors.
            name = f'{identity:02d}-{label}.json'
            (self.out / name).write_bytes(raw)
            record.update(response_file=name, response_sha256=hashlib.sha256(raw).hexdigest())
            return message['result']
        except urllib.error.HTTPError as error:
            record['http_status'] = error.code
            raise CaptureError('HTTP_' + str(error.code) + '_STOP_NO_RETRY') from None
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise CaptureError('TRANSPORT_OR_JSON_ERROR_STOP_NO_RETRY') from None


def verify_anchors(tx, receipt, header, parent, original):
    route.validate_receipt(receipt, route.SELECTED)
    for key in ['transactionHash', 'blockHash', 'blockNumber', 'transactionIndex', 'status',
                'gasUsed', 'effectiveGasPrice', 'gasUsedForL1', 'from', 'to']:
        route.require(receipt[key].lower() == original[key].lower(), 'archived receipt changed: ' + key)
    normalize = lambda log: (log['address'].lower(), tuple(t.lower() for t in log['topics']), log['data'].lower(), log['logIndex'])
    route.require([normalize(log) for log in receipt['logs']] == [normalize(log) for log in original['logs']], 'archived logs changed')
    for key, expected in [('hash', route.SELECTED), ('blockHash', receipt['blockHash']),
                          ('blockNumber', receipt['blockNumber']), ('transactionIndex', receipt['transactionIndex']),
                          ('from', receipt['from']), ('to', receipt['to'])]:
        route.require(tx[key].lower() == expected.lower(), 'transaction identity mismatch: ' + key)
    route.require(route.number(tx['chainId']) == 4663 and route.number(tx['value']) == 0, 'transaction chain/value mismatch')
    route.require(route.number(tx['gas']) >= route.number(receipt['gasUsed']), 'transaction gas limit mismatch')
    route.data_hex(tx['input'])
    route.require(header['hash'].lower() == receipt['blockHash'].lower() and header['number'] == receipt['blockNumber'], 'header mismatch')
    route.require(header['parentHash'].lower() == parent['hash'].lower(), 'parent link mismatch')
    route.require(route.number(parent['number']) + 1 == route.number(header['number']), 'parent height mismatch')
    route.require(header['transactions'][route.number(tx['transactionIndex'])].lower() == route.SELECTED, 'transaction order mismatch')


def trace_consistency(tx, receipt, trace, prestate, diff):
    for field, expected in [('from', tx['from']), ('to', tx['to']), ('input', tx['input'])]:
        route.require(trace[field].lower() == expected.lower(), 'trace root mismatch: ' + field)
    route.require(not trace.get('error') and route.number(trace.get('value', '0x0')) == route.number(tx['value']), 'trace reverted/value mismatch')
    route.require(route.number(trace['gasUsed']) == route.number(receipt['gasUsed']), 'trace gas differs from selected zero-poster-gas receipt')
    calls, logs = set(), []

    def walk(frame, reverted=False, depth=0):
        route.require(depth < 128, 'excessive trace depth')
        reverted = reverted or bool(frame.get('error'))
        if frame.get('to'):
            calls.add(frame['to'].lower())
        if not reverted:
            logs.extend(frame.get('logs', []))
        for child in frame.get('calls', []):
            walk(child, reverted, depth + 1)

    walk(trace)
    signature = lambda log: (log['address'].lower(), tuple(t.lower() for t in log['topics']), log['data'].lower())
    route.require(Counter(map(signature, logs)) == Counter(map(signature, receipt['logs'])), 'trace log multiset mismatch')
    route.require(CORE <= calls, 'trace omits route contracts')
    states = {address.lower(): state for address, state in prestate.items()}
    for address in CORE | {tx['to'].lower()}:
        route.require(address in states and len(route.data_hex(states[address].get('code', '0x'))) > 2, 'prestate missing route code')
        # Geth omits storage for stateless contracts. Omission is not missing code.
        route.require(isinstance(states[address].get('storage', {}), dict), 'malformed prestate storage')
        for slot, value in states[address].get('storage', {}).items():
            route.data_hex(slot, 32)
            route.data_hex(value, 32)
    route.require(isinstance(diff.get('pre'), dict) and isinstance(diff.get('post'), dict)
                  and bool(diff['pre']) and bool(diff['post']), 'missing state difference')
    # Logs are compared as a multiset. Their interleaved ordering and native ArbOS
    # internal state are retained for later independent review, not certified here.
    return {'provider_trace_consistent_with_receipt': True,
            'route_contracts_seen': sorted(CORE), 'prestate_account_count': len(states),
            'trace_log_count': len(logs), 'log_order_independently_verified': False,
            'state_cryptographic_proof': False, 'independent_local_replay': False,
            'nqc_executor_replayed': False}


def capture(client, original, prefix):
    ask = client.ask
    route.require(route.number(ask('chain-id', 'eth_chainId', [])) == 4663, 'wrong chain')
    version = ask('client-version', 'web3_clientVersion', [])
    tx = ask('transaction', 'eth_getTransactionByHash', [route.SELECTED])
    receipt = ask('receipt', 'eth_getTransactionReceipt', [route.SELECTED])
    header = ask('block', 'eth_getBlockByHash', [receipt['blockHash'], False])
    parent = ask('parent', 'eth_getBlockByHash', [header['parentHash'], False])
    verify_anchors(tx, receipt, header, parent, original)
    route.require(tx['input'].lower().startswith(prefix.lower()) and len(tx['input']) > len(prefix), 'full calldata not recovered')
    trace = ask('call-trace', 'debug_traceTransaction', [route.SELECTED,
                {'tracer': 'callTracer', 'timeout': '10s', 'reexec': 0, 'tracerConfig': {'withLog': True}}])
    prestate = ask('prestate', 'debug_traceTransaction', [route.SELECTED,
                {'tracer': 'prestateTracer', 'timeout': '10s', 'reexec': 0,
                 'tracerConfig': {'diffMode': False, 'disableCode': False, 'disableStorage': False}}])
    diff = ask('state-diff', 'debug_traceTransaction', [route.SELECTED,
                {'tracer': 'prestateTracer', 'timeout': '10s', 'reexec': 0, 'tracerConfig': {'diffMode': True}}])
    trace_report = trace_consistency(tx, receipt, trace, prestate, diff)
    component_error, components = None, None
    try:
        value = ask('prior-block-components', 'eth_call', [
            {'from': tx['from'], 'to': NODE_INTERFACE, 'value': tx['value'], 'gas': '0x5b8d80',
             'data': encode_components(tx['to'], tx['input'])},
            {'blockHash': parent['hash'], 'requireCanonical': True}])
        components = decode_components(value)
    except RpcError as error:
        component_error = str(error)
    final = ask('canonical-block-recheck', 'eth_getBlockByNumber', [header['number'], False])
    for key in ['hash', 'parentHash', 'stateRoot', 'timestamp', 'number']:
        route.require(final[key] == header[key], 'canonical block changed: ' + key)
    return {'status': 'HISTORICAL_PROVIDER_TRACE_CAPTURED_NOT_NQC_REPLAY',
            'client_version': version, 'receipt_fee': receipt_fee(receipt), 'trace': trace_report,
            'calldata_bytes': (len(tx['input']) - 2) // 2,
            'calldata_sha256': hashlib.sha256(bytes.fromhex(tx['input'][2:])).hexdigest(),
            'prior_block_components': components, 'prior_block_components_error': component_error,
            'nqc_full_route_replayed': False, 'nqc_cost_measured': False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True, help='New capture directory; existing paths are rejected')
    args = ap.parse_args()
    if args.out.exists():
        raise SystemExit('Output must be a new directory')
    args.out.mkdir(parents=True)
    endpoint = os.environ.get('NQC_ROBINHOOD_ARCHIVE_RPC')
    client = None
    started = time.time()
    result = {'status': 'BLOCKED_NO_AUTHORIZED_ARCHIVE_ENDPOINT',
              'nqc_full_route_replayed': False, 'nqc_cost_measured': False}
    try:
        if endpoint:
            client = Client(endpoint, args.out)
            # Authenticate existing observations before making requests.
            from fee_accounting import PREVIOUS
            route.audit(PREVIOUS / 'evidence')
            records = json.loads((PREVIOUS / 'evidence/historical-receipts/rpc_original_receipts.json').read_text())
            original = next(row['result'] for row in records[1:] if row['result']['transactionHash'] == route.SELECTED)
            prefix = json.loads((PREVIOUS / 'evidence/explorer/transaction.json').read_text())['data']['raw_input']
            result = capture(client, original, prefix)
    except (CaptureError, ValueError, KeyError, TypeError, IndexError) as error:
        # Never echo arbitrary service exception text containing an endpoint or token.
        result = {'status': 'BLOCKED_CAPTURE_OR_VALIDATION',
                  'reason': str(error) if isinstance(error, CaptureError) else type(error).__name__,
                  'nqc_full_route_replayed': False, 'nqc_cost_measured': False}
    result.update(transaction_hash=route.SELECTED, chain_id=4663, read_only=True,
                  requests=client.records if client else [],
                  provider_host=client.host if client else None,
                  elapsed_seconds=round(time.time() - started, 3),
                  needed_capabilities=['archive state at blocks 66744161 and 66744162',
                      'full eth_getTransactionByHash', 'debug_traceTransaction callTracer withLog and prestateTracer',
                      'Nitro NodeInterface eth_call at a pinned historical block'],
                  live_authorized=False, external_subscription_created=False)
    (args.out / 'capture.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'requests'}, indent=2))
    return 2 if result['status'].startswith('BLOCKED') else 0


if __name__ == '__main__':
    raise SystemExit(main())
