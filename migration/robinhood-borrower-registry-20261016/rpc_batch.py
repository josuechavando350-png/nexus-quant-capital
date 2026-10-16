"""Bounded JSON-RPC batches. Each element counts against the RPC budget."""
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
import urllib.error

from common import (need, canonical, qty, pinned, MORPHO, MARKET, BORROW, ORACLE,
                    IRM, MARKET_PARAMS, words, NoRedirect, RpcFailure, ENDPOINT)

MAX_REPLY = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def validate(method, params):
    need(type(params) is list, 'PARAMS_LIST')
    if method == 'eth_chainId':
        need(params == [], 'CHAIN_PARAMS')
    elif method == 'eth_getBlockByNumber':
        need(len(params) == 2 and params[1] is False, 'HEADERS_ONLY')
        if params[0] != 'latest': qty(params[0])
    elif method == 'eth_getLogs':
        need(len(params) == 1 and type(params[0]) is dict, 'LOG_FILTER')
        f = params[0]
        need(set(f) == {'address', 'topics', 'fromBlock', 'toBlock'} and
             f['address'] == MORPHO and f['topics'] == [BORROW, MARKET], 'ONLY_FIXED_BORROW_MARKET')
        need(0 <= qty(f['toBlock']) - qty(f['fromBlock']) < 10000, 'LOG_RANGE_LIMIT')
    elif method == 'eth_getCode':
        need(len(params) == 2 and params[0] in {MORPHO, ORACLE, IRM} and pinned(params[1]), 'PINNED_PROTOCOL_CODE')
    elif method == 'eth_call':
        need(len(params) == 2 and pinned(params[1]), 'PINNED_VIEW_NO_OVERRIDES')
        tx = params[0]
        need(type(tx) is dict and set(tx) == {'to', 'data'}, 'VIEW_FIELDS')
        data = tx['data']
        need(type(data) is str and re.fullmatch(r'0x[0-9a-f]+', data), 'CALLDATA_HEX')
        selector = data[:10]
        if tx['to'] == MORPHO and selector in {'0x5c60e39a', '0x2c3c9157'}:
            need(data[10:] == MARKET[2:], 'FIXED_MARKET')
        elif tx['to'] == MORPHO and selector == '0x93c52062':
            values = words('0x' + data[10:], 2)
            need(values[0] == int(MARKET, 16) and 0 < values[1] < 2**160, 'POSITION_ABI')
        elif tx['to'] == ORACLE:
            need(data == '0xa035b1fe', 'ORACLE_PRICE_ONLY')
        elif tx['to'] == IRM:
            need(selector == '0x8c00bf6b', 'RATE_VIEW_ONLY')
            values = words('0x' + data[10:], 11)
            need(values[:5] == MARKET_PARAMS and all(x < 2**128 for x in values[5:]), 'RATE_ABI')
        else:
            raise ValueError('UNAPPROVED_VIEW')
    else:
        raise ValueError('METHOD_NOT_ALLOWED')


def network(payload):
    req = urllib.request.Request(ENDPOINT, data=canonical(payload), headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as response:
        return response.read(MAX_REPLY + 1)


def decode(payload, raw):
    requests = payload if type(payload) is list else [payload]
    value = json.loads(raw)
    replies = value if type(payload) is list else [value]
    need(type(replies) is list and len(replies) == len(requests), 'BATCH_SIZE_OR_ENVELOPE')
    by_id = {}
    for reply in replies:
        need(type(reply) is dict and type(reply.get('id')) is int and reply.get('jsonrpc') == '2.0' and
             ('result' in reply) != ('error' in reply), 'INVALID_RPC_ENVELOPE')
        need(reply['id'] not in by_id, 'DUPLICATE_RESPONSE_ID')
        by_id[reply['id']] = reply
    need(set(by_id) == {r['id'] for r in requests}, 'MISSING_OR_UNKNOWN_ID')
    for request in requests:
        reply = by_id[request['id']]
        if 'error' in reply:
            error = reply['error']
            need(type(error) is dict, 'MALFORMED_RPC_ERROR')
            raise RpcFailure(error.get('code'), str(error.get('message', 'RPC_ERROR')), error.get('data'))
    return [by_id[r['id']]['result'] for r in requests]


class Reader:
    def __init__(self, folder, transport=network, max_requests=512, max_seconds=900):
        need(type(max_requests) is int and 1 <= max_requests <= 512 and
             type(max_seconds) is int and 1 <= max_seconds <= 900, 'BOUNDED_BUDGET')
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.transport, self.max_requests, self.max_seconds = transport, max_requests, max_seconds
        self.started_ns, self.count, self.total = time.monotonic_ns(), 0, 0
        self.records, self.stopped = [], False

    def group(self, queries, label, batch=True):
        need(type(queries) is list and 1 <= len(queries) <= 4 and (batch or len(queries) == 1), 'BATCH_WIDTH')
        for method, params in queries: validate(method, params)
        need(re.fullmatch(r'[a-z0-9_-]{1,90}', label), 'LABEL')
        need(not self.stopped and self.count + len(queries) <= self.max_requests, 'REQUEST_BUDGET_OR_STOPPED')
        need(time.monotonic_ns() - self.started_ns <= self.max_seconds * 10**9, 'TIME_BUDGET')
        requests = []
        for method, params in queries:
            self.count += 1
            requests.append({'jsonrpc': '2.0', 'id': self.count, 'method': method, 'params': params})
        payload = requests if batch else requests[0]
        row = {'label': label, 'payload': payload, 'started_ns': time.monotonic_ns(), 'started_wall_ns': time.time_ns()}
        self.records.append(row)
        try:
            raw = self.transport(payload)
            row.update(received_ns=time.monotonic_ns(), received_wall_ns=time.time_ns())
            self.total += len(raw)
            need(len(raw) <= MAX_REPLY and self.total <= MAX_TOTAL, 'RESPONSE_BYTE_BUDGET')
            name = f'{len(self.records):03d}-{label}.json'
            (self.folder / name).write_bytes(raw)
            row.update(response_file=name, response_sha256=hashlib.sha256(raw).hexdigest())
            return decode(payload, raw)
        except Exception as error:
            self.stopped = True
            row['exception'] = type(error).__name__
            if isinstance(error, RpcFailure): row['rpc_error_code'] = error.code
            if isinstance(error, urllib.error.HTTPError): row['http_status'] = error.code
            raise
        finally:
            row['finished_ns'] = time.monotonic_ns()
            (self.folder / 'requests.json').write_bytes(canonical(self.records))

    def call(self, method, params, label):
        return self.group([(method, params)], label, batch=False)[0]

    def many(self, queries, label, mode='batch'):
        need(mode in {'batch', 'sequential'}, 'READ_MODE')
        result = []
        width = 4 if mode == 'batch' else 1
        for offset in range(0, len(queries), width):
            result.extend(self.group(queries[offset:offset + width], f'{label}-{offset}', batch=mode == 'batch'))
        return result
