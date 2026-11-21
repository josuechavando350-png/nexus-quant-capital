"""Attest explicit boolean application policy in three pinned Android manifest resources."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from .product_reasoning import EvidenceError
from .safe_io import canonical

JADX = 'skylot/jadx'
APKTOOL = 'iBotPeaches/Apktool'
MASTG = 'OWASP/mastg'
ANDROID = 'http://schemas.android.com/apk/res/android'
JBASE = 'jadx-core/src/main/resources/android/'
ATTRS = JBASE + 'attrs_manifest.xml'
IDS = JBASE + 'res-map.txt'
APKBASE = 'brut.apktool/apktool-lib/src/'
AAPT = APKBASE + 'main/resources/prebuilt/linux/aapt2'
AAPT_HASH = '6fbed5edaddcfbee99a3ae6e7208c8654c6cb2bedb4ed5cbbf4e154d7d38a745'
ARTIFACTS = {
    'framework': (APKTOOL, APKBASE + 'main/resources/prebuilt/android-framework.jar'),
    'empty_9patch': (APKTOOL, APKBASE + 'test/resources/empty_9patch/empty_9patch.apk'),
    'resources_only': (JADX, 'jadx-cli/src/test/resources/samples/resources-only.apk'),
}
RULES = {'debuggable': ('rules/mastg-android-debuggable-flag.yml', 'mastg-android-debuggable-flag'),
         'allowBackup': ('rules/mastg-android-backup-manifest.yml', 'mastg-android-backup-manifest-allow-backup')}
PINS = {JADX: ('098-jadx', '3cbbc2348141b7b51dbec2b227f334d6785547e6'),
        APKTOOL: ('099-apktool', 'fbaeb4779d7aaed2c3097cd496de2bc9150ab869'),
        MASTG: ('200-mastg', 'e8183038d7a88c1ac962732d6e3f6e7f40a0251c')}


def sha(raw):
    return sha256(raw).hexdigest()


def source_files(root):
    paths = {JADX: [ATTRS, IDS], APKTOOL: [AAPT], MASTG: [r[0] for r in RULES.values()]}
    for repo, path in ARTIFACTS.values():
        paths[repo].append(path)
    result = {}
    for repo, (folder, revision) in PINS.items():
        base = ['git', '--no-replace-objects', '-C', str(Path(root) / folder)]
        def git(*args):
            return subprocess.run([*base, *args], check=True, capture_output=True, timeout=15).stdout
        if git('rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('Android source checkout revision differs')
        result[repo] = {path: git('cat-file', 'blob', revision + ':' + path) for path in paths[repo]}
    if sha(result[APKTOOL][AAPT]) != AAPT_HASH:
        raise EvidenceError('Android native decoder differs from its approved binary')
    return result


def contracts(sources):
    import yaml
    resources = ET.fromstring(sources[JADX][ATTRS])
    application = resources.find("declare-styleable[@name='AndroidManifestApplication']")
    if application is None:
        raise EvidenceError('application attributes missing from JADX')
    names = {e.get('name') for e in application.findall('attr')}
    mapping = {}
    rules = {}
    for name, (filename, rid) in RULES.items():
        records = [r for r in yaml.safe_load(sources[MASTG][filename])['rules'] if r['id'] == rid]
        if len(records) != 1 or records[0]['languages'] != ['xml']:
            raise EvidenceError('missing static XML policy rule')
        patterns = records[0]['patterns']
        if len(patterns) != 1 or set(patterns[0]) != {'pattern'}:
            raise EvidenceError('unsupported Android policy rule')
        match = re.fullmatch(r'android:(\w+)="\$ARG"', patterns[0]['pattern'])
        if (not match or match[1] != name or name not in names
                or resources.find(f"attr[@name='{name}'][@format='boolean']") is None):
            raise EvidenceError('policy selector differs from the documented boolean contract')
        matches = re.findall(rb'^([0-9a-f]{8})=attr/' + name.encode() + rb'$', sources[JADX][IDS], re.M)
        if len(matches) != 1:
            raise EvidenceError('ambiguous Android resource identifier')
        mapping[name] = int(matches[0], 16)
        rules[name] = records[0]['id']
    return mapping, rules


def manifest(archive):
    with zipfile.ZipFile(BytesIO(archive)) as z:
        matches = [i for i in z.infolist() if i.filename == 'AndroidManifest.xml']
        if len(matches) != 1 or not 8 <= matches[0].file_size <= 512_000:
            raise EvidenceError('missing, ambiguous or oversized Android manifest')
        return z.read(matches[0])


def pool_strings(block):
    count, _, flags, start = struct.unpack_from('<4I', block, 8)
    header = struct.unpack_from('<H', block, 2)[0]
    if header < 28 or header + 4 * count > start or start > len(block):
        raise EvidenceError('invalid Android string offsets')
    utf8 = bool(flags & 0x100)
    def length(p):
        if utf8:
            n = block[p]
            return (((n & 127) << 8) | block[p + 1], p + 2) if n & 128 else (n, p + 1)
        n = struct.unpack_from('<H', block, p)[0]
        return (((n & 0x7fff) << 16) | struct.unpack_from('<H', block, p+2)[0], p+4) if n & 0x8000 else (n, p+2)
    table = []
    for i in range(count):
        off = start + struct.unpack_from('<I', block, header + 4 * i)[0]
        n, off = length(off)
        if utf8:
            n, off = length(off)
        else:
            n *= 2
        if off + n + (1 if utf8 else 2) > len(block):
            raise EvidenceError('truncated Android manifest string')
        table.append(block[off:off+n].decode('utf-8' if utf8 else 'utf-16le'))
    return table


def decode(data, ids):
    """Read the typed attributes and resource map independently of AAPT2's text dump."""
    if len(data) < 8 or struct.unpack_from('<HHI', data) != (3, 8, len(data)):
        raise EvidenceError('Android XML length differs')
    offset = 8
    strings, resmap, stack, flags = [], [], [], {}
    apps = 0
    while offset < len(data):
        kind, head, size = struct.unpack_from('<HHI', data, offset)
        if size < head or head < 8 or offset + size > len(data):
            raise EvidenceError('invalid Android XML chunk')
        block = data[offset:offset+size]
        if kind == 1:
            strings = pool_strings(block)
        elif kind == 0x180:
            resmap = [value for value, in struct.iter_unpack('<I', block[head:])]
        elif kind == 0x102:
            name_index, begin, width, count = struct.unpack_from('<IHHH', block, head + 4)
            tag = strings[name_index]
            if stack == ['manifest'] and tag == 'application':
                apps += 1
                if width < 20 or head + begin + width * count > len(block):
                    raise EvidenceError('invalid Android attributes')
                for i in range(count):
                    pos = head + begin + width * i
                    ns, index, _, value_size, _, typ, value = struct.unpack_from('<IIIHBBI', block, pos)
                    key = strings[index]
                    if key not in ids or ns == 0xffffffff or strings[ns] != ANDROID:
                        continue
                    if (index >= len(resmap) or resmap[index] != ids[key] or typ != 0x12 or
                            value_size != 8 or value not in (0, 1, 0xffffffff) or key in flags):
                        raise EvidenceError('Android boolean name, identifier or value type differs')
                    flags[key] = (bool(value), offset + pos + 16)
            stack.append(tag)
        elif kind == 0x103:
            idx = struct.unpack_from('<I', block, head + 4)[0]
            if not stack or stack.pop() != strings[idx]:
                raise EvidenceError('unbalanced manifest')
        offset += size
    if stack or apps != 1:
        raise EvidenceError('expected exactly one manifest application')
    return flags


