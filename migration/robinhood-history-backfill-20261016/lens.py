"""One bounded eth_call contract-creation simulation, with exact local initcode."""
import hashlib
import json
import re
import time
import urllib.error

from support import (HERE, need, canonical, pin, words, encode, derive, decode,
                     MAX_REPLY, MAX_TOTAL)
from common import RpcFailure


def initcode(addresses):
    need(type(addresses) is list and len(addresses) <= 64 and addresses == sorted(set(addresses)), 'LENS_COHORT_ORDER')
    need(all(type(a) is str and re.fullmatch('0x[0-9a-f]{40}', a) and int(a, 16) > 0 for a in addresses), 'LENS_ADDRESS')
    artifact = json.loads((HERE / 'lens-build.json').read_text())
    code = artifact['creation_bytecode']
    need(hashlib.sha256(bytes.fromhex(code[2:])).hexdigest() == artifact['creation_bytecode_sha256'], 'LENS_CODE_HASH')
    return code + encode('', 32, len(addresses), *[int(a, 16) for a in addresses])


def query(block, addresses):
    # Omitted `to` is the standard creation-call form. Never sent as a transaction.
    return {'data': initcode(addresses), 'gas': hex(2000000)}, pin(block)


def parse(block, addresses, output, policy):
    count = 8 + 3 * len(addresses)
    values = words(output, count + 2)
    need(values[:2] == [32, count], 'LENS_RESULT_ABI')
    v = values[2:]
    raw = [encode('0x', *v[:6]), encode('0x', v[6])] + [encode('0x', *v[i:i+3]) for i in range(8, len(v), 3)]
    return derive(block, addresses, raw, encode('0x', v[7]), policy)


def call(reader, block, addresses, label):
    """Shares the old reader's count, wall budget, byte budget and evidence ledger."""
    need(re.fullmatch('[a-z0-9_-]{1,90}', label), 'LENS_LABEL')
    need(not reader.stopped and reader.count < reader.max_requests, 'REQUEST_BUDGET_OR_STOPPED')
    need(time.monotonic_ns() - reader.started_ns <= reader.max_seconds * 10**9, 'TIME_BUDGET')
    transaction, block_pin = query(block, addresses)
    reader.count += 1
    payload = {'jsonrpc': '2.0', 'id': reader.count, 'method': 'eth_call', 'params': [transaction, block_pin]}
    row = {'label': label, 'payload': payload, 'started_ns': time.monotonic_ns(), 'started_wall_ns': time.time_ns(),
           'kind': 'fixed_creation_view', 'cohort': addresses}
    reader.records.append(row)
    try:
        raw = reader.transport(payload)
        row.update(received_ns=time.monotonic_ns(), received_wall_ns=time.time_ns())
        reader.total += len(raw)
        need(len(raw) <= MAX_REPLY and reader.total <= MAX_TOTAL, 'RESPONSE_BYTE_BUDGET')
        name = f'{len(reader.records):03d}-{label}.json'
        (reader.folder / name).write_bytes(raw)
        row.update(response_file=name, response_sha256=hashlib.sha256(raw).hexdigest())
        return decode(payload, raw)[0]
    except Exception as error:
        reader.stopped = True
        row['exception'] = type(error).__name__
        if isinstance(error, RpcFailure): row['rpc_error_code'] = error.code
        if isinstance(error, urllib.error.HTTPError): row['http_status'] = error.code
        raise
    finally:
        row['finished_ns'] = time.monotonic_ns()
        (reader.folder / 'requests.json').write_bytes(canonical(reader.records))
