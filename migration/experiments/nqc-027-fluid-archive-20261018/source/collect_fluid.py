"""NQC027: bounded public archive acquisition, not a liquidation or funding test.

Only fixed read RPCs. No account, keys, signatures, state override, transaction
submission, paid endpoint, fallback endpoint, retries or third-party messages.
"""
from __future__ import annotations
import base64, gzip, hashlib, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

REPO = 'josuechavando350-png/nexus-quant-capital'
BASE = '16e352225ba8a6a931834c4edf3d86d9a2924b7d'
BRANCH = 'research/nqc-027-fluid-archive-20261018'
ENDPOINT = 'https://ethereum-rpc.publicnode.com'
PARENT = '0xf57a30121eac97b983cad86fcb3107787a9d400ca4d69d5a96a4b1b618ac65dc'
TARGET = '0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8'
TX = '0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b'
TX0 = '0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0'
POOL = '0xdd72157a021804141817d46d9852a97addfb9f59'
LIQ = '0x52aa899454998be5b000ad077a46bbe360f4e497'
EXECUTOR = '0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd'
EZETH = '0xbf5495efe5db9ce00f80364c8b423567e58d2110'
NATIVE = '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
AMOUNT = 24343983926960874121
MAX_RESPONSE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_CALLS = 12


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def plan():
    pin = {'blockHash': PARENT, 'requireCanonical': True}
    quote = '0x2668dfaa' + ''.join(f'{v:064x}' for v in (1, AMOUNT, 0, 0xdead))
    pairs = [
        ('chain', 'eth_chainId', []),
        ('parent_header', 'eth_getBlockByHash', [PARENT, False]),
        ('pool_code', 'eth_getCode', [POOL, pin]),
        ('liquidity_code', 'eth_getCode', [LIQ, pin]),
        ('constants', 'eth_call', [{'to': POOL, 'data': '0xb7791bf2'}, pin]),
        ('precisions', 'eth_call', [{'to': POOL, 'data': '0x1595cbd3'}, pin]),
        ('quote', 'eth_call', [{'from': EXECUTOR, 'to': POOL, 'value': '0x0', 'data': quote}, pin]),
        ('target_header', 'eth_getBlockByHash', [TARGET, False]),
        ('original_receipt', 'eth_getTransactionReceipt', [TX]),
        ('prefix_transaction', 'eth_getTransactionByHash', [TX0]),
        ('pool_parent_proof', 'eth_getProof', [POOL, ['0x0', '0x1'], pin]),
        ('original_prestate', 'debug_traceTransaction', [TX, {'tracer': 'prestateTracer', 'timeout': '10s', 'tracerConfig': {'diffMode': False}}]),
    ]
    return [{'label': label, 'rpc': {'jsonrpc': '2.0', 'id': i+1, 'method': method, 'params': params}}
            for i, (label, method, params) in enumerate(pairs)]


def validate_request(item):
    # Equality to a frozen allowlist also excludes latest, overrides and broadcasts.
    if type(item) is not dict or item not in plan():
        raise ValueError('request not in frozen public-read plan')
    if type(item['rpc']['id']) is not int:
        raise ValueError('id must be integer')


def decode_words(data, count):
    if type(data) is not str or re.fullmatch(r'0x[0-9a-fA-F]{'+str(count*64)+'}', data) is None:
        raise ValueError('noncanonical ABI result length')
    return [int(data[i:i+64], 16) for i in range(2, len(data), 64)]


