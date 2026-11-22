"""Project the known Census timestamp across four clock representations without inferring a Solana slot."""
import base64
import hashlib
import os
from pathlib import Path
import re
import tarfile
import tempfile
import ssl
from zipfile import ZipFile

from .product_evm_standards_batch import run, runtime_path
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json

LITE, MOLLUSK, ANCHOR, AGAVE = 'LiteSVM/litesvm', 'anza-xyz/mollusk', 'otter-sec/anchor', 'anza-xyz/agave'
HEADER = 'nqc-census/crates/nqc-census-chain/tests/fixtures/mainnet-block-25437474.json'
HEADER_SHA = '7fdfd8e9d583c854001e5a74b80bdc9b359f551496bfa1a6d6912c1de75d5501'
WORKER = 'superhunter/product_supply/fixed-clock.mjs.txt'
SUPPLY = 'superhunter/product_supply/clock-format-assets.json'
PROTOC_SHA = '9a757b79f98195a1798e6e5e698360b621121de79a87aac0f7cf4a8a3bd5dfa2'
NAPI_SHA = '99c77610d47b0b04a3c63a8a5760edf04ec6c4e4edb2e87db39a329d204583c5'

UPSTREAM = {
    'LiteSVM/litesvm': ('180-litesvm', 'c848c5617d1ae4d3f832fb0ca03e30c611a7ba52', {
        'crates/node-litesvm/src/sysvar/clock.rs':
            '5c98647e899a17f0b34b30887f5c03a473638a14dae38a97d0051fea2dd380d2',
        'crates/node-litesvm/tests/sysvar.test.ts':
            '2f0841b58f2aca1abfeefa50354462b6cf2f78f92fcf562296a7b6230a930d48',
        'crates/node-litesvm/package.json':
            'fe993118582946edbd2234caa1283dbea0f0435c322030d8ed37e5dd915aab0a',
    }),
    'anza-xyz/mollusk': ('181-mollusk', '81d1463aabad700c3bb953827215c5dfc81ca61a', {
        'fuzz/fixture/proto/sysvars.proto':
            '5729b42c217f356d3051ca3cd7d909d20f8ea8ad215cb189fdb77a07f32947e9',
    }),
    'otter-sec/anchor': ('182-anchor', '98846e3bb753a2e5b701d58d2655f76c8f41a01e', {
        'ts/packages/borsh/src/index.ts':
            '668715f26167a5dc69dcc20479815ed90aaa768a5c5c56f47b53d6a5574af985',
        'ts/yarn.lock':
            '567f7da500bd4db351ccdc2a038439f290ef363c1f0696bfa96ebf22e72ba00d',
    }),
    'anza-xyz/agave': ('183-agave', '07289a6692285a1f3bdb4a1121b24f0c5a589298', {
        'account-decoder/src/parse_sysvar.rs':
            'fb8ea18cf991f9f0f509a55d432b929b805ab7485ce7422a658893237cdd9c43',
    }),
}


def need(value, message):
    if not value:
        raise EvidenceError('Census clock formats: ' + message)


def load_sources(root):
    files = {}
    for repo, (folder, revision, paths) in UPSTREAM.items():
        checkout = Path(root)/folder
        need(git(checkout, 'rev-parse', 'HEAD').decode().strip() == revision, 'unexpected checkout for ' + repo)
        for path, digest in paths.items():
            raw = read_artifact(checkout, path)
            need(sha(raw) == digest, 'changed source at ' + path)
            files[path] = raw
    return files


