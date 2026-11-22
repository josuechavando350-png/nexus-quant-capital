"""Bounded native route and parameter discovery on an owned loopback API."""
from pathlib import Path
import subprocess
import sys
import tempfile

from .product_notice_ranking import install_wheels
from .product_notices import read_wheel
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_upstream_notices import sources
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'ffuf/ffuf': 'executable', 'OJ/gobuster': 'executable', 's0md3v/Arjun': 'executable'}
LOCK = 'superhunter/product_supply/discovery-native-linux-py312.txt'
LOCK_SHA = '704965de7f1ea30f6ea2aca76f492cd6867f10fb0ef4a5b79cd018f43a14ec0c'
PROOFS = 'superhunter/product_supply/discovery-native-sources.json'
PROOFS_SHA = '24d86e871d1551bb940cc52958effcb863694906b257960ce31f8a35acedac3a'
ISOLATE = ['/usr/bin/unshare', '--user', '--map-root-user', '--net']


def inputs():
    catalog = [{'id': row['id'], 'repository': row['repository'], 'revision': row['revision']}
               for row in sources() if row['id'] in (5, 51, 54)]
    catalog_body = canonical(catalog)
    rows = {'/live/catalog': (200, catalog_body), '/live/health': (200, b'{"status":"OWNED"}\n'),
            '/live/restricted': (403, b'{"error":"OWNED_DENIAL"}\n'), '/wild/catalog': (200, catalog_body)}
    return {'routes': {path: {'status': status, 'body': body.hex()} for path, (status, body) in rows.items()},
            'wildcard_body': b'{"message":"OWNED wildcard"}\n'.hex(),
            'parameter_body': b'{"positions":["OWNED_OPEN"]}\n'.hex(),
            'expanded_body': b'{"positions":["OWNED_OPEN","OWNED_CLOSED"]}\n'.hex(),
            'route_words': ['catalog', 'health', 'restricted', 'missing'],
            'parameter_words': ['include_closed', 'ignored_limit', 'unused_filter', 'plain_echo']}


def source_proofs():
    raw = read_artifact(ROOT, PROOFS)
    if sha(raw) != PROOFS_SHA:
        raise EvidenceError('discovery native producer pins differ')
    return strict_json(raw)


def verify_arjun(work, proof):
    expected = proof['package_git_blobs']
    actual = {p.relative_to(work/'lib').as_posix() for p in (work/'lib'/'arjun').rglob('*') if p.is_file()}
    if actual != set(expected):
        raise EvidenceError('Arjun source/data membership differs')
    for name, digest in expected.items():
        if git_object('blob', read_artifact(work/'lib', name)) != digest:
            raise EvidenceError('Arjun producer differs from the catalog source')
    return len(actual)


def validate(native, payload):
    wanted_names = {tool + '_' + profile for tool in ('ffuf', 'gobuster') for profile in ('live', 'clean', 'wild')}
    wanted_names |= {'arjun_live', 'arjun_clean'}
    if (set(native) != {'cases', 'versions', 'namespace'} or set(native['cases']) != wanted_names
            or native['namespace'] != {'interfaces': ['lo'], 'ipv4_route_count': 0}
            or native['versions'] != {'ffuf': 'ffuf version: 0.0.0-dev', 'gobuster': 'gobuster version 3.8.2', 'arjun': '2.2.7'}):
        raise EvidenceError('native discovery identity, namespace or case coverage differs')
    for name, row in native['cases'].items():
        parameter_case = name.startswith('arjun_')
        wildcard_refusal = name == 'gobuster_wild'
        audit = {'within_request_budget': True, 'only_owned_loopback': True, 'only_expected_path': True,
                 'methods': ['GET'], 'route_candidates_requested': [] if parameter_case or wildcard_refusal
                 else sorted(payload['route_words']), 'parameter_candidates_requested':
                 sorted(payload['parameter_words']) if parameter_case else []}
        if canonical(row['audit']) != canonical(audit):
            raise EvidenceError('native discovery traffic did not cover the bounded owned controls: ' + name)
        if parameter_case:
            live = name == 'arjun_live'
            expected = {'parameters': ['include_closed'] if live else [],
                        'verdict': 'parameters_found' if live else 'none_found', 'audit': audit}
        elif wildcard_refusal:
            expected = {'refused_wildcard': True, 'baseline_status': 200,
                        'baseline_bytes': len(bytes.fromhex(payload['wildcard_body'])), 'audit': audit}
        else:
            profile = name.split('_', 1)[1]
            matches = [{'path': path, 'status': entry['status'], 'bytes': len(bytes.fromhex(entry['body']))}
                       for path, entry in payload['routes'].items() if path.startswith('/' + profile + '/')]
            expected = {'matches': sorted(matches, key=lambda r: r['path']), 'audit': audit}
        if canonical(row) != canonical(expected):
            raise EvidenceError('native discovery findings disagree with the owned endpoint oracle: ' + name)
    return native


def run(kit: Path):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('locked discovery dependencies require CPython 3.12')
    kit = Path(kit)
    proofs, payload = source_proofs(), inputs()
    worker = Path(__file__).with_name('product_discovery_native_worker.py')
    with tempfile.TemporaryDirectory(prefix='nqc-discovery-native-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin', 'PYTHONIOENCODING': 'utf-8',
               'NO_PROXY': '*', 'GOMAXPROCS': '1'}
        for name, slug in [('ffuf', '005-ffuf'), ('gobuster', '054-gobuster')]:
            raw = read_wheel(kit/name)
            if sha(raw) != proofs[slug]['binary_sha256']:
                raise EvidenceError('native discovery binary digest differs')
            (work/name).write_bytes(raw)
            (work/name).chmod(0o700)
        install_wheels(kit, work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='Discovery native')
        arjun_files = verify_arjun(work, proofs['051-arjun'])
        proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S', str(worker)], cwd=work, env=env,
                              input=canonical(payload), capture_output=True, timeout=180)
        if proc.returncode:
            raise EvidenceError('native discovery worker failed: ' + proc.stderr.decode(errors='replace')[-1400:])
        result = validate(strict_json(read_artifact(work, 'discovery-native.json')), payload)
    return {'schema_version': 1, 'scope': 'fixed_owned_loopback_route_and_parameter_discovery',
            'input_sha256': sha(canonical(payload)), 'dependency_lock_sha256': LOCK_SHA,
            'source_proofs_sha256': PROOFS_SHA, 'source_revisions': {k: v['revision'] for k, v in proofs.items() if k != 'build'},
            'arjun_source_data_files_verified': arjun_files, 'observations': result,
            'summary': {'native_clients': 3, 'owned_control_runs': 8, 'live_routes_identified_by_both_clients': 3,
                        'clean_route_results': 0, 'wildcard_discriminating_routes': 1,
                        'wildcard_ambiguity_refusals': 1, 'live_parameters_identified': 1,
                        'clean_parameter_results': 0, 'original_vulnerabilities_confirmed': 0}}
