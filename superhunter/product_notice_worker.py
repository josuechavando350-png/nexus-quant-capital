"""Serve a single wheel-notice index inside a disposable loopback namespace."""
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from .product_guac_worker import enable_private_loopback
from .product_notice_search import VERSION

COLLECTION = '/collections/notices'


def request(method, path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = Request('http://127.0.0.1:6333' + path, method=method, data=body,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as res:
        raw = res.read(4 * 1024**2 + 1)
    if len(raw) > 4 * 1024**2:
        raise ValueError('oversized notice index response')
    return json.loads(raw)


def check_points(points):
    stored = request('POST', COLLECTION + '/points/scroll',
                     {'limit': len(points), 'with_payload': True, 'with_vector': True})['result']
    if stored['next_page_offset'] is not None:
        raise ValueError('unexpected data in notice index')
    actual = sorted(stored['points'], key=lambda p: p['id'])
    if [{k: p[k] for k in ('id', 'vector', 'payload')} for p in actual] != points:
        raise ValueError('stored notice vectors or hashes differ')


def main(parent_net):
    enable_private_loopback(parent_net)
    points = json.loads(Path('points.json').read_bytes())
    env = {'HOME': str(Path.cwd()), 'PATH': '/usr/bin:/bin', 'QDRANT__SERVICE__HOST': '127.0.0.1',
           'QDRANT__SERVICE__MAX_WORKERS': '2', 'QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS': '2',
           'QDRANT__TELEMETRY_DISABLED': 'true'}
    with subprocess.Popen(['./qdrant', '--disable-telemetry'], env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as server:
        try:
            for _ in range(120):
                if server.poll() is not None:
                    raise RuntimeError('Qdrant exited during startup')
                try:
                    version = request('GET', '/').get('version')
                    break
                except URLError:
                    time.sleep(.1)
            else:
                raise RuntimeError('private notice index startup timed out')
            if version != VERSION:
                raise ValueError('unexpected Qdrant version')
            request('PUT', COLLECTION, {'vectors': {}, 'sparse_vectors': {'terms': {}}})
            request('PUT', COLLECTION + '/points?wait=true', {'points': points})
            check_points(points)
            print(json.dumps({'version': version, 'indexed': len(points)}), flush=True)
            for line in sys.stdin.buffer:
                vector = json.loads(line)
                data = {'using': 'terms', 'query': vector, 'limit': len(points), 'with_payload': True}
                hits = request('POST', COLLECTION + '/points/query', data)['result']['points']
                print(json.dumps({'hits': hits}), flush=True)
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
