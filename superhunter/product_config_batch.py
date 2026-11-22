"""Inspect NQC's disabled jobs and the default TLS client used for source retrieval, offline."""
import ast
import http.client
from importlib import metadata
from pathlib import Path
import re
import ssl
import struct
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from . import infra_batch_config_worker as worker
from .product_infra_batch import capture
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

CART = 'cartography-cncf/cartography'
TLS = 'nabla-c0d3/sslyze'
MAPPING = 'testssl/testssl.sh'
SOURCES = {
    CART: ('080-cartography', 'ce236e196bbec30c99502e6ff5ac809a23b2ec42',
           ('cartography/intel/github/workflow_parser.py',)),
    TLS: ('066-sslyze', 'e064c2c8e7d251e5bc5db1a7beb21add5e12a0bc', ('sslyze/mozilla_tls_profile/5.7.json',)),
    MAPPING: ('072-testssl.sh', '0f87aca237ae52a35e69a14157c37377a1779908', ('etc/cipher-mapping.txt',)),
}
YAML_DIGEST = '05780a44b9c038a882c0a22e76719a5117c514ebb41f98f9e4f4cb96cc6dd73e'
WORKFLOWS = 'ci/migration/legacy-workflows'
WORKFLOW_TREE = '1cc2c2f05820eb707d7e71b0a1ae54e944f7fe45'
FETCHER = 'superhunter/tools/fetch_root_manifests.py'
FETCHER_BLOB = '2d7923fd67b71fdcd416bbc3f50576edeb376b85'


def yaml_modules():
    distribution = metadata.distribution('PyYAML')
    root = Path(distribution.locate_file('yaml'))
    data = {'yaml/' + p.name: read_artifact(root, p.name) for p in root.glob('*.py')}
    if sha(canonical({name: sha(raw) for name, raw in data.items()})) != YAML_DIGEST:
        raise EvidenceError('Cartography requires the verified pure Python module set from PyYAML 6.0.3')
    return data


def workflow_bytes():
    rows = {}
    for record in git(ROOT, 'ls-tree', '-z', WORKFLOW_TREE).decode().split('\0'):
        if not record:
            continue
        attrs, name = record.split('\t')
        mode, kind, oid = attrs.split()
        if (mode, kind) != ('100644', 'blob') or not re.fullmatch(r'[a-z0-9.-]+\.yml\.disabled', name):
            raise EvidenceError('unexpected file in historical workflow tree')
        raw = read_artifact(ROOT, WORKFLOWS + '/' + name)
        if git_object('blob', raw) != oid:
            raise EvidenceError('historical workflow changed')
        rows[name] = raw
    return rows


def verify_workflow(content, native):
    # Read the unquoted subset actually present in the fixed historical tree.
    # Do not infer organization settings, job token grants or active workflows.
    matches = re.findall(r'^ {4,}(?:- )?uses: *([^\s#]+)(?: *#.*)? *$', content, re.M)
    expected = {name: bool(re.fullmatch(r'[^@]+@[0-9a-f]{40}', name)) for name in matches}
    block = re.search(r'^permissions: *\n((?:  [\w-]+: (?:read|write|none) *\n)+)', content, re.M)
    if not block:
        raise EvidenceError('archived permissions are outside the independently parsed layout')
    permissions = dict(re.findall(r'  ([\w-]+): (read|write|none)', block[1]))
    permissions = {name.replace('-', '_'): level for name, level in permissions.items()}
    if expected != native['actions'] or permissions != native['permissions']:
        raise EvidenceError('workflow parser and independent references disagree')
    return {'requires_pin_review': sorted(name for name, pinned in expected.items() if not pinned),
            'declared_write_scopes': sorted(name for name, mode in permissions.items() if mode == 'write')}


