"""Native API contract checks and HTTP capture interpretation on fixed owned data."""
import base64
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile

from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_upstream_notices import sources
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'schemathesis/schemathesis': 'executable', 'secdev/scapy': 'executable',
                'rapid7/recog': 'reference_data'}
LOCK = 'superhunter/product_supply/web-native-linux-py312.txt'
LOCK_SHA = 'e8cac1f6744279169feb9fde33a37942c428679aa8e0197ae9dffee89837c057'
PROOFS = 'superhunter/product_supply/web-native-sources.json'
PROOFS_SHA = '214062848fdac5678d6ae01f1700b8b6a5a20c2300e83efd88cfc811fee8e955'
MUTATIONS = ('clean', 'id_as_text', 'extra_field', 'missing_repository', 'invalid_revision', 'server_error')


def checksum(data):
    if len(data) % 2:
        data += b'\0'
    total = sum(struct.unpack('!' + 'H' * (len(data) // 2), data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return ~total & 65535


def capture(records):
    """Encode owned Ethernet/IPv4/TCP frames independently of Scapy."""
    headers = ('Apache/2.4.62', 'nginx/1.28.0', 'OWNED-Unrecognized/1.0')
    pcap = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
    expected = []
    for i, (record, banner) in enumerate(zip(records, headers, strict=True)):
        body = canonical(record).rstrip(b'\n')
        http = ('HTTP/1.1 200 OK\r\nServer: ' + banner + '\r\nContent-Length: ' + str(len(body))
                + '\r\nContent-Type: application/json\r\n\r\n').encode() + body
        src, dst = socket.inet_aton('192.0.2.1'), socket.inet_aton('192.0.2.2')
        tcp = struct.pack('!HHIIBBHHH', 8080, 40000 + i, 1, 1, 80, 24, 4096, 0, 0)
        pseudo = src + dst + struct.pack('!BBH', 0, 6, len(tcp) + len(http))
        tcp = tcp[:16] + struct.pack('!H', checksum(pseudo + tcp + http)) + tcp[18:]
        ip = struct.pack('!BBHHHBBH4s4s', 69, 0, 40 + len(http), i, 0, 64, 6, 0, src, dst)
        ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
        raw = bytes.fromhex('0200000000020200000000010800') + ip + tcp + http
        pcap += struct.pack('<IIII', 1 + i, 0, len(raw), len(raw)) + raw
        expected.append({'src': '192.0.2.1', 'dst': '192.0.2.2', 'sport': 8080, 'dport': 40000 + i,
                         'captured_length': len(raw), 'wire_length': len(raw), 'ip_length': 40 + len(http),
                         'ip_checksum_valid': True, 'tcp_checksum_valid': True,
                         'server': banner, 'content_length': len(body), 'body_hex': body.hex(),
                         'status_line': 'HTTP/1.1 200 OK'})
    return pcap, expected


def fixtures():
    rows = [row for row in sources() if row['id'] in (4, 65, 92)]
    if len(rows) != 3:
        raise EvidenceError('owned web fixture requires three catalog identities')
    records = [{'id': r['id'], 'repository': r['repository'], 'revision': r['revision']} for r in rows]
    trials = []
    for record in records:
        for mutation in MUTATIONS:
            body = dict(record)
            status = 200
            if mutation == 'id_as_text':
                body['id'] = str(body['id'])
            elif mutation == 'extra_field':
                body['unexpected'] = 'OWNED_CONTROL_ONLY'
            elif mutation == 'missing_repository':
                body.pop('repository')
            elif mutation == 'invalid_revision':
                body['revision'] = 'f' * 39
            elif mutation == 'server_error':
                status = 500
            trials.append({'id': record['id'], 'mutation': mutation, 'status': status, 'body': body})
    schema = {'type': 'object', 'required': ['id', 'repository', 'revision'], 'additionalProperties': False,
              'properties': {'id': {'type': 'integer', 'minimum': 1, 'maximum': 200},
                             'repository': {'type': 'string', 'pattern': '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'},
                             'revision': {'type': 'string', 'pattern': '^[0-9a-f]{40}$'}}}
    openapi = {'openapi': '3.0.3', 'info': {'title': 'NQC owned catalog contract', 'version': '1'},
               'paths': {'/catalog/{id}': {'get': {
                   'parameters': [{'in': 'path', 'name': 'id', 'required': True,
                                   'schema': {'type': 'integer', 'minimum': 1, 'maximum': 200}}],
                   'responses': {'200': {'description': 'Owned catalog identity',
                                        'content': {'application/json': {'schema': schema}}}}}}}}
    raw, expected_packets = capture(records)
    return {'openapi': openapi, 'trials': trials,
            'captures': {'complete': base64.b64encode(raw).decode(),
                         'truncated': base64.b64encode(raw[:-7]).decode()}}, expected_packets


def source_proofs():
    raw = read_artifact(ROOT, PROOFS)
    if sha(raw) != PROOFS_SHA:
        raise EvidenceError('web source proof differs')
    return strict_json(raw)


def verify_installed(work, proofs):
    counts = {}
    for package in ('schemathesis', 'scapy'):
        entry = proofs[package]
        expected = set(entry['python_git_blobs']) | set(entry['git_archive_export_subst'])
        actual = {p.relative_to(work/'lib').as_posix() for p in (work/'lib'/package).rglob('*.py')}
        if expected != actual:
            raise EvidenceError('native Python module membership differs from source proof')
        for path, blob in entry['python_git_blobs'].items():
            if git_object('blob', read_artifact(work/'lib', path)) != blob:
                raise EvidenceError('installed web producer differs from the catalog source')
        for path, transform in entry['git_archive_export_subst'].items():
            raw = read_artifact(work/'lib', path)
            if sha(raw) != transform['packaged_sha256']:
                raise EvidenceError('packaged version metadata differs')
            original = raw.replace(transform['archive_substitution'].encode(), b'$Format:%ct %(describe:tags=true)$')
            if git_object('blob', original) != transform['git_blob']:
                raise EvidenceError('archive version transformation differs')
        counts[package] = {'python_files': len(actual), 'byte_identical_git_blobs': len(entry['python_git_blobs']),
                           'archive_version_substitutions': len(entry['git_archive_export_subst'])}
    return counts


def validate(native, payload, expected_packets):
    if set(native) != {'api_trials', 'captures', 'capture_warnings', 'fingerprints', 'versions'}:
        raise EvidenceError('web producer report fields differ')
    if native['versions'] != {'schemathesis': '4.33.4', 'scapy': '2026.11.21'}:
        raise EvidenceError('web producer versions differ')
    if len(native['api_trials']) != len(payload['trials']):
        raise EvidenceError('incomplete API trial coverage')
    for wanted, row in zip(payload['trials'], native['api_trials'], strict=True):
        valid = wanted['mutation'] == 'clean'
        failures = [] if valid else (['ServerError', 'UndefinedStatusCode']
                                    if wanted['mutation'] == 'server_error' else ['JsonSchemaError'])
        if canonical(row) != canonical({**wanted, 'valid': valid, 'failure_types': failures}):
            raise EvidenceError('native API observation disagrees with owned contract controls')
    truncated = [dict(row) for row in expected_packets]
    truncated[-1]['captured_length'] -= 7
    truncated[-1]['body_hex'] = truncated[-1]['body_hex'][:-14]
    truncated[-1]['tcp_checksum_valid'] = False
    if canonical(native['captures']) != canonical({'complete': expected_packets, 'truncated': truncated}):
        raise EvidenceError('native packet interpretation differs from independent frame encoder')
    if native['capture_warnings'] != {'complete': [], 'truncated': [
            {'level': 'WARNING', 'message': 'Pcap: packet has been truncated'}]}:
        raise EvidenceError('native packet truncation warning differs')
    expected_fingerprints = [
        {'banner': 'Apache/2.4.62', 'matches': [{'rule': 'Apache', 'parameters':
                                              {'service.product': 'HTTPD', 'service.version': '2.4.62'}}]},
        {'banner': 'nginx/1.28.0', 'matches': [{'rule': 'nginx with version info and/or mods', 'parameters':
                                             {'service.product': 'nginx', 'service.version': '1.28.0'}}]},
        {'banner': 'OWNED-Unrecognized/1.0', 'matches': []}]
    if native['fingerprints'] != expected_fingerprints:
        raise EvidenceError('Recog fingerprint controls disagree')
    return {'api_trials': native['api_trials'], 'captures': native['captures'],
            'capture_warnings': native['capture_warnings'],
            'fingerprints': native['fingerprints'], 'versions': native['versions'],
            'summary': {'api_cases': 18, 'accepted_valid': 3, 'rejected_invalid': 15,
                        'complete_packets': 3, 'detected_truncated_packets': 1,
                        'fingerprint_matches': 2, 'unknown_banners': 1}}


def run(kit: Path):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('the locked web native wheel inventory requires CPython 3.12')
    kit = Path(kit)
    payload, expected_packets = fixtures()
    proofs = source_proofs()
    reference = read_artifact(kit, 'http_servers.xml')
    if sha(reference) != proofs['recog']['sha256'] or git_object('blob', reference) != proofs['recog']['git_blob']:
        raise EvidenceError('Recog reference differs from catalog source')
    with tempfile.TemporaryDirectory(prefix='nqc-web-native-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin', 'PYTHONIOENCODING': 'utf-8',
               'SCHEMATHESIS_TELEMETRY_DISABLED': 'true'}
        install_wheels(kit, work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='Web native')
        verified_sources = verify_installed(work, proofs)
        (work/'http_servers.xml').write_bytes(reference)
        worker = Path(__file__).with_name('product_web_native_worker.py')
        proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S', str(worker)],
                              cwd=work, env=env, input=canonical(payload), capture_output=True, timeout=90)
        if proc.returncode:
            raise EvidenceError('web native worker failed: ' + proc.stderr.decode(errors='replace')[-1000:])
        result = validate(strict_json(read_artifact(work, 'web-native.json')), payload, expected_packets)
    return {'schema_version': 1, 'scope': 'fixed_owned_api_and_captures_no_external_targets',
            'input_sha256': sha(canonical(payload)), 'dependency_lock_sha256': LOCK_SHA,
            'source_proofs_sha256': PROOFS_SHA, 'source_revisions': {k: v['revision'] for k, v in proofs.items()},
            'verified_sources': verified_sources, 'reference_git_blob': proofs['recog']['git_blob'],
            'observations': result}
