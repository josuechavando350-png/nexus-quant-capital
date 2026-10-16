#!/usr/bin/env python3
"""Bounded reads from one documented public demo; no retry, redirect or sending."""
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
import urllib.error

ENDPOINT = 'https://docs-demo.robinhood-mainnet.quiknode.pro/'
MORPHO = '0x9d53d5e3bd5e8d4cbfa6db1ca238aea02e651010'
ORACLE = '0xcde9599059f8ae6d6b9f33a0af7877827ec75f16'
IRM = '0x2bd3d5965b26b51814ac95127b2b80dd6ccc0fa1'
MARKET = '0xaa586d26a6fe62d9c0f0948fede6e2130500ac7a655587447e2d4a37e6330589'
BORROW = '0x570954540bed6b1304a87dfe815a5eda4a648f7097a16240dcd85c9b5fd42a43'
ACCOUNT = '0xa16e02e87b7454126e5e10d957a927a7f5b5d2be'
EXECUTOR = '0x10c6e9530f1c1af873a391030a1d9e8ed0630d26'
ROUTER = '0xeebe00ac0756308ac4aabfd76c05c4f3088b8883'
FIXTURES = {ACCOUNT, EXECUTOR, ROUTER}
HASH = re.compile(r'0x[0-9a-f]{64}\Z')
QUANTITY = re.compile(r'0x(?:0|[1-9a-f][0-9a-f]*)\Z')
MAX_REPLY = 4 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024
MAX_REQUESTS = 90


class Rejected(ValueError):
    pass


class RpcFailure(Rejected):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.data = code, data


