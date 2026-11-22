"""Create schema-checked, banner-free EVE records from three recorded NQC HTTP responses."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from .product_infra_batch import capture
from .product_languages_batch import run, write_files
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_sources import git
from .product_timeline_formats import GO_SHA
from .product_web_native import fixtures
from .safe_io import canonical, read_artifact, strict_json

CILIUM, SURICATA = 'cilium/cilium', 'OISF/suricata'
FILTER = 'pkg/hubble/parser/seven/http.go'
OPTIONS = 'pkg/hubble/parser/options/options.go'
DEFAULTS = 'pkg/hubble/defaults/defaults.go'
SCHEMA = 'etc/schema.json'
ORIGINS = {
    CILIUM: ('083-cilium', 'fb070362cec985b65e10d733365b1f34839dbf5b', (FILTER, OPTIONS, DEFAULTS)),
    SURICATA: ('093-suricata', '5c7787ed61adb1aa7a26c23e093992350fc97d62', (SCHEMA,)),
}
ARCHIVE = 'superhunter/product_supply/web-native-review.json'
ARCHIVE_SHA = '635f8fc128cc34d725dc24076f9707659655e987e6e4af7fdc811d02234e843c'
WHEEL = 'jsonschema_rs-0.62.0-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl'
WHEEL_SHA = '39e37199946e6022762ecd106a5f6b83a6d7b4e9360a1ef578b98429c9379237'
MASK = 'HUBBLE_REDACTED'
GO_DRIVER = '''
func main() {
    var cases []map[string]string
    if err := json.NewDecoder(os.Stdin).Decode(&cases); err != nil { panic(err) }
    policy := options.HubbleRedactSettings{Enabled:true,
        RedactHttpHeaders:options.HttpHeadersList{Allow:map[string]struct{}{"content-length":{}}}}
    for _, row := range cases {
        for k, v := range row { row[k] = filterHeader(k, v, policy) }
    }
    if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"headers": cases}); err != nil { panic(err) }
}
'''
VALIDATOR = """import json, sys
sys.path.insert(0, '.')
from jsonschema_rs import Draft202012Validator
payload = json.load(sys.stdin)
check = Draft202012Validator(payload['schema'])
print(json.dumps({key: check.is_valid(record) for key, record in payload['cases'].items()}))
"""


def packets():
    raw = read_artifact(ROOT, ARCHIVE)
    if sha(raw) != ARCHIVE_SHA:
        raise EvidenceError('HTTP evidence archive changed')
    source = strict_json(raw)
    payload, expected = fixtures()
    rows = source['observations']['captures']['complete']
    if sha(canonical(payload)) != source['input_sha256'] or rows != expected:
        raise EvidenceError('regenerated fixed HTTP capture and recorded observations differ')
    pcap = base64.b64decode(payload['captures']['complete'], validate=True)
    offset, results = 24, []
    for row in rows:
        seconds, micros, captured, wire = struct.unpack_from('<IIII', pcap, offset)
        if captured != row['captured_length'] or wire != row['wire_length'] or micros >= 1_000_000:
            raise EvidenceError('packet time or size differs from archived capture')
        timestamp = datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=micros)
        results.append((timestamp.strftime('%Y-%m-%dT%H:%M:%S.%f%z'), row))
        offset += 16 + captured
    if offset != len(pcap) or len(results) != 3:
        raise EvidenceError('incomplete owned packet timeline')
    return results


def declaration(source, start):
    match = re.search('^' + re.escape(start) + r'[^\n]*\n.*?^}', source, re.M | re.S)
    if not match:
        raise EvidenceError('missing reviewed Go declaration')
    return match[0]


def hubble(work, files, headers):
    # Compile only the authenticated pure Hubble filter and the exact definitions it consumes.
    names = re.findall(r'^\s*(SensitiveValueRedacted = "[^"]+")$', files[DEFAULTS], re.M)
    if len(names) != 1:
        raise EvidenceError('Hubble mask constant is ambiguous')
    types = [declaration(files[OPTIONS], 'type ' + name + ' struct {') for name in ('HubbleRedactSettings', 'HttpHeadersList')]
    filter_source = declaration(files[FILTER], 'func filterHeader(')
    main = ('package main\nimport ("encoding/json"; "os"; "strings"; '
            '"github.com/cilium/cilium/pkg/hubble/defaults"; "github.com/cilium/cilium/pkg/hubble/parser/options")\n'
            + filter_source + '\n' + GO_DRIVER)
    write_files(work, {'go.mod': b'module github.com/cilium/cilium\n\ngo 1.25\n',
                       'main.go': main.encode(), DEFAULTS: ('package defaults\nconst ' + names[0] + '\n').encode(),
                       OPTIONS: ('package options\n' + '\n'.join(types) + '\n').encode()})
    go = Path(os.environ.get('NQC_STATE_GO', '/no-state-go')).resolve(strict=True)
    with go.open('rb') as binary:
        if hashlib.file_digest(binary, 'sha256').hexdigest() != GO_SHA:
            raise EvidenceError('unreviewed Go compiler for the Hubble header filter')
    env = {'HOME': str(work), 'PATH': str(go.parent), 'GOPROXY': 'off', 'GOENV': 'off', 'GOWORK': 'off',
           'GOSUMDB': 'off', 'CGO_ENABLED': '0', 'GOTOOLCHAIN': 'local', 'GOTELEMETRY': 'off',
           'GOROOT': str(go.parent.parent), 'GOCACHE': str(work/'cache'), 'GOPATH': str(work/'gopath'),
           'GOMAXPROCS': '2', 'GOOS': 'linux', 'GOARCH': 'amd64'}
    binary = work/'redact'
    subprocess.run([*ISOLATE, go, 'build', '-p=2', '-trimpath', '-buildvcs=false', '-ldflags=-buildid=',
                    '-o', binary, '.'], cwd=work, env=env, capture_output=True, timeout=150, check=True)
    observed = strict_json(run(work, [binary], canonical(headers)))["headers"]
    expected = [{name: val if name.lower() == 'content-length' else MASK for name, val in row.items()}
                for row in headers]
    if observed != expected:
        raise EvidenceError('Hubble header filter disclosed a private field or changed a public length')
    return observed, sha(binary.read_bytes())


def evidence(rows, masked):
    output = {}
    for i, ((timestamp, row), headers) in enumerate(zip(rows, masked, strict=True), 1):
        version, status, _ = row['status_line'].split(' ', 2)
        if headers != {'Server': MASK, 'Content-Length': str(row['content_length'])}:
            raise EvidenceError('redacted HTTP headers differ from known public projection')
        output[str(i)] = {'event_type': 'http', 'timestamp': timestamp, 'pcap_cnt': i,
                          'http': {'status': int(status), 'protocol': version, 'length': row['content_length'],
                                   'response_headers': [{'name': key, 'value': headers[key]} for key in sorted(headers)]}}
    return output


def schema_cases(records):
    cases = dict(records)
    for name in ('text_status', 'empty_headers', 'unknown_field', 'absent_time'):
        case = deepcopy(records['1'])
        if name == 'text_status':
            case['http']['status'] = '200'
        elif name == 'empty_headers':
            case['http']['response_headers'] = []
        elif name == 'unknown_field':
            case['http']['undocumented_field'] = True
        else:
            del case['timestamp']
        cases[name] = case
    return cases


def validate_eve(work, kit, schema, records):
    wheel = work/'validator.whl'
    copy_release('reviewed web schema validator', kit/WHEEL, wheel, WHEEL_SHA, executable=False)
    with ZipFile(wheel) as archive:
        for name in ('jsonschema_rs/__init__.py', 'jsonschema_rs/canonical/__init__.py',
                     'jsonschema_rs/jsonschema_rs.abi3.so'):
            write_files(work, {name: archive.read(name)})
    checks = strict_json(run(work, [sys.executable, '-I', '-S', '-B', '-c', VALIDATOR],
                             canonical({'schema': schema, 'cases': schema_cases(records)})))
    expected = {name: name in records for name in schema_cases(records)}
    if checks != expected:
        raise EvidenceError('EVE schema failed to distinguish the public records and invalid controls')
    return checks


def review(source_root, web_kit):
    if web_kit is None:
        raise EvidenceError('the public HTTP view requires the existing web native kit')
    sources, origins = {}, {}
    for name, (directory, revision, _) in ORIGINS.items():
        repo = source_root / directory
        if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('HTTP view source checkout differs')
        sources[name], origins[name] = capture(source_root, name, ORIGINS)
    rows = packets()
    headers = [{'Server': row['server'], 'Content-Length': str(row['content_length'])} for _, row in rows]
    control = {'sErVeR': 'NQC-FIXTURE-BANNER', 'X-Private': 'NQC-FIXTURE-OTHER', 'content-length': '9'}
    with tempfile.TemporaryDirectory(prefix='nqc-eve-view-') as tmp:
        work = Path(tmp)
        masked, binary = hubble(work, sources[CILIUM], [*headers, control])
        public = evidence(rows, masked[:-1])
        accepted = validate_eve(work, web_kit, strict_json(sources[SURICATA][SCHEMA].encode()), public)
    return {
        CILIUM: {**origins[CILIUM], 'role': 'executable', 'operation': 'Mask HTTP banners in a minimized QA capture export.',
                 'archive_sha256': ARCHIVE_SHA, 'go_sha256': GO_SHA, 'filter_binary_sha256': binary,
                 'result': {'masked_response_headers': masked[:-1], 'case_insensitive_and_unlisted_control': masked[-1]}},
        SURICATA: {**origins[SURICATA], 'role': 'reference_data', 'operation': 'Check public HTTP capture records against the EVE schema.',
                   'archive_sha256': ARCHIVE_SHA, 'validator_wheel_sha256': WHEEL_SHA,
                   'result': {'public_records': public, 'schema_controls': accepted}},
    }
