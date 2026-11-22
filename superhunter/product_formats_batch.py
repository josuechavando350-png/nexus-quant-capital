"""Check that fixed NQC proof obligations survive in a relocatable object, without running it."""
from io import BytesIO
from pathlib import Path
import re
import tarfile
import tempfile

from .product_languages_batch import run, write_files
from .product_license_choices import alternatives, tree
from .product_proof_languages import c_program
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .product_spdx_groups import TOKEN
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

RADARE = 'radareorg/radare2'
CAPSTONE = 'capstone-engine/capstone'
PROJECTS = {
    RADARE: ('129-radare2', '3f321aa3aeda3a69fa12b1df9840648c31b4df14'),
    CAPSTONE: ('132-capstone', 'ccd25ab39eea534afbb70cfb047310c5a9962553'),
}
PATHS = ('libr/bin/d/elf64.r2', 'libr/bin/d/elf_enums.r2')
INPUTS = {108: 'BSD-3-Clause AND (BSD-3-Clause AND Apache-2.0)',
          129: 'LGPL-3.0-only AND GPL-1.0-or-later', 199: 'CC-BY-SA-4.0 AND CC0-1.0'}
WORKER = """#include <capstone/capstone.h>
#include <stdio.h>
int main(void) {
    size_t n, count;
    unsigned char bytes[2048];
    csh handle;
    cs_insn *instructions = NULL;
    if (cs_open(CS_ARCH_X86, CS_MODE_64, &handle) != CS_ERR_OK) return 2;
    n = fread(bytes, 1, sizeof bytes, stdin);
    if (!n || n == sizeof bytes || ferror(stdin)) return 3;
    count = cs_disasm(handle, bytes, n, 0, 0, &instructions);
    if (!count) return 4;
    for (size_t i = 0; i < count; ++i) {
        cs_insn *insn = instructions + i;
        printf("%llu %u %u\\n", (unsigned long long)insn->address, insn->size, insn->id == X86_INS_CALL);
    }
    cs_free(instructions, count);
    cs_close(&handle);
    return 0;
}
"""


def selected(repo, rev, keep):
    entries = {}
    for item in git(repo, 'ls-tree', '-rz', rev).split(b'\0'):
        if not item:
            continue
        meta, name = item.split(b'\t', 1)
        path = name.decode()
        if keep(path):
            mode, kind, oid = meta.split()
            if kind != b'blob' or mode not in (b'100644', b'100755'):
                raise EvidenceError('unexpected Git object in the object-format review')
            entries[path] = oid.decode()
    if not entries or len(entries) > 700:
        raise EvidenceError('unexpected size of the reviewed native source set')
    archive = git(repo, 'archive', '--format=tar', rev, '--', *entries)
    result = {}
    with tarfile.open(fileobj=BytesIO(archive), mode='r:') as source:
        for item in source:
            if item.isdir():
                continue
            if item.name not in entries or not item.isfile() or item.name in result:
                raise EvidenceError('unexpected file in the native source archive')
            data = source.extractfile(item).read()
            if git_object('blob', data) != entries[item.name]:
                raise EvidenceError('native source differs from pinned blob')
            result[item.name] = data
    if set(result) != set(entries):
        raise EvidenceError('missing dependency in native source archive')
    return result, sha(canonical(entries))


def cap_file(name):
    p = Path(name)
    if len(p.parts) == 1:
        return p.suffix in ('.c', '.h', '.mk') or name == 'Makefile'
    return (name.startswith('arch/X86/') or name.startswith('include/capstone/') or
            (len(p.parts) == 3 and p.parts[0] == 'arch' and p.name.endswith('Module.h')))


def repositories(root):
    result = {}
    for name, (directory, revision) in PROJECTS.items():
        repo = root/directory
        if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('unexpected source checkout for ' + name)
        result[name] = selected(repo, revision, (lambda p: p in PATHS) if name == RADARE else cap_file)
    return result


def claims():
    rows = strict_json(read_artifact(ROOT, 'superhunter/product_supply/source-inventory.json'))['entries']
    selected_values = {e['id']: e['notice_scan']['detected_expression'] for e in rows if e['id'] in INPUTS}
    if selected_values != INPUTS:
        raise EvidenceError('reviewed proof inputs differ from the product inventory')
    result = []
    for expr in INPUTS.values():
        names = sorted(set(TOKEN.findall(expr)) - {'AND', '(', ')'})
        result.append({'names': names, 'original': tree(expr, names),
                       'candidate': alternatives([(1 << len(names))-1], len(names))})
    return result


