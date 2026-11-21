"""Native HTTP framing and JS route extraction from fixed NQC-owned responses."""
import gzip
from pathlib import Path
import subprocess
import sys
import tempfile

from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'mitmproxy/mitmproxy': 'executable', 'xnl-h4ck3r/xnLinkFinder': 'executable'}
LOCK = 'superhunter/product_supply/http-native-linux-py312.txt'
LOCK_SHA = '1d25bfdfa17bf904368ca79dfb1d6ee3df8d3cd3e0d675c0643cd5ee02004725'
PROOFS = 'superhunter/product_supply/http-native-sources.json'
PROOFS_SHA = '084d50bd07d388af6194dde0722d7b865d6033a15c86463990769df2cb6750c8'
JS = ('const catalogPath = "/api/catalog?limit=10&cursor=owned";\n'
      'fetch("/api/positions?owner=alice");\n'
      'const encodedPath = "\\u002fapi\\u002fstatus";\n')


def inputs():
    bodies = {'base': JS, 'changed': JS.replace('/api/positions?owner=alice', '/api/exposures?account_id=alice'),
              'duplicates': JS + 'fetch("/api/positions?owner=alice");\n',
              'no_routes': '/* OWNED response with no routes */\n"ready";\n"application/json";\n"/=ignored";\n'}
    messages = {
        'clean_get': ('GET /api/catalog?limit=10 HTTP/1.1', [], ''),
        'clean_post': ('POST /api/positions HTTP/1.1', ['Content-Length: 2'], '{}'),
        'clean_chunked': ('POST /api/catalog HTTP/1.1', ['Transfer-Encoding: chunked'], '0\r\n\r\n'),
        'both_lengths': ('POST /api/catalog HTTP/1.1', ['Content-Length: 0', 'Transfer-Encoding: chunked'], ''),
        'duplicate_length': ('POST /api/catalog HTTP/1.1', ['Content-Length: 2', 'Content-Length: 2'], '{}'),
        'conflicting_length': ('POST /api/catalog HTTP/1.1', ['Content-Length: 2', 'Content-Length: 3'], '{}'),
        'negative_length': ('POST /api/catalog HTTP/1.1', ['Content-Length: -1'], ''),
        'duplicate_encoding': ('POST /api/catalog HTTP/1.1', ['Transfer-Encoding: chunked', 'Transfer-Encoding: gzip'], ''),
        'wrong_encoding_order': ('POST /api/catalog HTTP/1.1', ['Transfer-Encoding: chunked, gzip'], ''),
        'http10_encoding': ('POST /api/catalog HTTP/1.0', ['Transfer-Encoding: chunked'], ''),
        'invalid_header_name': ('GET /api/catalog HTTP/1.1', ['Content Length: 0'], ''),
        'invalid_version': ('GET /api/catalog HTP/1.1', [], ''),
    }
    requests = {name: ('\r\n'.join([start, 'Host: owned.invalid', *headers]) + '\r\n\r\n' + body).encode().hex()
                for name, (start, headers, body) in messages.items()}
    responses = {}
    for name, body in bodies.items():
        compressed = gzip.compress(body.encode(), mtime=0)
        header = ('HTTP/1.1 200 OK\r\nContent-Type: application/javascript; charset=utf-8\r\n'
                  'Content-Encoding: gzip\r\nContent-Length: ' + str(len(compressed)) + '\r\n\r\n').encode()
        responses[name] = (header + compressed).hex()
        if name == 'base':
            damaged = bytearray(compressed)
            damaged[-8] ^= 1  # Corrupt CRC32 while retaining the exact framing length.
            responses['corrupt_gzip'] = (header + damaged).hex()
    return {'requests': requests, 'responses': responses}, bodies


def source_proofs():
    raw = read_artifact(ROOT, PROOFS)
    if sha(raw) != PROOFS_SHA:
        raise EvidenceError('HTTP native source proof differs')
    return strict_json(raw)


def verify_installed(work, proofs):
    counts = {}
    for package, entry in proofs.items():
        expected = entry['python_git_blobs']
        actual = {p.relative_to(work/'lib').as_posix() for p in (work/'lib'/package).rglob('*.py')}
        if set(expected) != actual:
            raise EvidenceError('HTTP native Python module membership differs')
        for name, digest in expected.items():
            if git_object('blob', read_artifact(work/'lib', name)) != digest:
                raise EvidenceError('HTTP native producer differs from the catalog source')
        counts[package] = {'python_files': len(actual), 'byte_identical_git_blobs': len(actual)}
    return counts


