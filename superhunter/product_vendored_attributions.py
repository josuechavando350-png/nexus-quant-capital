"""Reconcile a fixed source distribution's published notices with its vendored directories."""
from collections import Counter
import re

from .product_reasoning import EvidenceError
from .product_review import sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical

SUBJECT = 'sqlmapproject/sqlmap'
REVISION = '5db2e62884d91f3ed3b43ec55904737e4051e9d7'
DOCUMENT = 'doc/THIRD-PARTY.md'
DOCUMENT_BLOB = '971e794be6a7aaeb6a1782aaeeb453cb4474988f'
FAMILIES = {'BSD', 'LGPL', 'PSF', 'MIT', 'Public domain'}
NOTICE_NAME = re.compile(r'(?:licen[sc]e|copying|copyright|notice)(?:\.txt|\.md)?', re.I)
ENTRY = re.compile(r'\* The `([A-Za-z0-9_ -]+)` [^\n`]+? located under `((?:thirdparty|extra)/[A-Za-z0-9_-]+)/`\.')


def declarations(raw):
    groups = {}
    names = set()
    heading = None
    expected_headers = set()
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('#'):
            if not line.startswith('# ') or line[2:] not in FAMILIES or line[2:] in expected_headers:
                raise EvidenceError('unsupported or duplicate declaration heading')
            heading = line[2:]
            expected_headers.add(heading)
        elif line.startswith('*'):
            match = ENTRY.fullmatch(line)
            if not match or not heading:
                raise EvidenceError('unrecognized attribution entry')
            name, path = match.groups()
            if name.casefold() in names or path in groups:
                raise EvidenceError('duplicate declared package or directory')
            names.add(name.casefold())
            groups[path] = {'name': name, 'declared_group': heading}
    if not groups or {v['declared_group'] for v in groups.values()} != expected_headers:
        raise EvidenceError('empty declaration or license group')
    return groups


def tree_entries(repo, tree):
    entries = {}
    for chunk in git(repo, 'ls-tree', '-z', tree).split(b'\0'):
        if chunk:
            attrs, name = chunk.decode().split('\t', 1)
            mode, kind, oid = attrs.split()
            entries[name] = (mode, kind, oid)
    return entries


def notice_blob(repo, entry):
    mode, kind, oid = entry
    if mode != '100644' or kind != 'blob':
        raise EvidenceError('refusing to read a nonregular notice')
    size = int(git(repo, 'cat-file', '-s', oid))
    if not 0 < size <= 262144:
        raise EvidenceError('unexpected notice size')
    raw = git(repo, 'cat-file', 'blob', oid)
    if len(raw) != size or git_object('blob', raw) != oid:
        raise EvidenceError('notice bytes differ from their Git object')
    return raw


def text_group(raw):
    lower = b' '.join(raw.lower().split())
    indicators = {
        'MIT': (b'permission is hereby granted, free of charge', b'the software is provided "as is"'),
        'BSD': (b'redistribution and use in source and binary forms', b'this software is provided'),
    }
    families = [group for group, phrases in indicators.items() if all(p in lower for p in phrases)]
    return families[0] if len(families) == 1 else 'undetermined'


def review_packages(declared, directory_entries, notices_by_root):
    """Return distinct reasons for a missing tree, unmatched notice or undeclared vendored root."""
    unmatched = sorted(path for path, entry in directory_entries.items()
                       if path.startswith('thirdparty/') and entry[:2] == ('040000', 'tree') and path not in declared)
    evidence = {}
    for path, statement in sorted(declared.items()):
        entry = directory_entries.get(path)
        notices = notices_by_root.get(path, [])
        if not entry or entry[:2] != ('040000', 'tree'):
            disposition = 'declared_directory_missing_or_wrong_mode'
        elif not notices:
            disposition = 'global_declaration_only_no_named_root_notice'
        elif all(n['text_group'] == statement['declared_group'] for n in notices):
            disposition = 'named_notice_text_consistent_with_group'
        else:
            disposition = 'independent_notice_review_required'
        evidence[path] = {**statement, 'tree': entry[2] if entry and entry[:2] == ('040000', 'tree') else None,
                          'root_notices': notices, 'disposition': disposition}
    return {'declared_packages': len(evidence),
            'declared_group_counts': dict(sorted(Counter(s['declared_group'] for s in declared.values()).items())),
            'disposition_counts': dict(sorted(Counter(v['disposition'] for v in evidence.values()).items())),
            'bundled_roots_without_declaration': unmatched, 'package_evidence': evidence}


def review(root):
    repo = root/'003-sqlmap'
    if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD').decode().strip() != REVISION:
        raise EvidenceError('unexpected notice provider revision')
    entry = tree_entries(repo, REVISION + ':doc').get('THIRD-PARTY.md')
    if entry != ('100644', 'blob', DOCUMENT_BLOB):
        raise EvidenceError('third-party declaration not found at its pinned path')
    raw = notice_blob(repo, entry)
    declared = declarations(raw)
    entries = {}
    for parent in sorted({'thirdparty', *(path.split('/')[0] for path in declared)}):
        # Only first-level vendoring directories can be audited for missing declarations.
        children = tree_entries(repo, REVISION + ':' + parent)
        for name, child in children.items():
            path = parent + '/' + name
            if parent == 'thirdparty' or path in declared:
                entries[path] = child
    notices = {}
    for path in declared:
        child = entries.get(path)
        if not child or child[:2] != ('040000', 'tree'):
            continue
        for name, item in sorted(tree_entries(repo, child[2]).items()):
            if NOTICE_NAME.fullmatch(name):
                data = notice_blob(repo, item)
                notices.setdefault(path, []).append({'file': name, 'git_blob': item[2],
                                                     'sha256': sha(data), 'text_group': text_group(data)})
    result = review_packages(declared, entries, notices)
    return {SUBJECT: {'revision': REVISION, 'role': 'reference',
                      'operation': 'reconcile_published_vendor_notice_groups_with_committed_package_directories',
                      'notice_path': DOCUMENT, 'notice_git_blob': DOCUMENT_BLOB, 'notice_sha256': sha(raw),
                      'result': result,
                      'scope': 'The central notice declares package groups. Named root notices corroborate broad text '
                               'families only. Unlisted direct thirdparty directories require review. '
                               'No SPDX precision, complete copyright review or commercial approval is inferred.'}}