def interpret(label, obj):
    if type(obj) is not dict or obj.get('jsonrpc') != '2.0':
        raise ValueError('invalid RPC envelope')
    expected = next(x['rpc']['id'] for x in plan() if x['label'] == label)
    if type(obj.get('id')) is not int or obj['id'] != expected:
        raise ValueError('uncorrelated RPC response')
    if 'error' in obj:
        if 'result' in obj:
            raise ValueError('ambiguous RPC response')
        data = obj['error'].get('data') if type(obj['error']) is dict else None
        if label == 'quote' and type(data) is str and re.fullmatch(r'0xb3bfda99[0-9a-fA-F]{64}', data):
            amount = int(data[10:], 16)
            return {'status': 'QUOTE_ONLY_PARENT_END', 'amount_out_wei': str(amount),
                    'hypothetical_residual_historical_bid_and_gas_wei': str(amount-26039738525656992415-368092735714237547-198416195275125),
                    'all_cost_nqc_profit_wei': None, 'settlement_verified': False}
        raise ValueError('RPC error; stop without retry: ' + json.dumps(obj['error'])[:500])
    value = obj.get('result')
    if value is None:
        raise ValueError('missing/null result, not historical evidence')
    if label == 'chain':
        if value != '0x1': raise ValueError('not Ethereum chain 1')
        return {'status': 'CHAIN_1'}
    if label in ('parent_header', 'target_header'):
        expected_hash, number, stamp = (PARENT, 26190954, 1791983483) if label == 'parent_header' else (TARGET, 26190955, 1791983495)
        if not isinstance(value, dict) or value.get('hash', '').lower() != expected_hash or int(value['number'], 16) != number or int(value['timestamp'], 16) != stamp:
            raise ValueError('historical header mismatch')
        if label == 'target_header' and (value.get('parentHash', '').lower() != PARENT or value['transactions'][:2] != [TX0, TX]):
            raise ValueError('target ancestry/order mismatch')
        return {'status': 'HEADER_FIELDS_MATCH_NOT_CONSENSUS_PROOF', 'state_root': value['stateRoot'], 'hash': value['hash']}
    if label in ('pool_code', 'liquidity_code'):
        if not isinstance(value, str) or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})+', value):
            raise ValueError('no historical runtime')
        raw = bytes.fromhex(value[2:])
        return {'status': 'RUNTIME_OBSERVED', 'bytes': len(raw), 'sha256': sha(raw), 'source_parity': False}
    if label == 'constants':
        w = decode_words(value, 18)
        if w[0] != 21 or w[1] != int(LIQ,16) or w[9] != int(EZETH,16) or w[10] != int(NATIVE,16):
            raise ValueError('pool identity/token mapping mismatch')
        return {'status': 'DEX21_EZETH_TO_NATIVE_MATCH', 'words': [str(x) for x in w]}
    if label == 'precisions':
        w = decode_words(value, 4)
        if min(w) <= 0: raise ValueError('zero precision')
        return {'status': 'PRECISIONS_OBSERVED', 'words': [str(x) for x in w]}
    if label == 'quote':
        raise ValueError('quote must use published custom error, not normal success')
    if label == 'original_receipt':
        if value.get('transactionHash', '').lower() != TX or value.get('blockHash', '').lower() != TARGET or int(value['transactionIndex'],16) != 1 or int(value['status'],16) != 1:
            raise ValueError('wrong original receipt')
        return {'status': 'ORIGINAL_RECEIPT_OBSERVED', 'gas_used': int(value['gasUsed'],16), 'receipt_trie_verified': False}
    if label == 'prefix_transaction':
        if value.get('hash', '').lower() != TX0 or value.get('blockHash', '').lower() != TARGET or int(value['transactionIndex'],16) != 0:
            raise ValueError('wrong prefix transaction')
        return {'status': 'PREFIX_BYTES_OBSERVED_NOT_REPLAYED', 'from': value['from'], 'to': value['to']}
    if label == 'pool_parent_proof':
        if value.get('address', '').lower() != POOL or not value.get('accountProof') or len(value.get('storageProof', [])) != 2:
            raise ValueError('missing pool proof')
        return {'status': 'PROOF_OBSERVED_NOT_YET_VERIFIED', 'storage_items': len(value['storageProof'])}
    if type(value) is not dict or not value or any(not re.fullmatch(r'0x[0-9a-fA-F]{40}', k) for k in value):
        raise ValueError('not a prestateTracer account map')
    return {'status': 'PRE_TX1_PARTIAL_STATE_OBSERVED_NOT_REPLAYED', 'accounts': len(value),
            'pool_present': POOL in {k.lower() for k in value}, 'proof_verified': False}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect refused; endpoint must remain fixed')


