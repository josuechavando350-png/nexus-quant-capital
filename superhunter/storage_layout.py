"""Conservative storage-layout review of supplied Solidity compiler artifacts.

No compiler, bytecode, RPC, deployment or exploit is executed. Type fingerprints
are independent of compiler-local type/AST IDs. Unsupported shapes and renames
remain review-required. A favorable result only describes this declared profile.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
MAX_TYPES = 512
MAX_ENTRIES = 2048
MAX_DEPTH = 32
SPACE = (1 << 256) * 32
FILES = {'manifest.json', 'before.json', 'after.json', 'result.json', 'audit.json', 'REVIEW.md'}
CODE_FILES = ('storage_layout.py', 'safe_io.py', 'native_runtime.py', 'privacy.py')
HEX = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
VERSION = re.compile(r'0\.8\.[0-9]+(?:\+[A-Za-z0-9.-]+)?\Z')


class LayoutError(ValueError):
    """Fixed diagnostic codes, never user-supplied text."""


class UnsupportedLayout(LayoutError):
    """A valid-looking shape beyond this explicitly bounded profile."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise LayoutError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def text(value: Any, code: str) -> str:
    need(type(value) is str and 0 < len(value) <= 512 and
         all(ord(c) >= 32 and ord(c) != 127 for c in value), code)
    return value


def exact(obj: Any, keys: set[str], code: str) -> None:
    need(type(obj) is dict and set(obj) == keys, code)


def decimal(value: Any, maximum: int) -> int:
    need(type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,79}', value) is not None,
         'NONCANONICAL_DECIMAL')
    number = int(value)
    need(number <= maximum, 'INTEGER_OUT_OF_RANGE')
    return number


def validate_manifest(m: Any) -> dict:
    exact(m, {'schema_version', 'repo', 'contract', 'before', 'after'}, 'MANIFEST_SCHEMA')
    need(type(m['schema_version']) is int and m['schema_version'] == 1, 'MANIFEST_VERSION')
    need(REPO.fullmatch(text(m['repo'], 'REPO')) is not None and
         all(p not in ('.', '..') for p in m['repo'].split('/')), 'REPO')
    text(m['contract'], 'CONTRACT')
    for side in ('before', 'after'):
        exact(m[side], {'commit', 'sha256'}, 'VERSION_BINDING_SCHEMA')
        need(COMMIT.fullmatch(text(m[side]['commit'], 'COMMIT')) is not None, 'COMMIT')
        need(HEX.fullmatch(text(m[side]['sha256'], 'ARTIFACT_HASH')) is not None, 'ARTIFACT_HASH')
    return m


def validate_artifact(data: Any, manifest: dict, side: str) -> dict:
    exact(data, {'schema_version', 'target', 'compiler_version', 'storage_layout'}, 'ARTIFACT_SCHEMA')
    need(type(data['schema_version']) is int and data['schema_version'] == 1, 'ARTIFACT_VERSION')
    exact(data['target'], {'repo', 'commit', 'contract'}, 'TARGET_SCHEMA')
    need(data['target'] == {'repo': manifest['repo'], 'commit': manifest[side]['commit'],
                            'contract': manifest['contract']}, 'TARGET_BINDING_MISMATCH')
    text(data['compiler_version'], 'COMPILER_VERSION')
    need(VERSION.fullmatch(data['compiler_version']) is not None, 'COMPILER_VERSION_PROFILE')
    return data['storage_layout']


