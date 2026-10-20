"""Reviewed one-shot archive capability check; reuse the unchanged economic tests.
This driver changes only transport policy and adds a preflight. No state injection,
transaction signing, broadcasting, deployment on a public network or paid API.
"""
from pathlib import Path
import base64
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request

import rpc_guard as rg

ENDPOINT = 'https://eth.drpc.org/'
PARENT_HASH = '0xc3b1f4fe26e6743df8727eceec10c536b33db580b3346fa87e731d888ca5f4d3'
TARGET_HASH = '0x2702da91c548f69a98373525ae8409c6bd28189439bb53f2acb971a029ac5882'
V2 = '0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc'
R0 = 38669555298186
R1 = 16417414753955494219446
OLD_UPSTREAM = 'https://ethereum-rpc.publicnode.com'


def require(condition, message):
    if not condition:
        raise rg.Closed(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise rg.Closed('Redirect refused; no alternate upstream')


def configure_transport():
    require(rg.UPSTREAM == OLD_UPSTREAM, 'Unexpected original transport')
    rg.UPSTREAM = ENDPOINT
    rg.MAX_READS = 600
    rg.MAX_SECONDS = 420
    rg.MAX_BYTES = 2 * 1024 * 1024


def bounded_opener():
    opener = urllib.request.build_opener(NoRedirect())
    used_bytes = 0

    def open_once(request, timeout):
        nonlocal used_bytes
        require(request.full_url == ENDPOINT, 'Wrong upstream')
        require(request.get_method() == 'POST', 'Wrong transport verb')
        with opener.open(request, timeout=timeout) as response:
            require(response.geturl() == ENDPOINT, 'Upstream URL changed')
            raw = response.read(rg.MAX_BYTES + 1)
            used_bytes += len(raw)
            require(used_bytes <= 16 * 1024 * 1024, 'Total response budget exceeded')
            result = io.BytesIO(raw)
            result.status = response.status
            return result
    return open_once


def receipt_identity(receipt, tx_hash, index):
    require(isinstance(receipt, dict), 'Receipt object missing')
    require(receipt.get('transactionHash', '').lower() == tx_hash, 'Receipt tx mismatch')
    require(receipt.get('blockHash', '').lower() == TARGET_HASH, 'Receipt block mismatch')
    require(int(receipt.get('blockNumber', '0x0'), 16) == rg.TARGET, 'Receipt height mismatch')
    require(int(receipt.get('transactionIndex', '0xff'), 16) == index, 'Receipt index mismatch')
    require(receipt.get('status') == '0x1', 'Original/prefix failed: investigate')
    require(isinstance(receipt.get('logs'), list), 'Complete receipt logs missing')
    if index == 1:
        require(int(receipt.get('gasUsed', '0x0'), 16) == 602029, 'Original gas mismatch')
        require(int(receipt.get('effectiveGasPrice', '0x0'), 16) == 302819782345,
                'Original effective gas price mismatch')
        require(len(receipt['logs']) == 11, 'Original event count mismatch')
    return True


def preflight(guard):
    require(guard.call('eth_chainId', []) == '0x1', 'Wrong network')
    receipt = guard.call('eth_getTransactionReceipt', [rg.TX])
    receipt_identity(receipt, rg.TX, 1)
    parent = guard.call('eth_getBlockByNumber', [hex(rg.PARENT), False])
    target = guard.call('eth_getBlockByNumber', [hex(rg.TARGET), False])
    require(parent['hash'].lower() == PARENT_HASH, 'Parent hash mismatch')
    require(target['hash'].lower() == TARGET_HASH and target['parentHash'].lower() == PARENT_HASH,
            'Historical block identity mismatch')
    require(int(target['timestamp'], 16) == 1738548455, 'Historical timestamp mismatch')
    require(int(target['baseFeePerGas'], 16) == 302819782345, 'Historical base fee mismatch')
    require(len(target['transactions']) == 41 and
            [x.lower() for x in target['transactions'][:2]] == [rg.PREFIX, rg.TX],
            'Block prefix/target mismatch')
    prefix_receipt = guard.call('eth_getTransactionReceipt', [rg.PREFIX])
    receipt_identity(prefix_receipt, rg.PREFIX, 0)
    for tx_hash, index in ((rg.PREFIX, 0), (rg.TX, 1)):
        tx = guard.call('eth_getTransactionByHash', [tx_hash])
        require(tx['hash'].lower() == tx_hash and tx['blockHash'].lower() == TARGET_HASH and
                int(tx['transactionIndex'], 16) == index, 'Transaction identity mismatch')
        require(isinstance(tx.get('input'), str) and tx['input'].startswith('0x'), 'Missing calldata')
    code = guard.call('eth_getCode', [V2, hex(rg.PARENT)])
    require(isinstance(code, str) and len(code) > 2, 'Historical V2 code absent')
    slot = guard.call('eth_getStorageAt', [V2, '0x8', hex(rg.PARENT)])
    require(isinstance(slot, str) and len(slot) == 66, 'Malformed historical storage')
    # This is the parent state, not the pre-TX1 state. Do NOT require historical
    # TX1 reserves here; the prefix may change them. Foundry tests check after prefix.
    return {'receipt_present': True, 'prefix_receipt_present': True,
            'block_and_order_verified': True, 'parent_v2_code_bytes': (len(code) - 2) // 2,
            'parent_v2_code_sha256': hashlib.sha256(bytes.fromhex(code[2:])).hexdigest(),
            'parent_slot8_present': True, 'full_historical_state_proven': False,
            'canonical_consensus_independently_verified': False}


def emit_evidence(directory):
    files = {}
    for p in sorted(directory.glob('*')):
        if p.is_file():
            files[p.name] = base64.b64encode(p.read_bytes()).decode()
    raw = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > 4 * 1024 * 1024:
        print('EVIDENCE_EXPORT_INCOMPLETE compressed log budget exceeded', flush=True)
        return False
    encoded = base64.b64encode(compressed).decode()
    chunks = [encoded[i:i + 2000] for i in range(0, len(encoded), 2000)]
    print('NQC_EVIDENCE_MANIFEST ' + json.dumps({'format': 'base64-gzip-json-base64-files',
          'sha256': hashlib.sha256(compressed).hexdigest(), 'bytes': len(compressed),
          'chunks': len(chunks), 'files': list(files)}), flush=True)
    for i, chunk in enumerate(chunks):
        print('NQC_EVIDENCE_CHUNK ' + str(i) + ' ' + chunk, flush=True)
    return True


def main():
    configure_transport()
    out = Path(__file__).resolve().parent / 'evidence_run'
    out.mkdir(exist_ok=True)
    guard = rg.Guard(out, opener=bounded_opener())
    report = {'schema': 'nqc-reviewed-archive-replay-attempt-v1', 'endpoint': ENDPOINT,
              'producer_sha': os.environ.get('GITHUB_SHA'), 'preflight_passed': False,
              'baseline_replayed': False, 'variant_executed': False, 'commercial_admission': False,
              'realized_NQC_profit': None, 'sponsor_accepted': False}
    rc = 2
    try:
        report['preflight'] = preflight(guard)
        report['preflight_passed'] = True
        print('ARCHIVE_PREFLIGHT ' + json.dumps(report['preflight']), flush=True)
        import run_replay as runner
        # Reuse one cache, budget and stop flag; do not reset or repeat upstream reads.
        runner.Guard = lambda directory: guard
        rc = runner.main()
        report['baseline_replayed'] = runner.result['baseline_replayed']
        report['variant_executed'] = runner.result['variant_tested']
        report['all_variant_tests_pass'] = runner.result['all_variant_tests_pass']
        report['full_economic_receipt_cost'] = runner.result['complete_receipt_cost']
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        print('ARCHIVE_STOP ' + report['error'], flush=True)
    finally:
        report['rpc'] = guard.summary()
        (out / 'ARCHIVE_RESULT.json').write_text(json.dumps(report, indent=2))
        report['raw_evidence_exported_to_log'] = emit_evidence(out)
        print('ARCHIVE_RESULT ' + json.dumps(report, sort_keys=True), flush=True)
    return rc


class OfflineTests(unittest.TestCase):
    def valid_receipt(self):
        return {'transactionHash': rg.TX, 'blockHash': TARGET_HASH,
                'blockNumber': hex(rg.TARGET), 'transactionIndex': '0x1', 'status': '0x1',
                'gasUsed': hex(602029), 'effectiveGasPrice': hex(302819782345), 'logs': [{}] * 11}

    def test_receipt_valid(self):
        self.assertTrue(receipt_identity(self.valid_receipt(), rg.TX, 1))

    def test_receipt_conflicts_fail(self):
        for key, value in [('blockHash', '0x' + '00' * 32), ('status', '0x0'),
                           ('transactionIndex', '0x2'), ('gasUsed', '0x1'),
                           ('effectiveGasPrice', '0x1'), ('logs', [])]:
            with self.subTest(key=key):
                r = self.valid_receipt(); r[key] = value
                with self.assertRaises(rg.Closed): receipt_identity(r, rg.TX, 1)

    def test_null_stops_preflight(self):
        calls = []
        def opener(request, timeout):
            q = json.loads(request.data); calls.append(q['method'])
            response = io.BytesIO(json.dumps({'jsonrpc': '2.0', 'id': q['id'],
                       'result': '0x1' if q['id'] == 1 else None}).encode())
            response.status = 200
            return response
        with tempfile.TemporaryDirectory() as d:
            g = rg.Guard(Path(d), opener=opener, sleep=lambda _: None)
            with self.assertRaises(rg.Closed): preflight(g)
            with self.assertRaises(rg.Closed): g.call('eth_chainId', [])
            self.assertEqual(calls, ['eth_chainId', 'eth_getTransactionReceipt'])

    def test_no_redirect(self):
        with self.assertRaises(rg.Closed):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid')

    def test_no_write_permission(self):
        for m in ('eth_sendRawTransaction', 'eth_sendTransaction', 'anvil_setBalance',
                  'debug_traceTransaction', 'eth_call', 'eth_sign'):
            with self.assertRaises(rg.Closed): rg.validate(m, [])

    def test_raw_evidence_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d); (path / 'a.json').write_bytes(b'{"result":null}\n')
            from contextlib import redirect_stdout
            text = io.StringIO()
            with redirect_stdout(text): self.assertTrue(emit_evidence(path))
            lines = text.getvalue().splitlines()
            meta = json.loads(lines[0].split(' ', 1)[1])
            enc = ''.join(line.split(' ', 2)[2] for line in lines[1:])
            data = base64.b64decode(enc)
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta['sha256'])
            saved = json.loads(gzip.decompress(data))
            self.assertEqual(base64.b64decode(saved['a.json']), b'{"result":null}\n')

if __name__ == '__main__':
    if sys.argv[1:] == ['--offline-test']:
        unittest.main(argv=[sys.argv[0]], verbosity=2)
    elif not sys.argv[1:]:
        raise SystemExit(main())
    else:
        raise SystemExit('Unsupported arguments; no provider override allowed')