def validate_http(native, payload, bodies):
    if set(native) != {'requests', 'responses', 'version', 'network_events'}:
        raise EvidenceError('HTTP parser report fields differ')
    if native['version'] != '13.0.0.dev0' or native['network_events']:
        raise EvidenceError('HTTP parser version or offline boundary differs')
    if set(native['requests']) != set(payload['requests']) or set(native['responses']) != set(payload['responses']):
        raise EvidenceError('HTTP parser control coverage differs')
    errors = {
        'both_lengths': 'message with both transfer-encoding and content-length headers',
        'duplicate_length': "multiple content-length headers: [b'2', b'2']",
        'conflicting_length': "multiple content-length headers: [b'2', b'3']",
        'negative_length': "invalid content-length header: b'-1'",
        'duplicate_encoding': "multiple transfer-encoding headers: [b'chunked', b'gzip']",
        'wrong_encoding_order': "unknown transfer-encoding header: b'chunked, gzip'",
        'http10_encoding': "unexpected HTTP transfer-encoding b'chunked' for HTTP/1.0",
        'invalid_header_name': "invalid header name: b'Content Length'",
        'invalid_version': "Bad HTTP request line: b'GET /api/catalog HTP/1.1'",
    }
    for name, encoded in payload['requests'].items():
        if name in errors:
            expected = {'accepted': False, 'error_type': 'ValueError', 'message': errors[name]}
        else:
            head, body = bytes.fromhex(encoded).split(b'\r\n\r\n', 1)
            lines = head.decode().split('\r\n')
            method, path, version = lines[0].split()
            expected = {'accepted': True, 'method': method, 'path': path, 'http_version': version,
                        'headers': [line.split(': ', 1) for line in lines[1:]], 'body_hex': body.hex(),
                        'expected_body_size': {'clean_get': 0, 'clean_post': 2, 'clean_chunked': None}[name]}
        if canonical(native['requests'][name]) != canonical(expected):
            raise EvidenceError('native HTTP framing disagrees with the owned controls: ' + name)
    for name, text in bodies.items():
        expected = {'accepted': True, 'status': 200, 'content_type': 'application/javascript; charset=utf-8',
                    'decoded_body': text, 'decoded_sha256': sha(text.encode())}
        if canonical(native['responses'][name]) != canonical(expected):
            raise EvidenceError('native HTTP decoding differs from the original owned body')
    corrupt = native['responses']['corrupt_gzip']
    if (set(corrupt) != {'accepted', 'error_type', 'encoding_error', 'message'}
            or corrupt['accepted'] is not False or corrupt['error_type'] != 'ValueError'
            or corrupt['encoding_error'] is not True
            or sha(corrupt['message'].encode()) != '703e2229857eaed6448be1609e4906a191fff9991d63de2c038cdd5bce53c236'):
        raise EvidenceError('corrupt compressed HTTP response was not rejected')
    return native


def validate_links(results, bodies):
    if set(results) != set(bodies):
        raise EvidenceError('link-finder control coverage differs')
    expected = {
        'base': (['/api/catalog?limit=10&cursor=owned', '/api/positions?owner=alice', '/api/status'], ['cursor', 'limit', 'owner']),
        'changed': (['/api/catalog?limit=10&cursor=owned', '/api/exposures?account_id=alice', '/api/status'], ['account_id', 'cursor', 'limit']),
        'duplicates': (['/api/catalog?limit=10&cursor=owned', '/api/positions?owner=alice', '/api/status'], ['cursor', 'limit', 'owner']),
        'no_routes': ([], []),
    }
    for name, row in results.items():
        links, parameters = expected[name]
        wanted = {'links': links, 'parameter_candidates': parameters, 'version': '8.2',
                  'requests_made': 0, 'failed_requests': 0, 'visited_urls': [],
                  'network_events': ['socket.__new__']}
        if canonical(row) != canonical(wanted):
            raise EvidenceError('native link-finder disagrees with owned route controls: ' + name)
    return {'cases': results, 'route_change': {'removed': ['/api/positions?owner=alice'],
                                              'added': ['/api/exposures?account_id=alice']},
            'parameter_change': {'removed': ['owner'], 'added': ['account_id']},
            'interpretation': 'Static candidates from owned JS, not demonstrated server endpoints or vulnerabilities.'}


def run(kit: Path):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('locked HTTP native dependencies require CPython 3.12')
    payload, bodies = inputs()
    proofs = source_proofs()
    worker = Path(__file__).with_name('product_http_native_worker.py')
    with tempfile.TemporaryDirectory(prefix='nqc-http-native-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin', 'PYTHONIOENCODING': 'utf-8'}
        install_wheels(Path(kit), work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='HTTP native')
        counts = verify_installed(work, proofs)

        def execute(mode, data):
            for filename in ('http-native.json', 'links.txt', 'parameters.txt'):
                (work/filename).unlink(missing_ok=True)
            proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S', str(worker), mode],
                                  cwd=work, env=env, input=canonical(data), capture_output=True, timeout=90)
            if proc.returncode:
                raise EvidenceError('HTTP native producer failed: ' + proc.stderr.decode(errors='replace')[-1000:])
            return strict_json(read_artifact(work, 'http-native.json'))

        http = validate_http(execute('http', payload), payload, bodies)
        # Only decoder output already matched to the original owned body reaches the link finder.
        links = validate_links({name: execute('links', {'content': http['responses'][name]['decoded_body']})
                                for name in bodies}, bodies)
    return {'schema_version': 1, 'scope': 'fixed_owned_http_and_javascript_no_external_targets',
            'dependency_lock_sha256': LOCK_SHA, 'source_proofs_sha256': PROOFS_SHA,
            'source_revisions': {k: v['revision'] for k, v in proofs.items()},
            'verified_sources': counts, 'input_sha256': sha(canonical(payload)),
            'http': http, 'link_discovery': links,
            'summary': {'accepted_valid_request_headers': 3, 'rejected_invalid_request_headers': 9,
                        'decoded_responses': 4, 'rejected_corrupt_response': 1, 'link_controls': 4,
                        'confirmed_original_vulnerabilities': 0}}
