"""Run the original HTTP parser and link-finder on fixed owned content, offline."""
import contextlib
import hashlib
from importlib.metadata import version
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path('lib').resolve()))
network_events = []


def audit(event, args):
    if event.startswith('socket.'):
        network_events.append(event)
        raise PermissionError('owned offline producer cannot open network sockets')


sys.addaudithook(audit)


def http_checks(payload):
    from mitmproxy.net.http.http1 import read_request_head, read_response_head, expected_http_body_size
    from mitmproxy.net.http.validate import validate_headers
    requests, responses = {}, {}
    for name, encoded in payload['requests'].items():
        raw = bytes.fromhex(encoded)
        try:
            head, body = raw.split(b'\r\n\r\n', 1)
            request = read_request_head(head.split(b'\r\n'))
            validate_headers(request)
            requests[name] = {'accepted': True, 'method': request.method, 'path': request.path,
                              'http_version': request.http_version, 'headers':
                              [[key.decode(), value.decode()] for key, value in request.headers.fields],
                              'expected_body_size': expected_http_body_size(request),
                              'body_hex': body.hex()}
        except ValueError as error:
            requests[name] = {'accepted': False, 'error_type': type(error).__name__, 'message': str(error)}
    for name, encoded in payload['responses'].items():
        raw = bytes.fromhex(encoded)
        head, body = raw.split(b'\r\n\r\n', 1)
        response = read_response_head(head.split(b'\r\n'))
        response.raw_content = body
        try:
            validate_headers(response)
            text = response.get_text(strict=True)
            responses[name] = {'accepted': True, 'status': response.status_code,
                               'content_type': response.headers['content-type'],
                               'decoded_body': text, 'decoded_sha256': hashlib.sha256(text.encode()).hexdigest()}
        except ValueError as error:
            message = str(error)
            responses[name] = {'accepted': False, 'error_type': type(error).__name__,
                               'encoding_error': "with 'gzip'" in message and 'incorrect data check' in message,
                               'message': message}
    return {'requests': requests, 'responses': responses,
            'version': version('mitmproxy'), 'network_events': network_events}


def link_checks(payload):
    from xnLinkFinder import xnLinkFinder as finder
    Path('owned-config.yml').write_text('respParamPathWords: false\nrespParamJSVars: false\n')
    sys.stdin = io.StringIO(payload['content'])
    sys.argv = ['xnLinkFinder', '-nb', '-sf', 'owned.invalid', '-o', 'links.txt',
                '-op', 'parameters.txt', '-ow', '-vv', '--config', 'owned-config.yml']
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        finder.main()
    if 'ERROR ' in output.getvalue() or finder.stopProgram is not None:
        raise ValueError('native link-finder failed while reading owned content')
    rows = {}
    for key, name in [('links', 'links.txt'), ('parameter_candidates', 'parameters.txt')]:
        path = Path(name)
        # The original CLI creates no output for an empty result.
        rows[key] = sorted(set(path.read_text().splitlines())) if path.exists() else []
    return {**rows, 'version': version('xnlinkfinder'), 'requests_made': finder.totalRequests,
            'failed_requests': finder.failedRequests, 'visited_urls': sorted(finder.linksVisited),
            'network_events': network_events}


def main():
    data = sys.stdin.buffer.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('owned HTTP fixture too large')
    payload = json.loads(data)
    result = http_checks(payload) if sys.argv[1] == 'http' else link_checks(payload)
    Path('http-native.json').write_text(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