def schema_records(raw):
    records = {}
    for line in raw.decode().splitlines():
        if not line.startswith('pf.'):
            continue
        kind, fmt, *fields = line.split()
        if kind not in ('pf.elf_header', 'pf.elf_shdr'):
            continue
        tokens = re.findall(r'\?|\[(?:2|4|8)\]E|N2|[qx]', fmt)
        sizes = {'?': 16, 'q': 8, 'x': 4, 'N2': 2, '[2]E': 2, '[4]E': 4, '[8]E': 8}
        if ''.join(tokens) != fmt or len(tokens) != len(fields):
            raise EvidenceError('unrecognized radare2 ELF field definition')
        records[kind] = [(re.sub(r'^\([^()]+\)', '', f), sizes[t]) for f, t in zip(fields, tokens)]
    if sorted(records) != ['pf.elf_header', 'pf.elf_shdr']:
        raise EvidenceError('incomplete radare2 ELF schema')
    return records


def record(raw, fields, start=0):
    result = {}
    for name, size in fields:
        if start + size > len(raw):
            raise EvidenceError('truncated ELF structure')
        result[name] = int.from_bytes(raw[start:start+size], 'little')
        start += size
    return result


def named_value(enums, kind, label):
    definitions, = re.findall(r'enum '+kind+r' \{([^{}]+)\}', enums.decode())
    value, = [v for k, v in (s.split('=') for s in definitions.split(',')) if k.strip() == label]
    return int(value, 0)


def slice_section(raw, section):
    offset, size = section['offset'], section['size']
    if not size or offset+size > len(raw):
        raise EvidenceError('invalid fixed-object section range')
    return raw[offset:offset+size]


def read_text(raw, schemas):
    if not raw.startswith(b'\x7fELF\x02\x01\x01'):
        raise EvidenceError('expected an ELF64 little-endian object')
    records = schema_records(schemas[PATHS[0]])
    header = record(raw, records['pf.elf_header'])
    enums = schemas[PATHS[1]]
    if ((header['type'], header['machine']) != (named_value(enums, 'elf_type', 'ET_REL'),
            named_value(enums, 'elf_machine', 'EM_X86_64')) or header['shentsize'] != 64
            or not 0 < header['shstrndx'] < header['shnum'] <= 64 or header['phnum'] != 0):
        raise EvidenceError('ELF header outside fixed review scope')
    sections = [record(raw, records['pf.elf_shdr'], header['shoff']+i*header['shentsize'])
                for i in range(header['shnum'])]
    names = slice_section(raw, sections[header['shstrndx']])
    wanted = {}
    for section in sections:
        start = section['name']
        end = names.find(b'\x00', start)
        if end < start:
            raise EvidenceError('invalid section string')
        name = names[start:end]
        if name in (b'.text', b'.rodata'):
            if name in wanted:
                raise EvidenceError('duplicate proof section')
            wanted[name] = slice_section(raw, section)
    if set(wanted) != {b'.text', b'.rodata'}:
        raise EvidenceError('missing proof code or assertion labels')
    text, labels = wanted[b'.text'], wanted[b'.rodata']
    return text, labels, {'machine': 'EM_X86_64', 'type': 'ET_REL', 'sections': header['shnum'],
                          'object_sha256': sha(raw), 'text_size': len(text), 'text_sha256': sha(text),
                          'labels_sha256': sha(labels)}


def gcc_object(work, source):
    (work/'proof.c').write_text(source)
    (work/'decl.h').write_text('extern void __CPROVER_assert(_Bool, const char *);\n')
    run(work, ['/usr/bin/gcc', '-std=c11', '-O0', '-m64', '-fno-pie', '-fno-stack-protector',
               '-fno-asynchronous-unwind-tables', '-include', 'decl.h', '-c', 'proof.c', '-o', 'proof.o'])
    return sha(source.encode()), (work/'proof.o').read_bytes()


