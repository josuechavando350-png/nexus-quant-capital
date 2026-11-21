"""Exercise fixed native discovery clients against an owned loopback service."""
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit


def arjun_entry():
    import random
    import runpy
    sys.path.insert(0, str(Path('lib').resolve()))
    random.seed(0)
    sys.argv = ['arjun', *sys.argv[2:]]
    runpy.run_module('arjun', run_name='__main__')


def enable_owned_loopback():
    interfaces = [line.split(':', 1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]]
    if interfaces != ['lo']:
        raise ValueError('owned discovery requires a fresh namespace with only lo')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        fcntl.ioctl(control.fileno(), 0x8914, struct.pack('16sH14s', b'lo', 0x49, b''))
    if len(Path('/proc/net/route').read_text().splitlines()) != 1:
        raise ValueError('owned discovery namespace unexpectedly has a route')


def main():
    from importlib.metadata import Distribution
    payload = json.loads(sys.stdin.buffer.read(2_000_001))
    enable_owned_loopback()
    captured = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            with lock:
                captured.append({'path': parsed.path, 'query': sorted(query),
                                 'peer': self.client_address[0], 'method': self.command,
                                 'host': self.headers.get('Host')})
                over_budget = len(captured) > 512 or len(self.path) > 20000
            if over_budget:
                status, body = 429, b'OWNED budget exceeded'
            elif parsed.path == '/params/live' and 'include_closed' in query:
                status, body = 200, bytes.fromhex(payload['expanded_body'])
            elif parsed.path in ('/params/live', '/params/clean'):
                status, body = 200, bytes.fromhex(payload['parameter_body'])
            elif parsed.path in payload['routes']:
                row = payload['routes'][parsed.path]
                status, body = row['status'], bytes.fromhex(row['body'])
            elif parsed.path.startswith('/wild/'):
                status, body = 200, bytes.fromhex(payload['wildcard_body'])
            else:
                status, body = 404, b'OWNED missing\n'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    host = '127.0.0.1:' + str(server.server_port)
    base = 'http://' + host
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    Path('paths.txt').write_text('\n'.join(payload['route_words']) + '\n')
    Path('parameters.txt').write_text('\n'.join(payload['parameter_words']) + '\n')
    reports, traffic_counts = {}, {}

    def execute(command, name, prefix, parameter_case=False):
        start = len(captured)
        proc = subprocess.run(command, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        rows = captured[start:]
        traffic_counts[name] = len(rows)
        audit = {'within_request_budget': 0 < len(rows) <= 128,
                 'only_owned_loopback': all(row['peer'] == '127.0.0.1' and row['host'] == host for row in rows),
                 'only_expected_path': all(row['path'] == prefix if parameter_case else row['path'].startswith(prefix) for row in rows),
                 'methods': sorted(set(row['method'] for row in rows)),
                 'route_candidates_requested': sorted({row['path'].removeprefix(prefix) for row in rows}
                                                        & set(payload['route_words'])) if not parameter_case else [],
                 'parameter_candidates_requested': sorted({q for row in rows for q in row['query']}
                                                            & set(payload['parameter_words']))}
        return proc, audit

    def validate_url(url, profile):
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.netloc != host or not parsed.path.startswith('/' + profile + '/'):
            raise ValueError('native discovery output escaped the owned fixture')
        return parsed.path

    try:
        for profile in ('live', 'clean', 'wild'):
            name = 'ffuf_' + profile
            dest = name + '.json'
            command = ['./ffuf', '-u', base + '/' + profile + '/FUZZ', '-w', 'paths.txt', '-t', '1',
                       '-timeout', '3', '-maxtime', '30', '-noninteractive', '-s', '-mc', '200,403',
                       '-of', 'json', '-o', dest]
            if profile == 'wild':
                command += ['-ac']
            proc, audit = execute(command, name, '/' + profile + '/')
            if proc.returncode:
                raise ValueError('native ffuf failed: ' + proc.stderr.decode(errors='replace')[-600:])
            data = json.loads(Path(dest).read_text())
            found = []
            for row in data['results']:
                path = validate_url(row['url'], profile)
                if path != '/' + profile + '/' + row['input']['FUZZ']:
                    raise ValueError('native ffuf candidate identity differs')
                found.append({'path': path, 'status': row['status'], 'bytes': row['length']})
            reports[name] = {'matches': sorted(found, key=lambda r: r['path']), 'audit': audit}

            name = 'gobuster_' + profile
            dest = name + '.txt'
            command = ['./gobuster', 'dir', '-u', base + '/' + profile + '/', '-w', 'paths.txt',
                       '-t', '1', '--timeout', '3s', '--no-progress', '--no-color', '-q', '-e', '-o', dest]
            proc, audit = execute(command, name, '/' + profile + '/')
            if profile == 'wild':
                diagnostic = (proc.stdout + proc.stderr).decode(errors='replace')
                category = 'matches the provided options for non existing urls' in diagnostic
                size = re.search(r'=> (\d{3}) \(Length: (\d+)\)', diagnostic)
                if proc.returncode == 0 or not category or size is None:
                    raise ValueError('native Gobuster did not reject the ambiguous wildcard baseline')
                reports[name] = {'refused_wildcard': True, 'baseline_status': int(size[1]),
                                 'baseline_bytes': int(size[2]), 'audit': audit}
            else:
                if proc.returncode:
                    raise ValueError('native Gobuster failed')
                found = []
                for line in Path(dest).read_text().splitlines():
                    match = re.fullmatch(r'(\S+)\s+\(Status: (\d{3})\) \[Size: (\d+)\]', line)
                    if match is None:
                        raise ValueError('unexpected native Gobuster output row')
                    found.append({'path': validate_url(match[1], profile), 'status': int(match[2]), 'bytes': int(match[3])})
                reports[name] = {'matches': sorted(found, key=lambda r: r['path']), 'audit': audit}

        for profile in ('live', 'clean'):
            name = 'arjun_' + profile
            dest = name + '.json'
            target = base + '/params/' + profile
            command = [sys.executable, '-I', '-B', '-S', str(Path(__file__).resolve()), 'arjun',
                       '-u', target, '-w', 'parameters.txt', '-oJ', dest, '-t', '1', '-c', '4', '-T', '3',
                       '--disable-redirects', '--headers', 'User-Agent: NQC-owned-discovery']
            proc, audit = execute(command, name, '/params/' + profile, True)
            diagnostic = (proc.stdout + proc.stderr).decode(errors='replace')
            if proc.returncode or 'Skipped ' in diagnostic:
                raise ValueError('native Arjun failed: ' + diagnostic[-600:])
            if Path(dest).exists():
                data = json.loads(Path(dest).read_text())
                if set(data) != {target} or data[target]['method'] != 'GET':
                    raise ValueError('native Arjun target or method differs')
                parameters = sorted(data[target]['params'])
                verdict = 'parameters_found'
            else:
                if 'No parameters were discovered.' not in diagnostic:
                    raise ValueError('native Arjun produced no unambiguous completion')
                parameters, verdict = [], 'none_found'
            reports[name] = {'parameters': parameters, 'verdict': verdict, 'audit': audit}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    result = {'cases': reports, 'namespace': {'interfaces': ['lo'], 'ipv4_route_count': 0},
              'versions': {'ffuf': subprocess.check_output(['./ffuf', '-V'], text=True).strip(),
                           'gobuster': subprocess.check_output(['./gobuster', '--version'], text=True).splitlines()[0],
                           'arjun': Distribution.at(next(Path('lib').glob('arjun-*.dist-info'))).version}}
    Path('discovery-native.json').write_text(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
    Path('request-counts.json').write_text(json.dumps(traffic_counts, sort_keys=True) + '\n')


if __name__ == '__main__':
    arjun_entry() if len(sys.argv) > 1 and sys.argv[1] == 'arjun' else main()
