"""Sequential, no-retry transport experiment. No transaction sending API."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import signal
import sys
import time
import urllib.error

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'robinhood-history-backfill-20261016'))
from support import need, canonical, qty, header, pin, registry, Journal, MAX_REPLY, MAX_TOTAL
from rpc_batch import validate, decode, network
from common import ENDPOINT, RpcFailure
import lens
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

MODES = ('legacy', 'fresh', 'persistent')


@contextmanager
def deadline(seconds):
    """Main-thread POSIX wall deadline, including DNS, TLS, headers and body."""
    need(seconds > 0 and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'DEADLINE_CONFIGURATION')
    def expired(*_):
        raise TimeoutError('HTTP_OR_RUN_DEADLINE')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def session():
    value = requests.Session()
    value.trust_env = True
    retries = Retry(total=0, connect=0, read=0, redirect=0, status=0, other=0,
                    respect_retry_after_header=False)
    for prefix in ('https://', 'http://'):
        value.mount(prefix, HTTPAdapter(pool_connections=1, pool_maxsize=1,
                                       max_retries=retries, pool_block=True))
    return value


class Transports:
    def __init__(self):
        self.retained = None
        self.persistent_calls = 0
        self.sockets = []  # Retain object references: avoid ID/descriptor reuse ambiguity.
        self.last = {}
        self.prefix = b''

    def close(self):
        if self.retained is not None:
            self.retained.close()

    def __call__(self, mode, payload, seconds=20):
        need(mode in MODES, 'TRANSPORT_MODE')
        self.last, self.prefix = {'mode': mode}, b''
        with deadline(seconds):
            if mode == 'legacy':
                try:
                    self.prefix = network(payload)
                    self.last['status'] = 200
                except urllib.error.HTTPError as error:
                    self.last['status'] = error.code
                    try:
                        self.prefix = error.read(MAX_REPLY + 1)
                    finally:
                        error.close()
                    raise
                return self.prefix
            fresh = mode == 'fresh'
            if fresh:
                active = session()
            else:
                if self.retained is None:
                    self.retained = session()
                active = self.retained
                self.persistent_calls += 1
            self.last['session_request_number'] = 1 if fresh else self.persistent_calls
            try:
                # Request.prepare avoids implicit .netrc credentials and cookie state.
                prepared = requests.Request('POST', ENDPOINT, data=canonical(payload),
                    headers={'Content-Type': 'application/json', 'Accept-Encoding': 'identity',
                             'User-Agent': 'Python-urllib/' + '.'.join(map(str, sys.version_info[:2]))}).prepare()
                settings = active.merge_environment_settings(ENDPOINT, {}, True, None, None)
                need(settings['verify'] is not False and settings['cert'] is None, 'TLS_CONFIGURATION')
                self.last['proxy_configured'] = bool(requests.utils.select_proxy(ENDPOINT, settings['proxies']))
                # Public adapter API: never Session.send, whose redirect bookkeeping
                # can consume an unbounded redirect body even with allow_redirects=False.
                with active.get_adapter(ENDPOINT).send(prepared, timeout=(seconds, seconds), **settings) as response:
                    self.last['status'] = response.status_code
                    self.last['connection_close'] = response.headers.get('Connection', '').lower() == 'close'
                    conn = response.raw.connection
                    sock = getattr(conn, 'sock', None)
                    if sock is not None:
                        match = next((i for i, prior in enumerate(self.sockets) if prior is sock), None)
                        reused = match is not None
                        if not reused:
                            self.sockets.append(sock)
                            match = len(self.sockets)-1
                        self.last.update(client_socket_tag=match+1, client_socket_reused=reused)
                    else:
                        self.last.update(client_socket_tag=None, client_socket_reused=None)
                    # Bounded undecoded prefix; no compressed-body expansion.
                    while len(self.prefix) <= MAX_REPLY:
                        chunk = response.raw.read1(min(65536, MAX_REPLY+1-len(self.prefix)), decode_content=False)
                        if not chunk:
                            break
                        self.prefix += chunk
                    need(len(self.prefix) <= MAX_REPLY, 'RESPONSE_BYTE_BUDGET')
                    need(response.headers.get('Content-Encoding', 'identity').lower() in ('', 'identity'), 'UNEXPECTED_CONTENT_ENCODING')
                    need(response.status_code == 200, 'HTTP_STATUS_' + str(response.status_code))
                    return self.prefix
            finally:
                if fresh:
                    active.close()


class Reader:
    def __init__(self, folder, policy, transports=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.policy, self.transports = policy, transports or Transports()
        self.started_ns = time.monotonic_ns()
        self.records, self.count, self.total, self.stopped = [], 0, 0, False
        self.mode = 'legacy'

    def request(self, method, params, label, creation=None):
        if creation is None:
            validate(method, params)
        else:
            block, addresses = creation
            need(method == 'eth_call' and params == list(lens.query(block, addresses)), 'FIXED_LENS_QUERY')
        need(re.fullmatch('[a-z0-9_-]{1,90}', label), 'REQUEST_LABEL')
        need(not self.stopped and self.count < self.policy['max_requests'], 'REQUEST_BUDGET_OR_STOPPED')
        remaining = self.policy['max_run_seconds']-(time.monotonic_ns()-self.started_ns)/1e9
        need(remaining > 0, 'TIME_BUDGET')
        self.count += 1
        payload = {'jsonrpc': '2.0', 'id': self.count, 'method': method, 'params': params}
        row = {'label': label, 'mode': self.mode, 'payload': payload,
               'started_ns': time.monotonic_ns(), 'started_wall_ns': time.time_ns()}
        self.records.append(row)
        raw = None
        try:
            raw = self.transports(self.mode, payload, min(20, remaining))
            row.update(received_ns=time.monotonic_ns(), received_wall_ns=time.time_ns())
            self.total += len(raw)
            need(len(raw) <= MAX_REPLY and self.total <= MAX_TOTAL, 'RESPONSE_BYTE_BUDGET')
            return decode(payload, raw)[0]
        except Exception as error:
            self.stopped = True
            row['exception'] = type(error).__name__
            if isinstance(error, RpcFailure):
                row['rpc_error_code'] = error.code
            raise
        finally:
            row['transport'] = dict(self.transports.last)
            preserved = raw if raw is not None else self.transports.prefix
            if preserved:
                filename = f'{self.count:03d}-{label}.json'
                (self.folder/filename).write_bytes(preserved)
                row.update(response_file=filename, response_sha256=hashlib.sha256(preserved).hexdigest(),
                           response_bytes=len(preserved), response_complete=raw is not None)
            row['finished_ns'] = time.monotonic_ns()
            (self.folder/'requests.json').write_bytes(canonical(self.records))

    def call(self, method, params, label):
        return self.request(method, params, label)

    def many(self, queries, label, mode=None):
        return [self.call(method, params, f'{label}-{i}') for i, (method, params) in enumerate(queries)]

    def creation(self, block, addresses, label):
        return self.request('eth_call', list(lens.query(block, addresses)), label, (block, addresses))

    def verified(self):
        """Called only after decoding and comparing the canonical header."""
        stamp = time.monotonic_ns()
        self.records[-1]['verified_ns'] = stamp
        (self.folder/'requests.json').write_bytes(canonical(self.records))
        return stamp
