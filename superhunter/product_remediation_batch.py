"""Use remediation examples as offline policy checks when admitting local NQC evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

from .product_portable_roots import ARCHIVE_SHA, ARCHIVE
from .product_review import ROOT, sha
from .product_source_audit import REMOTE, REMOTE_SHA
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json

DIRECTORY = 'superhunter/product_supply/remediation-excerpts'
ORIGINS_SHA = '972a7bdc26fe874d4e3b059ccb34e26cb4bbeb57e80dfcb38f7c6e99de117f45'
NODE_SHA = 'acbe4b8d9153b841ed0697cbfc4f93e767386620edb745ab9358306c0a6f31aa'


def origins(upstream=None):
    raw = read_artifact(ROOT, DIRECTORY + '/origins.json')
    if sha(raw) != ORIGINS_SHA:
        raise ValueError('remediation source manifest changed')
    license_text = read_artifact(ROOT, DIRECTORY + '/GPL-2.txt')
    if sha(license_text) != 'edaef632cbb643e4e7a221717a6c441a4c1a7c918e6e4d56debc3d8739b233f6':
        raise ValueError('GPL-2 license text changed')
    rows = strict_json(raw)['sources']
    for row in rows:
        for item in [row, *row['notices']]:
            data = read_artifact(ROOT, DIRECTORY + '/' + item['local'])
            if sha(data) != item['sha256']:
                raise ValueError('remediation selection or notice changed')
            if upstream is not None:
                name = row['repository'].split('/')[1].lower()
                repo = upstream / f"{row['id']:03}-{name}"
                rev = row['revision']
                if (git(repo, 'rev-parse', rev + '^{tree}').decode().strip() != row['tree']
                        or git(repo, 'rev-parse', rev + ':' + item['path']).decode().strip() != item['blob']):
                    raise ValueError('upstream identity or file changed')
                full = git(repo, 'cat-file', 'blob', item['blob'])
                if 'lines' in item:
                    start, end = item['lines']
                    full = b''.join(full.splitlines(keepends=True)[start-1:end])
                if item.get('presentation') == 'normalized-lines':
                    if sha(full) != item['original_sha256']:
                        raise ValueError('original CRLF text differs')
                    full = b'\n'.join(line.rstrip() for line in full.splitlines()).rstrip() + b'\n'
                if full != data:
                    raise ValueError('published remediation bytes differ from upstream')
    return rows


def canonical_commit_link(url, approved):
    parts = urlsplit(url)
    regex = r'/repos/([^/]+)/([^/]+)/git/commits/([0-9a-f]{40})'
    path = re.fullmatch(regex, parts.path)
    return bool(parts.scheme == 'https' and parts.netloc == 'api.github.com' and path
                and not parts.query and not parts.fragment
                and url == parts.geturl() and path.groups() in approved)


def exact_links(rows, excerpt):
    """Run only the type-annotated exact-match function, under the host's isolated Node."""
    allowed = [r['url'] for r in rows]
    probes = allowed + [v + suffix for v in allowed for suffix in ('/', '?unused=1', '#unused')]
    probes.extend(v.replace('/git/commits/', '/git/trees/') for v in allowed)
    program = ('const [names, values] = JSON.parse(process.argv[1]);\n'
               'const redirectAllowlist = new Set(names);\n' + excerpt.decode() +
               '\nprocess.stdout.write(JSON.stringify(values.map(isRedirectAllowed)));')
    node = os.environ.get('NQC_REMEDIATION_NODE') or shutil.which('node')
    if not node:
        raise ValueError('pinned Node 24.22.3 binary is required for the referral check')
    with open(node, 'rb') as binary:
        if hashlib.file_digest(binary, 'sha256').hexdigest() != NODE_SHA:
            raise ValueError('unexpected Node build for remediation review')
        # The same open inode supplies bytes for both the digest and exec.
        binary.seek(0)
        proc = subprocess.run(['/usr/bin/unshare', '--user', '--map-current-user', '--net',
                               '/proc/self/fd/' + str(binary.fileno()), '--permission',
                               '--disable-warning=ExperimentalWarning', '--max-old-space-size=48',
                               '--input-type=module-typescript', '-e', program, json.dumps([allowed, probes])],
                              pass_fds=(binary.fileno(),), env={'PATH': '/usr/bin:/bin'}, timeout=12,
                              capture_output=True, check=True)
    results = json.loads(proc.stdout)
    permitted = {(*r['repository'].split('/'), r['commit']) for r in rows}
    expectations = [canonical_commit_link(url, permitted) for url in probes]
    if (len(permitted) != 47 or results != expectations or any(type(v) is not bool for v in results)
            or sum(results) != len(allowed) or not all(results[:len(allowed)])):
        raise ValueError('exact links and independent URL parsing differ')
    return {'accepted_commit_links': sum(results), 'rejected_alternatives': len(probes)-sum(results),
            'inputs_sha256': sha(canonical(probes)), 'decisions_sha256': sha(canonical(results)), 'node_sha256': NODE_SHA}


def filename_reference(raw):
    text = raw.decode().replace('\r\n', '\n')
    match = re.search(r'\$configFileNames = \[\n((?:    \'[a-z0-9.]+\',\n)+)\];', text)
    if (not match or 'if( !in_array($file, $configFileNames) ) {' not in text or '    exit;' not in text):
        raise ValueError('unknown filename allowlist reference')
    names = re.findall(r"'([a-z0-9.]+)'", match[1])
    if len(names) != len(set(names)) or not names:
        raise ValueError('ambiguous filename corpus')
    return names