def shapes(files):
    proto = files['fuzz/fixture/proto/sysvars.proto'].decode()
    block = re.search(r'message Clock \{([^}]+)\}', proto)[1]
    wire = {name: (int(tag), type_ == 'int64')
            for type_, name, tag in re.findall(r'(u?int64) (\w+) = (\d+);', block)}
    lite = files['crates/node-litesvm/src/sysvar/clock.rs'].decode()
    construction = re.search(r'Ok\(Self\(ClockOriginal \{([^}]+)\}', lite)[1]
    slots = [(left, sign == 'i') for left, sign, right in re.findall(
        r'(\w+): bigint_to_(u|i)64\(&([a-z_]+)\)\?,', construction) if left == right]
    need(len(wire) == len(slots) == 5 and sorted(v[0] for v in wire.values()) == list(range(1, 6))
         and {k: s for k, s in slots} == {k: s for k, (_, s) in wire.items()}, 'wire vs native signedness')
    agave = files['account-decoder/src/parse_sysvar.rs'].decode()
    block = re.search(r'#\[serde\(rename_all = "camelCase"\)\]\s*pub struct UiClock \{([^}]+)\}', agave)[1]
    json_names = {}
    for field, type_ in re.findall(r'pub (\w+): (\w+),', block):
        need(field in wire and (type_ == 'UnixTimestamp') == wire[field][1], 'Agave scalar types disagree')
        need(f'{field}: clock.{field},' in agave, 'Agave projection disagrees')
        json_names[field] = re.sub(r'_(.)', lambda m: m[1].upper(), field)
    need(set(json_names) == set(wire), 'incomplete JSON field set')
    return slots, wire, json_names


def kit_file(work, archive_name, member):
    with tarfile.open(work/archive_name) as archive:
        info = archive.getmember(member)
        need(info.isfile() and 0 < info.size < 16_000_000, 'invalid package member')
        return archive.extractfile(info).read()


def signed_package(name, work, proof, revision):
    entry = proof['bundles'][name]
    env = entry['envelope']
    raw = base64.b64decode(env['payload'], validate=True)
    statement = strict_json(raw)
    expected = hashlib.sha512((work/(name+'.tgz')).read_bytes()).hexdigest()
    need(statement['predicateType'] == 'https://slsa.dev/provenance/v1'
         and statement['subject'] == [{'name': f'pkg:npm/{name}@1.6.2', 'digest': {'sha512': expected}}],
         'published subject differs')
    git_url = 'https://github.com/LiteSVM/litesvm'
    tag = 'refs/tags/node-v1.6.2'
    definition = statement['predicate']['buildDefinition']
    workflow = definition['externalParameters']['workflow']
    need(workflow == {'ref': tag, 'repository': git_url, 'path': '.github/workflows/release-node.yml'}
         and definition['resolvedDependencies'] == [{'uri': 'git+'+git_url+'@'+tag,
                                                     'digest': {'gitCommit': revision}}], 'build source differs')
    cert = ssl.DER_cert_to_PEM_cert(base64.b64decode(entry['certificate_der'], validate=True))
    (work/'leaf.pem').write_text(cert)
    (work/'root.pem').write_text(proof['fulcio_root_pem'])
    (work/'intermediate.pem').write_text(proof['fulcio_intermediate_pem'])
    openssl = '/usr/bin/openssl'
    run(openssl, ['verify', '-CAfile', 'root.pem', '-untrusted', 'intermediate.pem',
                  '-attime', str(entry['integrated_time']), 'leaf.pem'], work)
    sans = run(openssl, ['x509', '-in', 'leaf.pem', '-noout', '-ext', 'subjectAltName'], work).decode()
    need(sans.strip().splitlines()[-1].strip() == 'URI:'+git_url+'/'+workflow['path']+'@'+tag,
         'workflow certificate identity differs')
    (work/'key.pem').write_bytes(run(openssl, ['x509', '-in', 'leaf.pem', '-noout', '-pubkey'], work))
    (work/'signature').write_bytes(base64.b64decode(env['signatures'][0]['sig'], validate=True))
    kind = env['payloadType'].encode()
    need(kind == b'application/vnd.in-toto+json', 'unexpected statement type')
    pae = b' '.join((b'DSSEv1', str(len(kind)).encode(), kind, str(len(raw)).encode(), raw))
    run(openssl, ['dgst', '-sha256', '-verify', 'key.pem', '-signature', 'signature'], work, pae)


