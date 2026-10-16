import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import transport as t
from benchmark import run, source
from audit_transport import audit
from common import MORPHO, ORACLE, IRM, MARKET_PARAMS, encode

POLICY = json.loads((t.HERE/'policy.json').read_text())
SOURCE = (t.HERE.parent.parent/POLICY['source_path']).read_bytes()
OLD = t.HERE.parent/'robinhood-history-continuation-20261016T0715/evidence/pilot'


class Synthetic:
    def __init__(self, fail=None, bad_json=False, wrong_chain=False, reorg=False, parity=False):
        self.last, self.prefix = {}, b''
        self.fail, self.bad_json, self.wrong_chain, self.reorg, self.parity = fail, bad_json, wrong_chain, reorg, parity
        self.heads = {}
        state = json.loads(SOURCE)['state']
        self.latest = state['through_block']+100
        for value in (state['segments'][0]['start'], state['checkpoint']):
            self.heads[value['number']] = self.raw_header(value)
        self.output = json.loads((OLD/'142-observe-r0-creation.json').read_text())['result']
        self.code = json.loads((t.HERE.parent/'robinhood-real-state-replay-20261016/evidence/provider-capture/08-prestate.json').read_text())['result']

    @staticmethod
    def raw_header(value):
        return {'number':hex(value['number']), 'hash':value['hash'], 'timestamp':hex(value['timestamp']),
                'parentHash':value['parent_hash'], 'stateRoot':value['state_root'], 'baseFeePerGas':hex(value['base_fee_wei'])}

    def __call__(self, mode, payload, seconds):
        self.last, self.prefix = {'mode':mode, 'status':200}, b''
        if payload['id'] == self.fail:
            if self.bad_json:
                self.prefix = b'not-json'
                return self.prefix
            self.last['status'] = 429
            self.prefix = b'{"error":"synthetic quota"}'
            raise OSError('synthetic failure')
        method, params = payload['method'], payload['params']
        if method == 'eth_chainId':
            result = hex(1 if self.wrong_chain else 4663)
        elif method == 'eth_getBlockByNumber':
            number = params[0]
            if number == 'latest':
                self.latest += 100
                result = {'number':hex(self.latest), 'hash':'0x'+f'{self.latest:064x}', 'timestamp':hex(int(time.time())),
                          'parentHash':'0x'+'0'*64, 'stateRoot':'0x'+'1'*64, 'baseFeePerGas':'0x1'}
                self.heads[self.latest] = result
            else:
                result = copy.deepcopy(self.heads[int(number,16)])
                if self.reorg and payload['id'] == 3:
                    result['hash'] = '0x'+'f'*64
        elif method == 'eth_getCode':
            result = self.code[params[0]]['code']
        elif method == 'eth_call' and 'to' in params[0]:
            result = encode('0x', *MARKET_PARAMS)
        else:
            result = self.output
            if self.parity and mode == 'fresh':
                # Alter last collateral word, retain valid ABI.
                result = result[:-64]+f'{int(result[-64:],16)+1:064x}'
        self.prefix = t.canonical({'jsonrpc':'2.0','id':payload['id'],'result':result})
        return self.prefix


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    hits = []
    behavior = 'ok'
    def log_message(self, *_):
        pass
    def handle(self):
        try:
            super().handle()
        except ConnectionResetError:
            # Expected when the bounded client closes an oversized test body.
            pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        self.hits.append((self.client_address[1], dict(self.headers)))
        if self.behavior == 'disconnect':
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if self.behavior == 'timeout':
            time.sleep(.15)
        status = int(self.behavior) if self.behavior.isdigit() else 200
        data = b'x'*(t.MAX_REPLY+20) if self.behavior == 'large' else body
        if self.behavior == 'truncated':
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)+100))
            self.end_headers()
            self.wfile.write(body); self.wfile.flush()
            self.close_connection = True
            return
        self.send_response(status)
        if self.behavior == 'encoded':
            self.send_header('Content-Encoding', 'gzip')
        if status == 302:
            self.send_header('Location', '/must-not-follow')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