def need(condition, message):
    if not condition:
        raise Rejected(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def qty(value):
    need(isinstance(value, str) and QUANTITY.fullmatch(value), 'INVALID_QUANTITY')
    return int(value, 16)


def pinned(value):
    return isinstance(value, dict) and set(value) == {'blockHash', 'requireCanonical'} and \
        isinstance(value['blockHash'], str) and HASH.fullmatch(value['blockHash']) and value['requireCanonical'] is True


def validate(method, params):
    need(type(params) is list, 'PARAMS_MUST_BE_LIST')
    if method == 'eth_chainId':
        need(params == [], 'CHAIN_PARAMS')
    elif method == 'eth_getBlockByNumber':
        need(len(params) == 2 and params[1] is False, 'HEADER_ONLY')
        if params[0] != 'latest': qty(params[0])
    elif method == 'eth_getCode':
        need(len(params) == 2 and pinned(params[1]), 'PIN_CODE_TO_HASH')
        need(params[0] in FIXTURES | {MORPHO, ORACLE, IRM}, 'UNAPPROVED_CODE_ADDRESS')
    elif method == 'eth_getLogs':
        need(len(params) == 1 and type(params[0]) is dict, 'LOG_FILTER')
        item = params[0]
        need(set(item) == {'address', 'topics', 'fromBlock', 'toBlock'} and
             item['address'] == MORPHO and item['topics'] == [BORROW, MARKET], 'BORROW_FILTER_REQUIRED')
        start, end = qty(item['fromBlock']), qty(item['toBlock'])
        need(0 <= end - start < 512, 'BOUNDED_LOG_RANGE')
    elif method == 'eth_call':
        need(len(params) == 2 and pinned(params[1]), 'PIN_CALL_TO_HASH_NO_OVERRIDES')
        tx = params[0]
        need(type(tx) is dict and set(tx) == {'to', 'data'} and type(tx['data']) is str, 'VIEW_CALL_ONLY')
        selector = tx['data'][:10]
        allowed = {MORPHO: {'0x5c60e39a', '0x93c52062', '0x2c3c9157'}, ORACLE: {'0xa035b1fe'}, IRM: {'0x8c00bf6b'}}
        need(tx['to'] in allowed and selector in allowed[tx['to']], 'UNAPPROVED_VIEW')
        need(re.fullmatch(r'0x[0-9a-f]+', tx['data']) and len(tx['data']) % 2 == 0, 'INVALID_CALLDATA')
    elif method == 'debug_traceCall':
        need(len(params) == 3 and pinned(params[1]), 'PIN_SIMULATION_TO_HASH')
        tx, _, config = params
        need(set(tx) == {'from', 'to', 'data', 'gas', 'gasPrice'} and tx['from'] == ACCOUNT and
             tx['to'] == EXECUTOR and tx['data'].startswith('0x3d47ed94') and qty(tx['gas']) <= 3000000,
             'ONLY_RESEARCH_ROUTE_SIMULATION')
        qty(tx['gasPrice'])
        need(set(config) <= {'tracer', 'tracerConfig', 'timeout', 'reexec', 'stateOverrides', 'blockOverrides'} and
             config.get('tracer') == 'callTracer' and config.get('tracerConfig') == {'withLog': True} and
             config.get('timeout') == '10s' and config.get('reexec') == 0 and
             set(config.get('stateOverrides', {})) == FIXTURES, 'BOUNDED_FIXTURE_TRACE')
        if 'blockOverrides' in config:
            need(set(config['blockOverrides']) == {'time'}, 'ONLY_TIME_PROJECTION')
            qty(config['blockOverrides']['time'])
    else:
        raise Rejected('METHOD_NOT_READ_ONLY_ALLOWLISTED')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Rejected('REDIRECT_REFUSED')


def network(request):
    http = urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(ENDPOINT, data=canonical(request), headers={'Content-Type': 'application/json'})
    with http.open(req, timeout=20) as response:
        return response.read(MAX_REPLY + 1)


class Reader:
    def __init__(self, folder, transport=network, limit=MAX_REQUESTS):
        need(type(limit) is int and 1 <= limit <= MAX_REQUESTS, 'INVALID_REQUEST_BUDGET')
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.transport, self.limit = transport, limit
        self.count, self.total, self.stopped = 0, 0, False
        self.records = []
        self.started_ns = time.monotonic_ns()

    def call(self, method, params, label):
        validate(method, params)
        need(not self.stopped and self.count < self.limit, 'READER_STOPPED_OR_EXHAUSTED')
        need(time.monotonic_ns() - self.started_ns <= 240 * 10**9, 'RUN_TIME_BUDGET_EXCEEDED')
        need(re.fullmatch(r'[a-z0-9_-]{1,70}', label), 'INVALID_LABEL')
        self.count += 1
        request = {'jsonrpc': '2.0', 'id': self.count, 'method': method, 'params': params}
        record = {'label': label, 'request': request, 'started_ns': time.monotonic_ns(), 'started_wall_ns': time.time_ns()}
        self.records.append(record)
        try:
            raw = self.transport(request)
            record['received_ns'], record['received_wall_ns'] = time.monotonic_ns(), time.time_ns()
            self.total += len(raw)
            need(len(raw) <= MAX_REPLY and self.total <= MAX_TOTAL, 'RESPONSE_BUDGET_EXCEEDED')
            filename = f'{self.count:03d}-{label}.json'
            (self.folder / filename).write_bytes(raw)
            record.update(response_file=filename, response_sha256=hashlib.sha256(raw).hexdigest())
            response = json.loads(raw)
            need(type(response) is dict and response.get('id') == self.count and
                 response.get('jsonrpc') == '2.0' and ('result' in response) != ('error' in response), 'INVALID_RPC_ENVELOPE')
            if 'error' in response:
                error = response['error']
                record['rpc_error'] = error
                raise RpcFailure(error.get('code'), str(error.get('message', 'RPC_ERROR')), error.get('data'))
            return response['result']
        except Exception as error:
            # Any transport/provider error stops the session. Never rotate endpoints or retry.
            self.stopped = True
            record['exception'] = type(error).__name__
            if isinstance(error, urllib.error.HTTPError): record['http_status'] = error.code
            raise
        finally:
            record['finished_ns'] = time.monotonic_ns()
            (self.folder / 'requests.json').write_bytes(canonical(self.records))


def header(raw, wall_ns=None):
    need(type(raw) is dict, 'MISSING_HEADER')
    for key in ['hash', 'parentHash', 'stateRoot']:
        need(isinstance(raw.get(key), str) and HASH.fullmatch(raw[key]), 'INVALID_HEADER_HASH')
    number, timestamp = qty(raw.get('number')), qty(raw.get('timestamp'))
    fee = qty(raw.get('baseFeePerGas'))
    need(number > 0 and timestamp > 0 and raw['hash'] != raw['parentHash'], 'INVALID_HEADER')
    if wall_ns is not None:
        age = wall_ns // 10**9 - timestamp
        need(-5 <= age <= 30, 'STALE_OR_FUTURE_HEADER')
    return {'number': number, 'timestamp': timestamp, 'hash': raw['hash'], 'parent_hash': raw['parentHash'],
            'state_root': raw['stateRoot'], 'base_fee_wei': fee}