def prepare(work, files, kit):
    supply = strict_json(read_artifact(ROOT, SUPPLY))
    need(supply['native_revision'] == UPSTREAM[LITE][1], 'npm release revision')
    for name, row in supply['assets'].items():
        copy_release(name, kit/name, work/name, row['sha256'], executable=False)
        if name in ('bn.js.tgz', 'buffer-layout.tgz'):
            sri = 'sha512-' + base64.b64encode(hashlib.sha512((work/name).read_bytes()).digest()).decode()
            basename = name.removesuffix('.tgz')
            block = next((entry for entry in files['ts/yarn.lock'].decode().split('\n\n')
                          if entry.startswith(basename + '@') and sri in entry), '')
            need(sri == row['integrity'] and bool(block), 'Anchor dependency differs from its lock')
    proof = read_artifact(ROOT, 'superhunter/product_supply/clock-format-provenance.json')
    need(sha(proof) == '90f0713975712cf97405d6e0e0d4230d3875185d8221a1604b15dfcc7c5a9bd6', 'changed provenance evidence')
    for package_name in ('litesvm', 'litesvm-linux-x64-gnu'):
        signed_package(package_name, work, strict_json(proof), UPSTREAM[LITE][1])
    wrapper = strict_json(kit_file(work, 'litesvm.tgz', 'package/package.json'))
    upstream = strict_json(files['crates/node-litesvm/package.json'])
    need(wrapper['version'] == upstream['version'] == supply['version']
         and wrapper['optionalDependencies'][supply['platform_package']] == supply['version'], 'LiteSVM release link')
    node = kit_file(work, 'litesvm-linux-x64-gnu.tgz', 'package/litesvm.linux-x64-gnu.node')
    need(sha(node) == NAPI_SHA, 'different native addon')
    (work/'litesvm.node').write_bytes(node)
    (work/'bn.cjs').write_bytes(kit_file(work, 'bn.js.tgz', 'package/lib/bn.js'))
    (work/'layout.cjs').write_bytes(kit_file(work, 'buffer-layout.tgz', 'package/lib/Layout.js'))
    # Use the original numeric layout class and its signed/unsigned factories without
    # importing Anchor's unrelated public-key type, chain client or transaction modules.
    source = files['ts/packages/borsh/src/index.ts'].decode()
    section = source[source.index('class BNLayout extends'):source.index('export function u128')]
    imports = "import BN from './bn.cjs';\nimport layout from './layout.cjs';\nconst {Layout: LayoutCls, blob} = layout;\n"
    (work/'anchor.mts').write_text(imports + section)
    (work/'clock.mjs').write_bytes(read_artifact(ROOT, WORKER))
    (work/'sysvars.proto').write_bytes(files['fuzz/fixture/proto/sysvars.proto'])
    with ZipFile(work/'protoc.zip') as archive:
        member = archive.getinfo('bin/protoc')
        need(0 < member.file_size < 16_000_000, 'compiler size')
        compiler = archive.read(member)
    need(sha(compiler) == PROTOC_SHA, 'unreviewed protobuf compiler')
    (work/'protoc').write_bytes(compiler)
    (work/'protoc').chmod(0o500)


def varint(integer):
    data = bytearray()
    value = integer % (1 << 64)
    while value >= 128:
        data.append(128 | (value & 127))
        value >>= 7
    data.append(value)
    return bytes(data)