class NetworkTests(unittest.TestCase):
    def setUp(self):
        Handler.hits, Handler.behavior = [], 'ok'
        self.server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/'
        self.endpoint = patch.object(t, 'ENDPOINT', self.url)
        self.endpoint.start()
        self.proxy = patch.dict('os.environ', {'NO_PROXY':'127.0.0.1','no_proxy':'127.0.0.1'})
        self.proxy.start()
        self.transport = t.Transports()
    def tearDown(self):
        self.transport.close()
        self.endpoint.stop(); self.proxy.stop()
        self.server.shutdown(); self.server.server_close(); self.thread.join()
    def test_persistent_reuses_actual_client_socket(self):
        self.transport('persistent', {'a':1})
        self.assertFalse(self.transport.last['client_socket_reused'])
        self.transport('persistent', {'a':2})
        self.assertTrue(self.transport.last['client_socket_reused'])
        self.assertEqual(Handler.hits[0][0], Handler.hits[1][0])
    def test_fresh_opens_new_socket(self):
        self.transport('fresh', {'a':1}); self.transport('fresh', {'a':2})
        self.assertFalse(self.transport.last['client_socket_reused'])
        self.assertNotEqual(Handler.hits[0][0], Handler.hits[1][0])
    def test_redirect_and_quota_never_follow_or_retry(self):
        for behavior in ('302','429','503'):
            with self.subTest(status=behavior):
                Handler.behavior = behavior
                before = len(Handler.hits)
                with self.assertRaisesRegex(ValueError, 'HTTP_STATUS_'):
                    self.transport('persistent', {'a':1})
                self.assertEqual(len(Handler.hits), before+1)
                self.assertEqual(self.transport.prefix, t.canonical({'a':1}))
    def test_disconnect_does_not_retry(self):
        Handler.behavior = 'disconnect'
        with self.assertRaises(Exception):
            self.transport('persistent', {'a':1})
        self.assertEqual(len(Handler.hits), 1)
    def test_response_cap_preserves_bounded_prefix(self):
        Handler.behavior = 'large'
        with self.assertRaisesRegex(ValueError, 'RESPONSE_BYTE_BUDGET'):
            self.transport('persistent', {'a':1})
        self.assertEqual(len(self.transport.prefix), t.MAX_REPLY+1)
        self.assertEqual(len(Handler.hits), 1)
    def test_wall_timeout_no_retry(self):
        Handler.behavior = 'timeout'
        started = time.monotonic()
        with self.assertRaises(Exception):
            self.transport('persistent', {'a':1}, .03)
        self.assertLess(time.monotonic()-started, .14)
        self.assertEqual(len(Handler.hits), 1)
    def test_truncated_body_keeps_returned_prefix(self):
        Handler.behavior = 'truncated'
        with self.assertRaises(Exception):
            self.transport('persistent', {'a':1})
        self.assertEqual(self.transport.prefix, t.canonical({'a':1}))
        self.assertEqual(len(Handler.hits), 1)
    def test_unexpected_encoding_stops_without_decompression(self):
        Handler.behavior = 'encoded'
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_CONTENT_ENCODING'):
            self.transport('persistent', {'a':1})
        self.assertEqual(self.transport.prefix, t.canonical({'a':1}))
    def test_no_netrc_or_cookies_and_proxy_settings_are_retained(self):
        with patch('requests.sessions.get_netrc_auth', side_effect=AssertionError('netrc read')):
            self.transport('persistent', {'a':1})
        headers = {k.lower():v for k,v in Handler.hits[0][1].items()}
        self.assertNotIn('authorization',headers); self.assertNotIn('cookie',headers)
        active = t.session()
        try:
            with patch.dict('os.environ', {'HTTPS_PROXY':'http://example.invalid:8080', 'https_proxy':'http://example.invalid:8080', 'NO_PROXY':'','no_proxy':'', 'REQUESTS_CA_BUNDLE':'/test/ca.pem'}):
                settings = active.merge_environment_settings('https://example.test/',{},True,None,None)
                self.assertEqual(settings['proxies']['https'], 'http://example.invalid:8080')
                self.assertEqual(settings['verify'], '/test/ca.pem')
            retries = active.get_adapter('https://').max_retries
            self.assertEqual((retries.total,retries.connect,retries.read,retries.redirect,retries.status,retries.other),(0,0,0,0,0,0))
            self.assertFalse(retries.respect_retry_after_header)
        finally:
            active.close()