def aapt_tree(binary, work, data):
    archive = work / 'manifest.zip'
    # Only the declarative XML enters the sandbox. Omit all other package members.
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('AndroidManifest.xml', data)
    command = ['/usr/bin/unshare', '--user', '--map-root-user', '--net', '--',
               '/usr/bin/prlimit', '--as=268435456', '--cpu=8', '--nofile=32', '--',
               '/usr/bin/bwrap', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
               '--ro-bind', str(binary), '/reader', '--ro-bind', str(archive), '/manifest.zip',
               '--clearenv', '--', '/reader', 'dump', 'xmltree', '/manifest.zip', '--file', 'AndroidManifest.xml']
    run = subprocess.run(command, check=True, capture_output=True, timeout=12)
    if run.stderr or not 1 <= len(run.stdout) <= 1_000_000:
        raise EvidenceError('unexpected AAPT2 diagnostics or dump size')
    return run.stdout.decode()


def native_flags(text, ids):
    result = {}
    nodes = []
    for line in text.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith('E: '):
            while nodes and nodes[-1][0] >= indent:
                nodes.pop()
            nodes.append((indent, stripped.split()[1]))
        elif [n for _, n in nodes] == ['manifest', 'application'] and stripped.startswith('A: ' + ANDROID + ':'):
            for name, rid in ids.items():
                start = 'A: ' + ANDROID + ':' + name + '('
                if stripped.startswith(start):
                    match = re.fullmatch(re.escape(start) + r'(0x[0-9a-f]+)\)=(true|false)', stripped)
                    if not match or int(match[1], 16) != rid or name in result:
                        raise EvidenceError('AAPT2 attribute does not match the reviewed contract')
                    result[name] = match[2] == 'true'
    return result


