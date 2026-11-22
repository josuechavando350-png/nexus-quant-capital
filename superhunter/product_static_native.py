"""Pinned offline C diagnostics and native instruction inspection for owned inputs."""
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from xml.etree import ElementTree

from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json

REPOSITORIES = {'cppcheck-opensource/cppcheck': 'executable',
                'capstone-engine/capstone': 'executable'}
PINS = 'superhunter/product_supply/static-native-pins.json'
PINS_SHA = '7c13adf3377a55adb9dc47fc1f8cef83f8e25bc967d0c2fbe712d29455fc9df7'
CASES = 'superhunter/product_supply/static-native-cases.json'
HELPER = 'superhunter/product_supply/static-native-capstone-helper.txt'
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def inputs():
    raw = read_artifact(ROOT, PINS)
    if sha(raw) != PINS_SHA:
        raise EvidenceError('static native producer pins differ')
    pins = strict_json(raw)
    raw = read_artifact(ROOT, CASES)
    if (sha(raw) != pins['cases_sha256'] or
            sha(read_artifact(ROOT, HELPER)) != pins['helper_source_sha256']):
        raise EvidenceError('static native owned inputs differ')
    return pins, strict_json(raw)


def cppcheck_result(raw, case, source):
    if len(raw) > MAX_BYTES or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
        raise EvidenceError('invalid Cppcheck XML size or declaration')
    try:
        report = ElementTree.fromstring(raw)
        producer, errors = report
        if (report.tag, report.get('version'), producer.tag, producer.get('version'), errors.tag) != (
                'results', '2', 'cppcheck', '2.23 dev', 'errors'):
            raise EvidenceError('Cppcheck producer or output schema differs')
        issues = []
        for row in errors:
            if row.tag != 'error':
                raise EvidenceError('Cppcheck output includes an unknown record')
            locations = row.findall('location')
            if not locations:
                raise EvidenceError('Cppcheck diagnostic has no location')
            for location in locations:
                if (location.get('file') != case or
                        not 1 <= int(location.get('line', 0)) <= len(source.splitlines())):
                    raise EvidenceError('Cppcheck location is outside the owned input')
            first = locations[0]
            issues.append({'id': row.attrib['id'], 'severity': row.attrib['severity'],
                           'cwe': int(row.attrib['cwe']), 'line': int(first.attrib['line']),
                           'column': int(first.attrib['column'])})
    except (ElementTree.ParseError, KeyError, TypeError, ValueError) as exc:
        raise EvidenceError('malformed Cppcheck evidence') from exc
    expected = {
        'null.c': [{'id': 'nullPointer', 'severity': 'error', 'cwe': 476, 'line': 3, 'column': 13}],
        'bounds.c': [{'id': 'arrayIndexOutOfBounds', 'severity': 'error', 'cwe': 788, 'line': 3, 'column': 18}],
        'clean.c': [],
    }
    # Verify the locations identify the independently constructed faulty expressions.
    expressions = {'null.c': ('*pointer', 11), 'bounds.c': ('values[2]', 11)}
    if case in expressions:
        expression, column = expressions[case]
        if source.splitlines()[2][column:column+len(expression)] != expression:
            raise EvidenceError('owned C diagnostic control changed')
    if case not in expected or issues != expected[case]:
        raise EvidenceError('Cppcheck positive or clean control disagrees')
    return {'source_sha256': sha(source.encode()), 'diagnostics': issues}


def relative_target(raw, address):
    if len(raw) == 5 and raw[0] in (0xe8, 0xe9):
        return address + 5 + int.from_bytes(raw[1:], 'little', signed=True)
    if len(raw) == 2 and (raw[0] == 0xeb or 0x70 <= raw[0] <= 0x7f):
        return address + 2 + int.from_bytes(raw[1:], 'little', signed=True)
    if len(raw) == 6 and raw[0] == 0x0f and 0x80 <= raw[1] <= 0x8f:
        return address + 6 + int.from_bytes(raw[2:], 'little', signed=True)
    return None


def decoder_result(report, raw, address):
    if (report.get('api_version') != [6, 0] or type(report.get('input_bytes')) is not int or
            report['input_bytes'] != len(raw) or not isinstance(report.get('instructions'), list)):
        raise EvidenceError('Capstone producer or input size differs')
    position, rows = 0, []
    for row in report['instructions']:
        if (set(row) != {'address', 'size', 'bytes', 'mnemonic', 'direct_target'} or
                type(row['address']) is not int or row['address'] != address + position or
                type(row['size']) is not int or not 1 <= row['size'] <= 15 or
                position + row['size'] > len(raw) or
                row['bytes'] != raw[position:position+row['size']].hex() or
                not isinstance(row['mnemonic'], str) or not re.fullmatch('[a-z][a-z0-9 ]*', row['mnemonic']) or
                (row['direct_target'] is not None and (type(row['direct_target']) is not int or
                                                      not 0 <= row['direct_target'] < 2**64))):
            raise EvidenceError('Capstone instruction spans differ from input bytes')
        expected = relative_target(raw[position:position+row['size']], row['address'])
        if expected is not None and row['direct_target'] != expected:
            raise EvidenceError('Capstone relative branch disagrees with encoded displacement')
        rows.append(row)
        position += row['size']
    if type(report.get('decoded_bytes')) is not int or report['decoded_bytes'] != position:
        raise EvidenceError('Capstone decoded coverage differs')
    boundaries = {r['address'] for r in rows}
    invalid = [r['direct_target'] for r in rows if r['direct_target'] is not None
               and address <= r['direct_target'] < address + position and r['direct_target'] not in boundaries]
    return {'input_sha256': sha(raw), 'input_bytes': len(raw), 'decoded_bytes': position,
            'undecoded_suffix': raw[position:].hex(), 'misaligned_internal_targets': sorted(invalid),
            'instructions': rows}