def project(case, observed, wire, names, work):
    need(set(observed) == set(case), 'native presence differs')
    proto_input = ''.join(f'{field}: {number}\n' for field, number in case.items()).encode()
    proto = work/'protoc'
    encoded = run(proto, ['-I.', '--encode=org.mollusk.svm.Clock', 'sysvars.proto'], work, proto_input)
    decoded = run(proto, ['-I.', '--decode=org.mollusk.svm.Clock', 'sysvars.proto'], work, encoded)
    received = {k: int(v) for k, v in re.findall(r'^(\w+): (-?\d+)$', decoded.decode(), re.M)}
    output, expected_wire = {}, bytearray()
    for key, (tag, signed) in sorted(wire.items(), key=lambda pair: pair[1][0]):
        if key not in case:
            need(key not in received, 'absent field acquired a value')
            continue
        value = case[key]
        need(observed[key]['lite'] == observed[key]['decoded'] == str(value)
             and bytes.fromhex(observed[key]['borsh']) == value.to_bytes(8, 'little', signed=signed),
             'native integer round trip')
        need(received.get(key, 0) == value, 'protobuf round trip')
        if value:
            expected_wire += varint(tag << 3) + varint(value)
        output[names[key]] = str(value)
    need(expected_wire == encoded, 'independent protobuf framing disagrees')
    return {'known_fields': sorted(case), 'unknown_fields': sorted(wire.keys()-case.keys()), 'protobuf_hex': encoded.hex(),
            'borsh_integer_hex': {k: v['borsh'] for k, v in observed.items()},
            'agave_fields_decimal_text': output}


def review(source_root):
    files = load_sources(source_root)
    slots, wire, names = shapes(files)
    header = read_artifact(ROOT, HEADER)
    need(sha(header) == HEADER_SHA, 'historical header changed')
    time = int(strict_json(header)['block']['timestamp'], 16)
    test = files['crates/node-litesvm/tests/sysvar.test.ts'].decode()
    control = re.search(r'new Clock\((\d+n(?:, \d+n){4})\)', test)
    need(control is not None, 'upstream reference control changed')
    cases = {'census_header': {'unix_timestamp': time},
             'upstream_clock_control': dict(zip((s[0] for s in slots),
                                                (int(v[:-1]) for v in control[1].split(', ')), strict=True)),
             'signed_and_unsafe_js_integer': {'slot': 2**53+1, 'unix_timestamp': -1},
             'known_zero': {'unix_timestamp': 0}, 'unknown': {}}
    payload = {'keys': [k for k, _ in slots], 'signed': [s for _, s in slots],
               'cases': {k: {name: str(value) for name, value in c.items()} for k, c in cases.items()}}
    with tempfile.TemporaryDirectory(prefix='nqc-slot-time-') as tmp:
        work = Path(tmp)
        prepare(work, files, Path(os.environ.get('NQC_SLOT_KIT', '/no-slot-kit')))
        node = runtime_path('node')
        calc = strict_json(run(node, ['--permission', '--allow-addons', '--allow-fs-read=' + str(work),
                                      '--disable-warning=ExperimentalWarning', 'clock.mjs'], work, canonical(payload)))
        need(calc['rejected'] == ['negativeSlot', 'oversizedSlot', 'oversizedTime'], 'native range controls')
        reports = {k: project(c, calc['results'][k], wire, names, work) for k, c in cases.items()}
    need(reports['known_zero']['protobuf_hex'] == reports['unknown']['protobuf_hex'] == ''
         and reports['known_zero']['known_fields'] != reports['unknown']['known_fields'], 'lost field presence')
    roles = {LITE: ('executable', 'native clock BigInt field conversion and overflow rejection'),
             ANCHOR: ('executable', 'signed and unsigned 64-bit Borsh numeric encode/decode'),
             MOLLUSK: ('reference', 'proto3 field types and tags consumed by the official protobuf compiler'),
             AGAVE: ('reference', 'UI clock field names and type mapping with explicit missing-field coverage')}
    return {repo: {'revision': UPSTREAM[repo][1], 'role': role, 'operation': operation,
                   'source_files': UPSTREAM[repo][2], 'input_sha256': HEADER_SHA,
                   'results': reports, 'rejected_range_controls': calc['rejected'], 'protoc_sha256': PROTOC_SHA,
                   'native_addon_sha256': NAPI_SHA}
            for repo, (role, operation) in roles.items()}
