#!/usr/bin/env python3
"""Bounded, read-only historical price acquisition; no retries or transactions."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import urllib.error
import urllib.request

START, END = 25880316, 26095351
START_HASH = '0x0b29e0c8c1997f059f82e7fed67e047269f68422ab194d56546c1c9833469d96'
END_HASH = '0x0d7a15fbb72e69696a33c65bc20902fe08e5630862ada64b065a97405c70c781'
ENDPOINT = 'https://ethereum-public.nodies.app'
ORACLE = '0x54586bE62E3c3580375aE3723C145253060Ca0C2'
PRIMARY_PIN = '1c359a46f8e0b5fbeb39df593ce0e98f581909d057a09819635602ae2a76f906'
ASSET_SOURCE_PIN = 'c64719793eed5fd5b09eb725f18b811746b1a50e101bfa00b9569be65282d19e'


def canon(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def need(value, message):
    if not value:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def calldata(document):
    assets = document['assets']
    need(document['source_sha256'] == ASSET_SOURCE_PIN and len(assets) == len(set(assets)) == 67,
         'asset source or cardinality')
    for asset in assets:
        need(isinstance(asset, str) and len(asset) == 42 and asset.startswith('0x')
             and bytes.fromhex(asset[2:]).hex() == asset[2:], 'asset encoding')
    # getAssetsPrices(address[]): selector independently checked against the helper.
    words = (32).to_bytes(32, 'big') + (67).to_bytes(32, 'big')
    words += b''.join(bytes.fromhex(a[2:]).rjust(32, b'\0') for a in assets)
    return '0x9d23d9f2' + words.hex()


def block_bindings(primary):
    pins, parents = [], []
    for a in range(START, END + 1, 50):
        b = min(END, a + 49)
        name = f'chunk-{a:08d}-{b:08d}.json'
        raw = (primary / name).read_bytes()
        pins.append({'name': name, 'sha256': sha(raw)})
        doc = json.loads(raw)
        need(doc['provider'] == 'drpc' and doc['start_block'] == a and doc['end_block'] == b
             and len(doc['headers']) == b - a + 1, 'primary chunk coverage')
        parents.extend(row[1] for row in doc['headers'])
    need(sha(canon(pins)) == PRIMARY_PIN, 'original primary chunk commitment')
    hashes = parents[1:] + [END_HASH]
    need(len(hashes) == END - START + 1 and hashes[0] == START_HASH, 'block hash inventory')
    return hashes


def price_request(number, block_hash, data):
    return {'jsonrpc': '2.0', 'id': number, 'method': 'eth_call',
            'params': [{'to': ORACLE, 'data': data},
                       {'blockHash': block_hash, 'requireCanonical': True}]}


def decode_prices(result):
    need(isinstance(result, str) and result.startswith('0x') and len(result) == 2 + 69 * 64,
         'price ABI shape')
    raw = bytes.fromhex(result[2:])
    words = [int.from_bytes(raw[i:i + 32], 'big') for i in range(0, len(raw), 32)]
    need(words[:2] == [32, 67] and all(v > 0 for v in words[2:]), 'price ABI offset/count/value')
    return words[2:]


def decode_batch(body, requests):
    responses = json.loads(body)
    need(isinstance(responses, list) and len(responses) == len(requests), 'response batch cardinality')
    by_id = {}
    for response in responses:
        need(isinstance(response, dict) and response.get('jsonrpc') == '2.0'
             and type(response.get('id')) is int and response['id'] not in by_id,
             'response identity/duplicate')
        need('error' not in response and 'result' in response, 'RPC error: ' + str(response.get('error')))
        by_id[response['id']] = decode_prices(response['result'])
    need(set(by_id) == {r['id'] for r in requests}, 'response block identity')
    return by_id


class Acquisition:
    def __init__(self, out):
        self.out = out
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.next_request = 0.0
        self.calls = 0
        self.http_requests = 0

    def request(self, payload, stream):
        count = len(payload) if isinstance(payload, list) else 1
        with self.lock:
            need(not self.stop.is_set(), 'acquisition already stopped')
            need(self.calls + count <= END - START + 4, 'finite RPC call budget')
            delay = max(0, self.next_request - time.monotonic())
            self.next_request = max(self.next_request, time.monotonic()) + 0.125
            self.calls += count
            self.http_requests += 1
        if self.stop.wait(delay):
            raise ValueError('acquisition stopped before request')
        need(shutil.disk_usage(self.out).free > 2 * 1024**3, 'free disk budget')
        request = json.dumps(payload, separators=(',', ':')).encode()
        sent = now()
        started = time.monotonic()
        status, headers, body, error = None, [], b'', None
        try:
            req = urllib.request.Request(ENDPOINT, data=request, headers={
                'Content-Type': 'application/json', 'User-Agent': 'nqc-census-v2-readonly-oracle/1'})
            with urllib.request.urlopen(req, timeout=40) as response:
                status, headers = response.status, list(response.headers.items())
                body = response.read(2 * 1024**2 + 1)
        except urllib.error.HTTPError as exc:
            status, headers = exc.code, list(exc.headers.items())
            body, error = exc.read(2 * 1024**2 + 1), str(exc)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        record = {'url': ENDPOINT, 'sent_at': sent, 'received_at': now(),
                  'elapsed_seconds': time.monotonic() - started, 'http_status': status,
                  'response_headers': headers, 'transport_error': error,
                  'request_body': request.decode('utf-8'), 'request_sha256': sha(request),
                  'response_body': body.decode('utf-8', errors='strict'), 'response_sha256': sha(body)}
        stream.write(canon(record))
        stream.flush()
        need(error is None and status == 200 and len(body) <= 2 * 1024**2,
             'transport/access/rate/size failure: ' + str(error or status))
        return body


def run(args):
    need(1 <= args.workers <= 8 and START <= args.start <= args.end <= END, 'bounded acquisition scope')
    args.out.mkdir(parents=True, exist_ok=False)
    data = calldata(json.loads(args.assets.read_bytes()))
    hashes = block_bindings(args.primary)
    (args.out / 'assets.json').write_bytes(args.assets.read_bytes())
    (args.out / 'collector.py').write_bytes(Path(__file__).read_bytes())
    acq = Acquisition(args.out)
    begun = now()
    failures, complete = [], []
    with gzip.open(args.out / 'anchors.jsonl.gz', 'wb') as stream:
        for i, (method, params) in enumerate([
            ('eth_chainId', []), ('eth_getBlockByNumber', [hex(START), False]),
            ('eth_getBlockByNumber', [hex(END), False]),
        ]):
            request = {'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}
            response = json.loads(acq.request(request, stream))
            need(response.get('id') == i and 'error' not in response, 'anchor RPC identity/error')
            if i == 0:
                need(response['result'] == '0x1', 'Ethereum chain')
            else:
                expected = (START, START_HASH) if i == 1 else (END, END_HASH)
                need((int(response['result']['number'], 16), response['result']['hash']) == expected,
                     'historical anchor')

    def chunk(a, b):
        done = 0
        path = args.out / f'capture-{a:08d}-{b:08d}.jsonl.gz'
        with gzip.open(path, 'wb', compresslevel=6) as stream:
            for first in range(a, b + 1, 10):
                if acq.stop.is_set():
                    break
                requests = [price_request(n, hashes[n - START], data)
                            for n in range(first, min(b + 1, first + 10))]
                try:
                    decode_batch(acq.request(requests, stream), requests)
                except Exception:
                    acq.stop.set()
                    raise
                done += len(requests)
        return {'start_block': a, 'end_block': b, 'observed_blocks': done,
                'file': path.name, 'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size}

    ranges = [(a, min(args.end, a + 999)) for a in range(args.start, args.end + 1, 1000)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        pending = {executor.submit(chunk, a, b): (a, b) for a, b in ranges}
        for future in concurrent.futures.as_completed(pending):
            a, b = pending[future]
            try:
                result = future.result()
                complete.append(result)
                if result['observed_blocks']:
                    print(json.dumps({'observed_blocks': sum(x['observed_blocks'] for x in complete),
                                      'last_range': [a, b], 'captured_bytes': sum(x['bytes'] for x in complete)}, sort_keys=True), flush=True)
            except Exception as exc:
                acq.stop.set()
                failures.append({'range': [a, b], 'reason': str(exc)})
    observed = sum(x['observed_blocks'] for x in complete)
    report = {'schema': 'nqc-direct-oracle-acquisition-v1', 'started_at': begun, 'finished_at': now(),
              'status': 'COMPLETE_REQUESTED_RANGE' if not failures and observed == args.end - args.start + 1 else 'INCOMPLETE',
              'start_block': args.start, 'end_block': args.end, 'observed_blocks_in_successful_files': observed,
              'endpoint': ENDPOINT, 'workers': args.workers, 'maximum_http_requests_per_second': 8,
              'maximum_batch_size': 10, 'attempted_rpc_calls': acq.calls, 'attempted_http_requests': acq.http_requests,
              'primary_chunk_commitment': PRIMARY_PIN, 'collector_sha256': sha(Path(__file__).read_bytes()),
              'asset_document_sha256': sha(args.assets.read_bytes()),
              'completed_files': sorted(complete, key=lambda x: x['start_block']), 'failures': failures,
              'historical_decision_time_observation': False, 'independent_node_infrastructure_proven': False,
              'census_certified': False, 'gas_spent': False}
    (args.out / 'acquisition.json').write_bytes(canon(report))
    print(json.dumps({k: v for k, v in report.items() if k not in {'completed_files', 'failures'}}, sort_keys=True), flush=True)
    return 0 if report['status'] == 'COMPLETE_REQUESTED_RANGE' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['primary', 'assets', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--start', type=int, default=START)
    parser.add_argument('--end', type=int, default=END)
    parser.add_argument('--workers', type=int, default=4)
    raise SystemExit(run(parser.parse_args()))