def executable_spans(raw):
    if (len(raw) < 64 or raw[:6] != b'\x7fELF\x02\x01' or
            int.from_bytes(raw[18:20], 'little') != 62):
        raise EvidenceError('expected an owned x86-64 ELF')
    entry, offset = struct.unpack_from('<QQ', raw, 24)
    size, count = struct.unpack_from('<HH', raw, 54)
    if size != 56 or not 1 <= count <= 64 or offset + size*count > len(raw):
        raise EvidenceError('ELF program headers exceed the owned image')
    spans = []
    for index in range(count):
        kind, flags, file_offset, address, _, file_bytes, memory_bytes, _ = struct.unpack_from(
            '<IIQQQQQQ', raw, offset + index*size)
        if kind == 1 and flags & 1:
            if file_bytes > memory_bytes or file_offset + file_bytes > len(raw):
                raise EvidenceError('ELF executable segment exceeds the owned image')
            spans.append((address, file_offset, file_bytes))
    return entry, spans


def image_bytes(raw, spans, address, length):
    matches = [(offset + address - start) for start, offset, size in spans
               if start <= address and address + length <= start + size]
    if len(matches) != 1:
        raise EvidenceError('native address has no unambiguous executable file mapping')
    return raw[matches[0]:matches[0]+length]


def objdump_spans(output):
    rows = []
    for line in output.splitlines():
        fields = line.split('\t')
        if len(fields) >= 3 and re.fullmatch(r'\s*[0-9a-f]+:', fields[0]):
            raw = fields[1].strip().replace(' ', '')
            if not re.fullmatch(r'(?:[0-9a-f]{2})+', raw):
                raise EvidenceError('objdump emitted a malformed instruction')
            rows.append((int(fields[0].strip()[:-1], 16), raw))
    return rows


def run(kit):
    """Run fixed owned controls and inspect the pinned NQC Geth helper, without network."""
    kit = Path(kit)
    pins, cases = inputs()
    with tempfile.TemporaryDirectory(prefix='nqc-static-native-') as tmp:
        work = Path(tmp)
        (work/'cfg').mkdir()
        for name, pin in pins['files'].items():
            copy_release(name, kit/name, work/name, pin['sha256'], limit=pin['bytes'],
                         executable=name in ('cppcheck', 'capstone-decoder', 'objdump'))
        env = {'HOME': tmp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TMPDIR': tmp}

        def execute(args):
            return subprocess.run([*ISOLATE, *map(str, args)], cwd=work, env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=45)

        cpp = {}
        for name, source in sorted(cases['c'].items()):
            (work/name).write_text(source)
            process = execute([work/'cppcheck', '--quiet', '--xml', '--xml-version=2', '--enable=warning',
                               '--language=c', '--std=c11', '--platform=unix64', '--error-exitcode=0', name])
            if process.stdout:
                raise EvidenceError('Cppcheck emitted unexpected standard output')
            cpp[name] = cppcheck_result(process.stderr, name, source)

        def decode(raw, address):
            process = execute([work/'capstone-decoder', raw.hex(), str(address)])
            if process.stderr:
                raise EvidenceError('Capstone emitted unexpected diagnostics')
            result = decoder_result(strict_json(process.stdout), raw, address)
            used = result['decoded_bytes']
            if used:
                (work/'instructions.bin').write_bytes(raw[:used])
                other = execute([work/'objdump', '-D', '-b', 'binary', '-m', 'i386:x86-64', '-M', 'intel',
                                 '--adjust-vma=' + str(address), '-w', work/'instructions.bin'])
                if objdump_spans(other.stdout.decode()) != [(r['address'], r['bytes']) for r in result['instructions']]:
                    raise EvidenceError('Capstone and objdump disagree on instruction boundaries')
            return result

        controls = {name: decode(bytes.fromhex(c['hex']), c['address']) for name, c in cases['x86'].items()}
        if (controls['aligned']['misaligned_internal_targets'] or controls['aligned']['undecoded_suffix'] or
                controls['misaligned']['misaligned_internal_targets'] != [4106] or
                controls['truncated']['decoded_bytes'] != 3 or controls['truncated']['undecoded_suffix'] != 'e90100'):
            raise EvidenceError('native branch or truncation controls disagree')
        raw = (work/'geth-header').read_bytes()
        entry, spans = executable_spans(raw)
        first = image_bytes(raw, spans, entry, 5)
        if first[0] != 0xe9:
            raise EvidenceError('owned Geth entrypoint is not the expected relative jump')
        target = relative_target(first, entry)
        owned = {'entrypoint': entry, 'entry_target': target,
                 'entry': decode(image_bytes(raw, spans, entry, 32), entry),
                 'startup': decode(image_bytes(raw, spans, target, 64), target)}
        if owned['entry']['instructions'][0]['direct_target'] != target:
            raise EvidenceError('owned entrypoint target disagrees')
    sections = {'cppcheck': {'cases': cpp}, 'capstone': {'controls': controls, 'owned_geth': owned}}
    return {'schema_version': 1, 'query': 'static-native', 'pins_sha256': PINS_SHA,
            'producers': pins['sources'], 'input_hashes': {'cases': pins['cases_sha256'],
                'owned_geth': pins['files']['geth-header']['sha256']},
            'scope': 'OWNED static controls and pinned NQC executable; original vulnerability findings: 0',
            'sections': sections, 'sections_sha256': sha(canonical(sections))}