def admitted(root, candidate, approved, require_containment):
    if type(candidate) is not str or candidate not in approved:
        return False
    try:
        resolved = (root / candidate).resolve(strict=True)
        if require_containment and not resolved.is_relative_to(root.resolve(strict=True)):
            return False
        raw = read_artifact(root, candidate)
    except (OSError, RuntimeError, ValueError):
        return False
    return sha(raw) == approved[candidate]


def check_containment(raw):
    # Apply the original document's normative containment condition. No sample server is started.
    if (b'The canonical path function' not in raw
            or b'path is inside the expected directory.' not in raw):
        raise ValueError('unrecognised path containment reference')
    return True


def evidence_reader(contents, names, require_containment):
    with tempfile.TemporaryDirectory(prefix='nqc-remediation-evidence-') as temp:
        root = Path(temp)/'evidence'
        sibling = Path(temp)/'evidence-old'
        root.mkdir()
        sibling.mkdir()
        approved = {name: sha(raw) for name, raw in contents.items()}
        for name, raw in contents.items():
            (root/name).write_bytes(raw)
        payload = next(iter(contents.values()))
        (sibling/'other.json').write_bytes(payload)
        (root/'unregistered.json').write_bytes(payload)
        (root/'external-link.json').symlink_to(sibling/'other.json')
        (root/'short-link.json').symlink_to(root/next(iter(contents)))
        paths = ['external-link.json', '../evidence-old/other.json', 'short-link.json']
        for path in paths:
            # Include these names and matching digests on purpose: filesystem confinement stands alone.
            approved[path] = sha(payload)
        original = list(contents)
        candidates = [*original, 'unregistered.json', *paths]
        accepted = [admitted(root, name, approved, require_containment) for name in candidates]
        canonical_inside = {name: (root/name).resolve(strict=True).is_relative_to(root)
                            for name in candidates}
        if (accepted != [True]*len(contents) + [False]*4 or canonical_inside[paths[0]]
                or canonical_inside[paths[1]] or not canonical_inside[paths[2]]):
            raise ValueError('evidence path guard differs from controlled filesystem witnesses')
        # Check the canonical containment oracle via path components, and evaluate the
        # common string-prefix substitute against the two real out-of-root locations.
        independently_inside = {name: root in (root/name).resolve().parents for name in candidates}
        lexical_mismatches = [name for name in candidates if
                              str((root/name).resolve()).startswith(str(root)) != canonical_inside[name]]
        if canonical_inside != independently_inside or lexical_mismatches != paths[:2]:
            raise ValueError('containment policy failed to distinguish the sibling directory')
        (root/original[0]).write_bytes(payload + b'\n')
        tampered = admitted(root, original[0], approved, require_containment)
        if tampered:
            raise ValueError('changed evidence content accepted')

        # The original educational repair provides an independent name corpus for this gate.
        corpus = {name: sha(name.encode()) for name in names}
        additions = ('unknown.php', names[0].upper(), names[0] + '.backup')
        for name in [*names, *additions]:
            (root/name).write_bytes(name.encode())
        observed = [admitted(root, name, corpus, require_containment) for name in [*names, *additions]]
        if observed != [True]*len(names) + [False]*len(additions):
            raise ValueError('filename admission differs from independent reference cases')
        return {'accepted_product_files': original, 'rejected_unregistered': True,
                'canonical_inside': canonical_inside, 'refuted_string_prefix_on': lexical_mismatches,
                'refused_named_links_or_outside': paths,
                'tampered_content_rejected': not tampered, 'reference_names': names,
                'reference_controls_rejected': list(additions)}


def review(source_root: Path):
    rows = origins()
    refs = {row['id']: read_artifact(ROOT, DIRECTORY + '/' + row['local']) for row in rows}
    tree_index = read_artifact(ROOT, REMOTE)
    archive = read_artifact(ROOT, ARCHIVE)
    if sha(tree_index) != REMOTE_SHA or sha(archive) != ARCHIVE_SHA:
        raise ValueError('reviewed NQC evidence bytes changed')
    links = exact_links(strict_json(tree_index)['commits'], refs[194])
    contents = {Path(REMOTE).name: tree_index, Path(ARCHIVE).name: archive}
    file_report = evidence_reader(contents, filename_reference(refs[197]), check_containment(refs[195]))
    inventory = {name: sha(raw) for name, raw in contents.items()}
    combined = sha(canonical({'links': links, 'files': file_report, 'inventory': inventory}))
    results = {
        194: ('execution', 'Check 47 exact offline evidence URLs with the original TypeScript repair and a separate URL parser.', links),
        195: ('reference', 'Validate canonical containment, then use the NQC file-descriptor reader and exact evidence digests.',
              {key: file_report[key] for key in ('accepted_product_files', 'canonical_inside', 'refuted_string_prefix_on', 'refused_named_links_or_outside', 'tampered_content_rejected')}),
        197: ('reference', 'Apply the repaired filename allowlist to the NQC evidence reader and test it against the original accepted-name corpus.',
              {key: file_report[key] for key in ('accepted_product_files', 'rejected_unregistered', 'reference_names', 'reference_controls_rejected')})}
    evidence = {}
    for row in rows:
        role, operation, output = results[row['id']]
        evidence[row['repository']] = {'revision': row['revision'], 'role': role, 'operation': operation, 'output': output,
                                       'input_sha256': inventory, 'combined_report_sha256': combined,
                                       'source_blob': row['blob'], 'excerpt_sha256': row['sha256']}
    return evidence