def check_calls(text, string_data, native, listing, relocations, expected):
    decoded = [tuple(map(int, line.split())) for line in native.splitlines()]
    independent = []
    disassembly = {}
    for line in listing.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\t([0-9a-f ]+)\t(\S+)(?:\s+(.*))?$', line)
        if m:
            address = int(m[1], 16)
            independent.append((address, len(bytes.fromhex(m[2])), int(m[3] == 'call')))
            disassembly[address] = (m[3], m[4] or '')
    offset = 0
    for address, size, _ in decoded:
        if address != offset or size < 1:
            raise EvidenceError('noncontiguous native instruction coverage')
        offset += size
    if decoded != independent or not decoded or offset != len(text):
        raise EvidenceError('Capstone instruction coverage differs from the independent disassembler')
    sites = {o+1 for o, size, call in decoded if call and size == 5}
    symbols = []
    for line in relocations.splitlines():
        m = re.match(r'^([0-9a-f]+)\s+[0-9a-f]+\s+R_X86_64_PLT32\s+[0-9a-f]+\s+(\w+) - 4$', line)
        if m:
            symbols.append((int(m[1], 16), m[2]))
    if len(symbols) != len(sites) or {offset for offset, _ in symbols} != sites:
        raise EvidenceError('compiler call boundaries and relocation locations disagree')
    targets = [label for _, label in symbols]
    if set(targets) != {'__VERIFIER_nondet_bool', '__CPROVER_assert'}:
        raise EvidenceError('unexpected external helper in local proof object')
    # For these fixed SysV AMD64 objects GCC puts the bound assertion label in ESI.
    label_loads = {}
    for line in relocations.splitlines():
        match = re.match(r'^([0-9a-f]+)\s+[0-9a-f]+\s+R_X86_64_32\s+[0-9a-f]+\s+\.rodata \+ ([0-9a-f]+)$', line)
        if match:
            start = int(match[1], 16)-1
            offset = int(match[2], 16)
            word = string_data[offset:].split(b'\0', 1)[0]
            if (not re.fullmatch(rb'nqc_[0-9]+', word) or (start, 5, 0) not in decoded or
                    disassembly[start] != ('mov', '$0x0,%esi') or start in label_loads):
                raise EvidenceError('unbound proof label relocation')
            label_loads[start] = word.decode()
    labels = []
    for site, target in symbols:
        if target != '__CPROVER_assert':
            continue
        prior = [addr for addr in label_loads if addr < site-1]
        if not prior:
            raise EvidenceError('assertion has no concrete label argument')
        start = max(prior)
        if any(op != 'mov' or not operands.endswith(',%edi') for addr, (op, operands) in disassembly.items()
               if start < addr < site-1):
            raise EvidenceError('unexpected operation between the bound label and assertion')
        labels.append(label_loads.pop(start))
    if label_loads:
        raise EvidenceError('unconsumed assertion label')
    assertions = targets.count('__CPROVER_assert')
    return {'instructions': len(decoded), 'external_calls': len(sites), 'assertion_calls': assertions,
            'expected_assertions': expected, 'bound_labels': labels,
            'covers_reviewed_obligations': labels == [f'nqc_{i}' for i in range(expected)],
            'boundaries_sha256': sha(canonical(decoded))}


def review(source_root: Path):
    refs = repositories(source_root)
    schemas, r2_manifest = refs[RADARE]
    cap_files, cap_manifest = refs[CAPSTONE]
    obligations = claims()
    objects, checks = {}, {}
    with tempfile.TemporaryDirectory(prefix='nqc-proof-object-') as tmp:
        work = Path(tmp)
        write_files(work, cap_files)
        run(work, ['/usr/bin/make', '-j2', 'CAPSTONE_ARCHS=x86', 'CAPSTONE_X86_REDUCE=yes', 'CAPSTONE_SHARED=no',
                   'CAPSTONE_STATIC=yes', 'CAPSTONE_X86_ATT_DISABLE=yes', 'libcapstone.a'])
        (work/'observe.c').write_text(WORKER)
        run(work, ['/usr/bin/gcc', '-Iinclude', 'observe.c', 'libcapstone.a', '-o', 'observe'])
        original = c_program('cbmc', obligations)
        if original.count('"nqc_2"') != 1:
            raise EvidenceError('proof emitter no longer has the reviewed label')
        cases = {'original': original, 'missing_obligation': c_program('cbmc', obligations[:-1]),
                 'duplicate_label': original.replace('"nqc_2"', '"nqc_1"')}
        for case, source in cases.items():
            source_id, raw = gcc_object(work, source)
            text, labels, header = read_text(raw, schemas)
            for section, data in (('.text', text), ('.rodata', labels)):
                run(work, ['/usr/bin/objcopy', '-O', 'binary', '--only-section='+section, 'proof.o', 'section.bin'])
                if data != (work/'section.bin').read_bytes():
                    raise EvidenceError('radare2 section definition and GNU object parser disagree')
            objects[case] = {**header, 'source_sha256': source_id}
            native = run(work, ['./observe'], text).decode()
            disasm = run(work, ['/usr/bin/objdump', '-dw', 'proof.o']).decode()
            relocs = run(work, ['/usr/bin/readelf', '-rW', 'proof.o']).decode()
            checks[case] = check_calls(text, labels, native, disasm, relocs, len(obligations))
    accepted = [case for case, result in checks.items() if result['covers_reviewed_obligations']]
    if accepted != ['original'] or checks['duplicate_label']['assertion_calls'] != len(obligations):
        raise EvidenceError('proof obligations and source control decisions disagree')
    r2 = {'reviewed_catalog_ids': list(INPUTS), 'cases': objects}
    return {RADARE: {'role': 'reference', 'revision': PROJECTS[RADARE][1], 'operation': 'read_proof_object_sections',
                     'source_manifest_sha256': r2_manifest, 'result': r2},
            CAPSTONE: {'role': 'execution', 'revision': PROJECTS[CAPSTONE][1], 'operation': 'check_proof_obligation_calls',
                       'source_manifest_sha256': cap_manifest, 'source_blobs': len(cap_files),
                       'result': {'radare2_sha256': sha(canonical(r2)), 'cases': checks}}}