def workflow_report(parser):
    rows = workflow_bytes()
    control_name = 'classification-control.yml.disabled'
    original = 'nqc-build-truth.yml.disabled'
    src = rows[original].decode()
    match = re.search(r'actions/checkout@[0-9a-f]{40}', src)
    if not match or src.count('  contents: read\n') != 1:
        raise EvidenceError('expected archived control source changed')
    control = src.replace(match[0], 'actions/checkout@compatibility-control').replace('  contents: read\n', '  contents: write\n')
    with tempfile.TemporaryDirectory(prefix='nqc-disabled-config-') as temp:
        work = Path(temp)
        with ZipFile(work / 'libraries.zip', 'w') as archive:
            archive.writestr('workflow_parser.py', parser)
            for name, payload in yaml_modules().items():
                archive.writestr(name, payload)
        for name, raw in rows.items():
            (work / name).write_bytes(raw)
        (work / control_name).write_text(control, encoding='utf-8')
        response = subprocess.run([*ISOLATE, sys.executable, '-I', '-S', '-B', worker.__file__], cwd=work,
                                  env={'HOME': temp, 'LANG': 'C'}, stdin=subprocess.DEVNULL,
                                  capture_output=True, check=True, timeout=24)
        native = strict_json(response.stdout)
    if set(native) != set(rows) | {control_name}:
        raise EvidenceError('workflow parser omitted or added a filename')
    findings = {name: verify_workflow(raw.decode(), native[name]) for name, raw in rows.items()}
    changed = verify_workflow(control, native[control_name])
    baseline = findings[original]
    if (set(changed['declared_write_scopes']) - set(baseline['declared_write_scopes']) != {'contents'}
            or set(changed['requires_pin_review']) - set(baseline['requires_pin_review']) != {'actions/checkout@compatibility-control'}):
        raise EvidenceError('workflow controlled change escaped independent checks')
    writes = {n: x['declared_write_scopes'] for n, x in findings.items() if x['declared_write_scopes']}
    tags = {n: x['requires_pin_review'] for n, x in findings.items() if x['requires_pin_review']}
    return {'role': 'executed', 'operation': 'resolve_disabled_workflow_action_revisions_and_declared_write_scopes',
            'historical_workflow_tree': WORKFLOW_TREE, 'files_parsed': len(rows),
            'declared_jobs': sum(native[n]['jobs'] for n in rows),
            'distinct_action_refs_per_file_total': sum(len(native[n]['actions']) for n in rows),
            'manual_review': {'declared_writes': writes, 'unpinned_references': tags},
            'decisions_sha256': sha(canonical(findings)), 'control_delta': sorted(['contents:write', 'mutable-checkout']),
            'pure_pyyaml_sources_sha256': YAML_DIGEST}


def vector(blob, position, width):
    if position + width > len(blob):
        raise EvidenceError('truncated handshake vector length')
    size = int.from_bytes(blob[position:position + width], 'big')
    end = position + width + size
    if end > len(blob):
        raise EvidenceError('truncated handshake vector payload')
    return blob[position + width:end], end


def pairs(raw):
    if len(raw) == 0 or len(raw) % 2:
        raise EvidenceError('invalid TLS identifier list')
    return [v for v, in struct.iter_unpack('!H', raw)]


def hello_offers(blob):
    if len(blob) < 9 or blob[0] != 22 or blob[5] != 1:
        raise EvidenceError('expected a single ClientHello record')
    if int.from_bytes(blob[3:5], 'big') + 5 != len(blob) or int.from_bytes(blob[6:9], 'big') + 9 != len(blob):
        raise EvidenceError('ClientHello envelope length differs')
    body = blob[9:]
    _, i = vector(body, 34, 1)
    suites, i = vector(body, i, 2)
    _, i = vector(body, i, 1)
    extensions, end = vector(body, i, 2)
    if end != len(body):
        raise EvidenceError('trailing ClientHello data')
    i = 0
    versions = None
    while i < len(extensions):
        kind = int.from_bytes(extensions[i:i + 2], 'big')
        field, i = vector(extensions, i + 2, 2)
        if kind == 43:
            advertised, end = vector(field, 0, 1)
            if end != len(field) or versions is not None:
                raise EvidenceError('unexpected supported_versions field')
            versions = pairs(advertised)
    return pairs(suites), versions or [int.from_bytes(body[:2], 'big')]