def review(source_root: Path):
    sources = source_files(source_root)
    ids, rules = contracts(sources)
    raws = {name: manifest(sources[repo][path]) for name, (repo, path) in ARTIFACTS.items()}
    known = decode(raws['empty_9patch'], ids)
    if not known.get('debuggable', (False,))[0]:
        raise EvidenceError('missing original positive Android fixture')
    control = bytearray(raws['empty_9patch'])
    struct.pack_into('<I', control, known['debuggable'][1], 0)
    raws['changed_debuggable_to_false'] = bytes(control)
    reports = {}
    with tempfile.TemporaryDirectory(prefix='nqc-manifest-') as folder:
        work = Path(folder)
        binary = work / 'aapt2'
        binary.write_bytes(sources[APKTOOL][AAPT])
        binary.chmod(0o500)
        for name, data in raws.items():
            direct = {k: value for k, (value, _) in decode(data, ids).items()}
            text = aapt_tree(binary, work, data)
            if native_flags(text, ids) != direct:
                raise EvidenceError('AAPT2 and independent resource/attribute decoder disagree')
            reports[name] = {'manifest_sha256': sha(data), 'aapt_dump_sha256': sha(text.encode()),
                             'observations': {rules[k]: direct.get(k) for k in rules}}
    missing = dict.fromkeys(rules.values())
    if (reports['framework']['observations'] != missing or reports['resources_only']['observations'] != missing
            or reports['empty_9patch']['observations'] != dict.fromkeys(rules.values(), True)
            or reports['changed_debuggable_to_false']['observations'] != {rules['debuggable']: False, rules['allowBackup']: True}):
        raise EvidenceError('Android policy controls changed')
    join = sha(canonical(reports))
    rows = {APKTOOL: {'operation': 'decode pinned binary Android manifests with the Apktool-distributed AAPT2',
                      'reports': reports, 'compiled_here': False},
            JADX: {'operation': 'validate application attribute scope, boolean type and numeric identity',
                   'resource_ids': {k: hex(v) for k, v in ids.items()}, 'type': 'boolean'},
            MASTG: {'operation': 'classify explicit debugging and backup declarations, preserving absent values',
                    'selectors': rules, 'observations': {k: v['observations'] for k, v in reports.items()}}}
    for repo, row in rows.items():
        row.update(revision=PINS[repo][1], manifest_set_sha256=join,
                   source_sha256={name: sha(data) for name, data in sources[repo].items()})
    return rows