def collect(out: Path):
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != 'refs/heads/'+BRANCH or os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise ValueError('only exact NQC research producer, first attempt')
    out.mkdir(parents=True, exist_ok=False)
    result = {'experiment': 'NQC027', 'producer_sha': os.environ.get('GITHUB_SHA'), 'base_sha': BASE,
              'run_id': os.environ.get('GITHUB_RUN_ID'), 'endpoint': ENDPOINT, 'max_calls': MAX_CALLS,
              'stage': 'PARENT_END_DIAGNOSTIC_NOT_NQC_EXECUTION', 'amount_is_historical_seizure_not_preregistered': True,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'observations': [], 'status': 'INCOMPLETE',
              'nqc_opportunity_proven': False, 'funding_verified': False, 'no_recourse_verified': False,
              'nqc_profit_wei': None, 'public_transactions': 0, 'signatures': 0, 'retries': 0}
    (out/'plan.json').write_bytes(canon(plan()))
    opener = build_opener(NoRedirect())
    total = 0
    for index, item in enumerate(plan()):
        validate_request(item)
        if index >= MAX_CALLS: raise ValueError('read budget')
        request_bytes = canon(item['rpc'])
        entry = {'label': item['label'], 'request': item['rpc'], 'endpoint': ENDPOINT,
                 'sent_utc': datetime.now(timezone.utc).isoformat(), 'http_status': None}
        raw = b''
        try:
            req = Request(ENDPOINT, data=request_bytes, headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'NQC-Research-ReadOnly/027'}, method='POST')
            with opener.open(req, timeout=20) as response:
                entry['http_status'] = response.status
                raw = response.read(MAX_RESPONSE+1)
            total += len(raw)
            if len(raw) > MAX_RESPONSE or total > MAX_TOTAL: raise ValueError('response byte budget exceeded')
            entry['parsed'] = interpret(item['label'], json.loads(raw))
            result['observations'].append({'label': item['label'], **entry['parsed']})
        except Exception as error:
            if isinstance(error, HTTPError):
                entry['http_status'] = error.code
                raw = error.read(MAX_RESPONSE+1)
            entry['error'] = type(error).__name__ + ': ' + str(error)[:700]
            result['status'] = 'BLOCKED_NO_RETRY'
            result['blocked_at'] = item['label']
            result['error'] = entry['error']
        entry['received_utc'] = datetime.now(timezone.utc).isoformat()
        entry['raw_bytes'] = len(raw); entry['raw_sha256'] = sha(raw)
        (out/f'{index+1:02d}_{item["label"]}.response').write_bytes(raw)
        (out/f'{index+1:02d}_{item["label"]}.json').write_bytes(canon(entry))
        if 'error' in entry: break
        time.sleep(0.3)
    else:
        result['status'] = 'BOUNDED_READS_COMPLETE_NOT_COMMERCIAL_ADMISSION'
    result['requests_attempted'] = index+1
    result['ended_utc'] = datetime.now(timezone.utc).isoformat()
    (out/'result.json').write_bytes(canon(result))
    bundle = {p.name: {'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),'base64':base64.b64encode(p.read_bytes()).decode()} for p in sorted(out.iterdir()) if p.is_file()}
    gz = gzip.compress(canon(bundle), mtime=0)
    encoded = base64.b64encode(gz).decode()
    parts = [encoded[i:i+4800] for i in range(0,len(encoded),4800)]
    print('NQC027_EXPORT_META '+json.dumps({'gzip_bytes':len(gz),'gzip_sha256':sha(gz),'chunks':len(parts),'files':len(bundle)}), flush=True)
    for i, part in enumerate(parts): print(f'NQC027_CHUNK {i:05d} {part}', flush=True)
    print('NQC027_STATUS '+json.dumps(result,sort_keys=True), flush=True)
    return result


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('one new output directory required')
    collect(Path(sys.argv[1]))