def default_offer(*, tls12_only=False):
    # Construction selects CPython's default HTTPS client configuration without
    # connecting. SSLObject produces only the client's first record in memory.
    ctx = http.client.HTTPSConnection('nqc.invalid')._context
    if tls12_only:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    output = ssl.MemoryBIO()
    client = ctx.wrap_bio(ssl.MemoryBIO(), output, server_hostname='nqc.invalid')
    try:
        client.do_handshake()
    except ssl.SSLWantReadError:
        pass
    else:
        raise EvidenceError('TLS client did not pause for input')
    suites, versions = hello_offers(output.read())
    active = [c for c in ctx.get_ciphers() if 772 in versions or c['protocol'] != 'TLSv1.3']
    negotiated = [value for value in suites if value != 0x00ff]  # Signaling value, never a cipher.
    if [c['id'] & 0xffff for c in active] != negotiated:
        raise EvidenceError('wire cipher identifiers disagree with the independent OpenSSL API')
    return active, versions


def resolve_profiles(active, versions, mapping, profiles):
    ids = {}
    for hi, lo, alias, iana in re.findall(r'^ *0x([0-9a-fA-F]{2}),0x([0-9a-fA-F]{2}) +- +(\S+) +(\S+)', mapping, re.M):
        ids[int(hi + lo, 16)] = (alias, iana)
    offers = {}
    for cipher in active:
        code = cipher['id'] & 0xffff
        if code not in ids or ids[code][0] != cipher['name']:
            raise EvidenceError('OpenSSL and testssl.sh cipher identity differs')
        offers[ids[code][1]] = cipher['protocol']
    supported = {772: 'TLSv1.3', 771: 'TLSv1.2'}
    levels = {supported[n] for n in versions}
    comparable = {}
    for name in ('modern', 'intermediate'):
        conf = profiles['configurations'][name]
        offered_versions = levels.intersection(conf['tls_versions'])
        iana = set(conf['ciphers']['iana']) | set(conf['ciphersuites'])
        comparable[name] = sorted(n for n in iana if n in offers and offers[n] in offered_versions)
    return offers, comparable


def tls_report(profile_raw, cipher_table):
    raw = read_artifact(ROOT, FETCHER)
    if git_object('blob', raw) != FETCHER_BLOB:
        raise EvidenceError('manifest fetcher revision changed')
    calls = [n for n in ast.walk(ast.parse(raw)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == 'urlopen']
    if len(calls) != 1 or len(calls[0].args) != 1 or {kw.arg for kw in calls[0].keywords} != {'timeout'}:
        raise EvidenceError('fetcher uses a nondefault TLS configuration')
    profiles = strict_json(profile_raw)
    native, versions = default_offer()
    named, normal = resolve_profiles(native, versions, cipher_table.decode(), profiles)
    restricted, restricted_versions = default_offer(tls12_only=True)
    _, control = resolve_profiles(restricted, restricted_versions, cipher_table.decode(), profiles)
    if not(normal['modern'] and normal['intermediate'] and control['intermediate']) or control['modern']:
        raise EvidenceError('in-memory TLS capability controls disagree with the profile')
    evidence = {'fetcher_git_blob': FETCHER_BLOB, 'wire_protocols': versions, 'implementation': ssl.OPENSSL_VERSION,
                'role': 'reference', 'transport': 'in-memory first TLS record'}
    return {TLS: {**evidence, 'operation': 'compare_client_offers_against_Mozilla_server_cipher_and_version_profiles',
                  'overlap_by_profile': normal, 'tls12_only_control': control},
            MAPPING: {**evidence, 'operation': 'resolve_wire_identifiers_to_OpenSSL_and_IANA_names',
                      'wire_cipher_names': named, 'wire_code_to_IANA_count': len(named)}}


def review(source_root: Path):
    data, receipts = {}, {}
    for repo in SOURCES:
        contents, receipts[repo] = capture(source_root, repo, SOURCES, binary=True)
        data[repo], = contents.values()
    receipts[CART].update(workflow_report(data[CART]))
    for repo, result in tls_report(data[TLS], data[MAPPING]).items():
        receipts[repo].update(result)
    return receipts