class ProtocolTests(unittest.TestCase):
    def capture(self, directory, synthetic=None, policy=None):
        policy = policy or POLICY
        reader = t.Reader(directory, policy, synthetic or Synthetic())
        journal = t.Journal(reader.folder)
        (reader.folder/'source-registry.json').write_bytes(SOURCE)
        try:
            run(reader,journal.append,policy,'a'*40,SOURCE)
        except Exception as error:
            reason = str(error) if isinstance(error, ValueError) else type(error).__name__
            journal.append('stopped',{'exception':type(error).__name__,'reason':reason,
                'rpc_calls':reader.count,'http_requests':len(reader.records),'realized_profit':None})
        return reader
    def test_complete_and_all_49_failure_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.capture(Path(tmp)/'complete')
            result = audit(Path(tmp)/'complete')
            self.assertEqual((result['rpc_calls'],result['completed_triads'],len(result['reads'])), (49,6,18))
            for fault in range(1,50):
                with self.subTest(fault=fault):
                    path = Path(tmp)/str(fault)
                    reader = self.capture(path,Synthetic(fail=fault))
                    result = audit(path)
                    self.assertEqual(result['status'],'stopped')
                    self.assertEqual(reader.count,fault)
                    self.assertEqual(result['rpc_calls'],fault)
    def test_json_wrong_chain_reorg_and_parity_stops(self):
        cases = [Synthetic(fail=1,bad_json=True),Synthetic(fail=10,bad_json=True),
                 Synthetic(wrong_chain=True),Synthetic(reorg=True),Synthetic(parity=True)]
        with tempfile.TemporaryDirectory() as tmp:
            for index, synthetic in enumerate(cases):
                path = Path(tmp)/str(index)
                self.capture(path,synthetic)
                self.assertEqual(audit(path)['status'],'stopped')
    def test_source_hash_and_illegal_methods_before_rpc(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_FILE_HASH'):
            source(POLICY,SOURCE+b' ')
        with tempfile.TemporaryDirectory() as tmp:
            reader = t.Reader(Path(tmp)/'p',POLICY,Synthetic())
            with self.assertRaisesRegex(ValueError,'METHOD_NOT_ALLOWED'):
                reader.call('eth_sendRawTransaction',['0x'],'bad')
            self.assertEqual(reader.count,0)
    def test_request_time_and_stop_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = t.Reader(Path(tmp)/'p',dict(POLICY,max_requests=1),Synthetic())
            reader.call('eth_chainId',[],'a')
            with self.assertRaisesRegex(ValueError,'REQUEST_BUDGET_OR_STOPPED'):
                reader.call('eth_chainId',[],'b')
            other = t.Reader(Path(tmp)/'q',POLICY,Synthetic())
            other.started_ns -= 901*10**9
            with self.assertRaisesRegex(ValueError,'TIME_BUDGET'):
                other.call('eth_chainId',[],'a')
            self.assertEqual(other.count,0)
            failed = t.Reader(Path(tmp)/'r',POLICY,Synthetic(fail=1))
            with self.assertRaises(OSError):
                failed.call('eth_chainId',[],'a')
            with self.assertRaisesRegex(ValueError,'REQUEST_BUDGET_OR_STOPPED'):
                failed.call('eth_chainId',[],'b')
            self.assertEqual(failed.count,1)
    def test_total_byte_budget_preserves_failing_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = t.Reader(Path(tmp)/'p',POLICY,Synthetic())
            reader.total = t.MAX_TOTAL
            with self.assertRaisesRegex(ValueError,'RESPONSE_BYTE_BUDGET'):
                reader.call('eth_chainId',[],'a')
            self.assertTrue(reader.stopped)
            self.assertTrue((reader.folder/reader.records[0]['response_file']).exists())
    def test_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'p'; self.capture(path)
            rows = json.loads((path/'requests.json').read_text())
            rows[8]['mode'] = 'persistent'
            (path/'requests.json').write_bytes(t.canonical(rows))
            with self.assertRaisesRegex(ValueError,'REPLAY_REQUEST_DIFFERS'):
                audit(path)
    def test_response_hash_and_journal_timing_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'p'; self.capture(path)
            file = path/'001-chain.json'
            file.write_bytes(file.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'RESPONSE_HASH'):
                audit(path)
            other = Path(tmp)/'q'; self.capture(other)
            journal = [json.loads(x) for x in (other/'journal.jsonl').read_text().splitlines()]
            next(row for row in journal if row['kind']=='read_completed')['data']['input_ms'] += 1
            # Rehashing cannot conceal a derived-metric change from replay.
            previous = '0'*64
            import hashlib
            for row in journal:
                row['previous_sha256'] = previous; row.pop('sha256')
                row['sha256'] = hashlib.sha256(t.canonical(row)).hexdigest(); previous = row['sha256']
            (other/'journal.jsonl').write_bytes(b''.join(t.canonical(row) for row in journal))
            with self.assertRaisesRegex(ValueError,'JOURNAL_REPLAY_DIFFERS'):
                audit(other)


if __name__ == '__main__':
    unittest.main()