class _Layout:
    """Validate declared allocation and fingerprint reachable type graphs.

    Interval checks include complete aggregate footprints. Dynamic arrays and
    mappings occupy their head slot only; their children still enter type hashes.
    Recursive types, custom value types, enums and function pointers are explicitly
    unsupported, not silently assumed equivalent.
    """
    def __init__(self, raw: Any) -> None:
        exact(raw, {'storage', 'types'}, 'LAYOUT_SCHEMA')
        self.types = raw['types']
        if self.types is None and raw['storage'] == []:
            self.types = {}
        need(type(self.types) is dict and len(self.types) <= MAX_TYPES, 'TYPE_BUDGET')
        self.cache: dict[str, dict] = {}
        self.active: set[str] = set()
        self.entries_seen = 0
        for name, desc in self.types.items():
            text(name, 'TYPE_ID')
            need(type(desc) is dict and {'encoding', 'label', 'numberOfBytes'} <= set(desc) and
                 set(desc) <= {'encoding', 'label', 'numberOfBytes', 'base', 'key', 'value', 'members'},
                 'TYPE_SCHEMA')
            text(desc['label'], 'TYPE_LABEL')
            need(desc['encoding'] in ('inplace', 'mapping', 'dynamic_array', 'bytes'), 'TYPE_ENCODING')
            need(decimal(desc['numberOfBytes'], SPACE) > 0, 'ZERO_TYPE_SIZE')
            for field in ('base', 'key', 'value'):
                if field in desc:
                    need(type(desc[field]) is str and desc[field] in self.types, 'MISSING_TYPE')
        self.entries = self._entries(raw['storage'], top=True, depth=0)
        self.end = max((e['end_byte'] for e in self.entries), default=0)

    def _entries(self, raw: Any, *, top: bool, depth: int) -> list[dict]:
        need(type(raw) is list, 'ENTRY_LIST')
        self.entries_seen += len(raw)
        need(self.entries_seen <= MAX_ENTRIES, 'ENTRY_BUDGET')
        entries = []
        seen = set()
        for row in raw:
            exact(row, {'astId', 'contract', 'label', 'offset', 'slot', 'type'}, 'ENTRY_SCHEMA')
            need(type(row['astId']) is int and row['astId'] >= 0, 'AST_ID')
            text(row['contract'], 'ENTRY_CONTRACT')
            text(row['label'], 'ENTRY_LABEL')
            # Duplicate labels (e.g. inherited private declarations) need explicit
            # correspondence; do not guess by source ordering or AST IDs.
            if row['label'] in seen:
                raise UnsupportedLayout('AMBIGUOUS_DECLARATION_LABEL')
            seen.add(row['label'])
            need(type(row['offset']) is int and 0 <= row['offset'] < 32, 'OFFSET')
            slot = decimal(row['slot'], (1 << 256) - 1)
            typ = self._type(row['type'], depth + 1)
            offset = row['offset']
            need((typ['packable'] and offset + typ['size'] <= 32) or
                 (not typ['packable'] and offset == 0), 'TYPE_ALIGNMENT')
            start = 32 * slot + offset
            end = start + typ['size']
            need(end <= SPACE, 'STORAGE_ADDRESS_WRAP')
            entries.append({'label': row['label'], 'slot': row['slot'], 'offset': offset,
                            'start_byte': start, 'end_byte': end, 'type_sha256': typ['fingerprint'],
                            'gap': row['label'] == '__gap' or row['label'].startswith('__gap_')})
        ordered = sorted(entries, key=lambda e: (e['start_byte'], e['end_byte']))
        for a, b in zip(ordered, ordered[1:]):
            need(a['end_byte'] <= b['start_byte'], 'OVERLAPPING_ALLOCATION')
        return entries

    def _type(self, identifier: Any, depth: int) -> dict:
        need(type(identifier) is str and identifier in self.types, 'MISSING_TYPE')
        if identifier in self.cache:
            return self.cache[identifier]
        if identifier in self.active:
            raise UnsupportedLayout('RECURSIVE_TYPE_REVIEW')
        if depth > MAX_DEPTH:
            raise UnsupportedLayout('TYPE_DEPTH_REVIEW')
        self.active.add(identifier)
        try:
            d = self.types[identifier]
            encoding, label = d['encoding'], d['label']
            size = decimal(d['numberOfBytes'], SPACE)
            extras = set(d) - {'encoding', 'label', 'numberOfBytes'}
            shape: dict = {'encoding': encoding, 'bytes': str(size)}
            packable = False
            if encoding == 'mapping':
                need(extras == {'key', 'value'} and size == 32, 'MAPPING_SCHEMA')
                key = self._type(d['key'], depth + 1)
                need(key['key_allowed'], 'MAPPING_KEY_TYPE')
                shape.update(key=key['fingerprint'], value=self._type(d['value'], depth + 1)['fingerprint'])
            elif encoding == 'dynamic_array':
                need(extras == {'base'} and size == 32, 'DYNAMIC_ARRAY_SCHEMA')
                shape['element'] = self._type(d['base'], depth + 1)['fingerprint']
            elif encoding == 'bytes':
                need(not extras and label in ('bytes', 'string') and size == 32, 'BYTES_SCHEMA')
                # Same physical encoding does not prove semantic interchangeability.
                shape['label'] = label
            elif 'members' in extras:
                need(extras == {'members'} and size % 32 == 0, 'STRUCT_SCHEMA')
                members = self._entries(d['members'], top=False, depth=depth + 1)
                need(bool(members), 'EMPTY_STRUCT')
                end = max(e['end_byte'] for e in members)
                need(((end + 31) // 32) * 32 == size, 'STRUCT_SIZE_MISMATCH')
                shape['members'] = [{'label': e['label'], 'slot': e['slot'], 'offset': e['offset'],
                                     'type': e['type_sha256']} for e in
                                    sorted(members, key=lambda e: (e['start_byte'], e['label']))]
            elif 'base' in extras:
                need(extras == {'base'}, 'ARRAY_SCHEMA')
                match = re.search(r'\[([1-9][0-9]*)\]\Z', label)
                need(match is not None and len(match[1]) <= 78, 'FIXED_ARRAY_LENGTH')
                length = int(match[1])
                child = self._type(d['base'], depth + 1)
                if child['packable']:
                    per_slot = 32 // child['size']
                    expected = ((length + per_slot - 1) // per_slot) * 32
                else:
                    expected = length * child['size']
                need(expected == size and expected <= SPACE, 'ARRAY_SIZE_MISMATCH')
                shape.update(length=str(length), element=child['fingerprint'])
            else:
                need(not extras, 'PRIMITIVE_SCHEMA')
                if label in ('bool', 'address', 'address payable'):
                    expected = 1 if label == 'bool' else 20
                elif (match := re.fullmatch(r'(?:uint|int)([0-9]+)', label)) is not None:
                    bits = int(match[1]);need(8 <= bits <= 256 and bits % 8 == 0, 'INTEGER_WIDTH')
                    expected = bits // 8
                elif (match := re.fullmatch(r'bytes([0-9]+)', label)) is not None:
                    expected = int(match[1]);need(1 <= expected <= 32, 'FIXED_BYTES_WIDTH')
                else:
                    raise UnsupportedLayout('UNSUPPORTED_VALUE_TYPE')
                need(size == expected, 'PRIMITIVE_SIZE_MISMATCH')
                packable = True;shape['label'] = label
            value = {'size': size, 'packable': packable, 'fingerprint': sha(canonical(shape)),
                     'key_allowed': packable or encoding == 'bytes'}
            self.cache[identifier] = value
            return value
        finally:
            self.active.remove(identifier)


def compare(manifest: Any, before: bytes, after: bytes) -> dict:
    m = validate_manifest(manifest)
    raws = {'before': before, 'after': after}
    layouts = {}; unsupported = []; compiler_versions = {}
    for side, raw in raws.items():
        need(type(raw) is bytes and len(raw) <= 2_000_000, 'ARTIFACT_SIZE')
        need(sha(raw) == m[side]['sha256'], 'ARTIFACT_HASH_MISMATCH')
        artifact = strict_json(raw)
        data = validate_artifact(artifact, m, side)
        compiler_versions[side] = artifact['compiler_version']
        try:
            layouts[side] = _Layout(data)
        except UnsupportedLayout as exc:
            unsupported.append({'side': side, 'reason': str(exc)})
    changes = []; notes = []; preserved = 0; additions = 0
    if not unsupported:
        old, new = layouts['before'], layouts['after']
        old_by = {e['label']: e for e in old.entries}
        new_by = {e['label']: e for e in new.entries}
        for label, entry in old_by.items():
            ref = sha(label.encode())
            replacement = new_by.get(label)
            if replacement is None:
                notes.append({'code': 'REMOVED_OR_RENAMED', 'declaration_sha256': ref})
                continue
            moved = (entry['slot'], entry['offset']) != (replacement['slot'], replacement['offset'])
            changed = entry['type_sha256'] != replacement['type_sha256']
            if entry['gap'] or replacement['gap']:
                if moved or changed:
                    notes.append({'code': 'GAP_REQUIRES_SPECIALIZED_REVIEW', 'declaration_sha256': ref})
            else:
                if moved:
                    changes.append({'code': 'DECLARATION_MOVED', 'declaration_sha256': ref,
                                    'before': {'slot': entry['slot'], 'offset': entry['offset']},
                                    'after': {'slot': replacement['slot'], 'offset': replacement['offset']}})
                if changed:
                    changes.append({'code': 'TYPE_SHAPE_CHANGED', 'declaration_sha256': ref,
                                    'before_type_sha256': entry['type_sha256'],
                                    'after_type_sha256': replacement['type_sha256']})
            preserved += not moved and not changed
        for label in sorted(new_by.keys() - old_by.keys()):
            entry = new_by[label];additions += 1
            if entry['start_byte'] < old.end:
                notes.append({'code': 'INSERTION_WITHIN_PREVIOUS_FOOTPRINT', 'declaration_sha256': sha(label.encode())})
        if not old.entries:
            notes.append({'code': 'NO_PREVIOUS_STORED_STATE_DECLARED'})
        if compiler_versions['before'] != compiler_versions['after']:
            notes.append({'code': 'COMPILER_VERSION_CHANGED_REVIEW'})
    status = ('LAYOUT_CHANGE_DETECTED' if changes else
              'LAYOUT_REVIEW_REQUIRED' if unsupported or notes else 'LAYOUT_PRESERVED_IN_PROFILE')
    return {'schema_version': 1, 'profile': 'solc-storage-structure-v1', 'status': status,
            'manifest_sha256': sha(canonical(m)),
            'artifact_sha256': {k: sha(v) for k,v in raws.items()},
            'compiler_versions_claimed': compiler_versions, 'changes': changes,
            'review_notes': notes, 'unsupported': unsupported,
            'existing_declarations_preserved': preserved, 'added_declarations': additions,
            'root_declarations': {k: len(v.entries) for k,v in layouts.items()},
            'compiler_executed': False, 'source_or_bytecode_authenticated': False,
            'deployed_storage_verified': False, 'upgrade_authorized': False,
            'vulnerability_confirmed': False, 'manual_review_required': True,
            'unsupported_features': ['unstructured/ERC7201 storage', 'transient storage',
                'inline assembly storage access', 'custom value types/enums/functions',
                'recursive type graphs', 'automatic gap consumption', 'initializer/code behavior']}


def _engine() -> dict:
    return {'sources': {p: sha(read_artifact(ROOT,p)) for p in CODE_FILES},
            'native_sources': source_inventory()}


def _audit(result: dict, engine: dict) -> dict:
    native = load_components()
    # Deterministic event times are not physical event-time claims.
    log = native.audit.AuditLog(clock=lambda: '1970-01-01T00:00:00+00:00')
    log.append('layout.review.inputs', {'manifest_sha256': result['manifest_sha256'],
                                      'artifact_sha256': result['artifact_sha256']})
    for i, change in enumerate(result['changes']):
        log.append('layout.review.change', {'index': i, 'record_sha256': sha(canonical(change))})
    log.append('layout.review.result', {'result_sha256': sha(canonical(result))})
    log.assert_intact()
    return {'entries': [asdict(e) for e in log.entries], 'engine': engine,
            'event_time_semantics': 'fixed-reference-not-wall-clock'}


def render(result: dict) -> bytes:
    # Private artifact messages, names and paths are deliberately not printed.
    counts = Counter(c['code'] for c in result['changes'])
    text_lines = ['# Revisión de compatibilidad de almacenamiento', '',
                  'Estado: ' + result['status'],
                  'Cambios estructurales: ' + str(len(result['changes'])),
                  'Pendientes de revisión: ' + str(len(result['review_notes']) + len(result['unsupported'])), '']
    text_lines += [f'{code}: {count}' for code,count in sorted(counts.items())]
    text_lines += ['', 'Se compararon artefactos suministrados. No se ejecutó solc ni una actualización.',
                   'Un resultado favorable solo cubre este perfil y estas declaraciones.',
                   'No autentica fuentes, código desplegado ni seguridad de una actualización.',
                   'El paquete completo es privado; contiene los artefactos originales.', '']
    return '\n'.join(text_lines).encode()


def create(manifest_path: Path, before_path: Path, after_path: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_IN_CHECKOUT')
    raw = read_artifact(manifest_path.parent, manifest_path.name)
    before = read_artifact(before_path.parent, before_path.name)
    after = read_artifact(after_path.parent, after_path.name)
    engine = _engine()
    result = compare(strict_json(raw), before, after)
    need(_engine() == engine, 'ENGINE_CHANGED')
    write_new_bundle(out, {'manifest.json': raw, 'before.json': before, 'after.json': after,
                          'result.json': canonical(result), 'audit.json': canonical(_audit(result,engine)),
                          'REVIEW.md': render(result)})
    return verify(out, manifest_path)


def verify(root: Path, expected_manifest: Path) -> dict:
    need(not root.is_symlink(), 'ROOT_SYMLINK')
    need(not expected_manifest.resolve().is_relative_to(root.resolve()), 'EXTERNAL_MANIFEST_REQUIRED')
    expected_raw = read_artifact(expected_manifest.parent, expected_manifest.name)
    expected = validate_manifest(strict_json(expected_raw))
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    exact(marker, {'schema_version','sha256'}, 'BUNDLE_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version']==1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES, 'BUNDLE_SCHEMA')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILE_SET')
    data = {name: read_artifact(root,name) for name in FILES}
    need(all(sha(v)==marker['sha256'][k] for k,v in data.items()), 'BUNDLE_HASH')
    need(canonical(strict_json(data['manifest.json'])) == canonical(expected), 'EXTERNAL_REFERENCE_MISMATCH')
    engine = _engine()
    result = compare(expected, data['before.json'], data['after.json'])
    need(data['result.json'] == canonical(result) and data['audit.json'] == canonical(_audit(result,engine)) and
         data['REVIEW.md'] == render(result), 'RECOMPUTATION_MISMATCH')
    need(_engine() == engine and read_artifact(expected_manifest.parent, expected_manifest.name) == expected_raw,
         'SOURCE_CHANGED_DURING_VERIFICATION')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Compare supplied Solidity storage layouts; no code execution')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('review-layout')
    for name in ('manifest', 'before', 'after', 'out'):
        make.add_argument('--'+name, type=Path, required=True)
    check = sub.add_parser('verify-layout')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected', type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        r = create(a.manifest,a.before,a.after,a.out) if a.command=='review-layout' else verify(a.bundle,a.expected)
        print(json.dumps({k:r[k] for k in ('status','compiler_executed','vulnerability_confirmed')}))
        return 0 if r['status']=='LAYOUT_PRESERVED_IN_PROFILE' else 1
    except (ValueError, OSError, KeyError, TypeError, RecursionError, UnicodeError, OverflowError) as exc:
        print(json.dumps({'status':'LAYOUT_REVIEW_ERROR','error_type':type(exc).__name__,
                          'vulnerability_confirmed':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
