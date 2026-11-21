"""Apply the pinned Go digest rule to NQC's fixed Census header comparator and two controls."""
from pathlib import Path
import subprocess
import tarfile
import tempfile

from .product_census_header import GETH_REVISION, pinned
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json

GOSEC_REV = '244f1f6f4d1d0d14f89e79a73dab1219eabb5228'
GOSEC_SHA = 'c627296e4e69c8dcf57abd44419fb51d9eb0a4fe3d32e3b03c8201e9809fcc47'
GO_SHA = '65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40'
SOURCE = 'superhunter/product_supply/geth-header-main.txt'
SOURCE_SHA = '9ce7504add1fd9baf6500f92a84a45f4423bd14df95c323ad3d761179e2fdb66'

MODULE_PINS = {'go.mod': '57e87833320a77060bcbc38271847bf85fd5ffc9770ac3ffe16eaa8ee3ab6330', 'go.sum': '1a136fd995017cb3479111007ffd99fef598186afa920b9246151356ce6d9399'}


def variants(raw):
    if raw.count(b'"crypto/sha256"') != 1 or raw.count(b'sha256.Sum256(encoded)') != 1:
        raise EvidenceError('unexpected source locations for digest controls')
    return {'original': raw, 'alternate': raw.replace(b'"crypto/sha256"', b'"crypto/sha512"')
            .replace(b'sha256.Sum256(encoded)', b'sha512.Sum512_256(encoded)'),
            'changed': raw.replace(b'"crypto/sha256"', b'"crypto/md5"')
            .replace(b'sha256.Sum256(encoded)', b'md5.Sum(encoded)')}


def assess(report, sources, work):
    if report.get('Golang errors') != {} or report['Stats']['files'] != 3 or report['Stats']['nosec'] != 0:
        raise EvidenceError('incomplete Go source review')
    issues = []
    for finding in report['Issues'] or []:
        path = Path(finding['file'])
        if path not in {work/k/'main.go' for k in sources} or finding.get('nosec') or finding.get('suppressions'):
            raise EvidenceError('finding is unbound or suppressed')
        scope = path.parent.name
        line = int(finding['line'])
        col = int(finding['column'])
        content = sources[scope].splitlines()
        if not 1 <= line <= len(content):
            raise EvidenceError('Go diagnostic outside source bytes')
        if (scope != 'changed' or finding['rule_id'] != 'G401' or finding['cwe']['id'] != '328' or
                finding['confidence'] != 'HIGH' or content[line-1].lstrip() != b'digest := md5.Sum(encoded)'
                or content[line-1][col-1:col+6] != b'md5.Sum'):
            raise EvidenceError('Go diagnostic differs from independent source witness')
        issues.append({'case': scope, 'rule': 'G401', 'cwe': '328', 'line': line, 'column': col,
                       'confidence': finding['confidence'], 'severity': finding['severity']})
    if report['Stats']['found'] != 1 or len(issues) != 1:
        raise EvidenceError('missing or duplicate digest control finding')
    return {'diagnostics': issues, 'clean_cases': ['alternate', 'original'],
            'inputs_sha256': {k: sha(v) for k, v in sources.items()}, 'reviewed_files': 3}


def build(checkout, kit, header):
    if checkout is None or header is None:
        raise EvidenceError('Go source review requires the Geth Census comparison')
    geth = checkout/'upstream/037-go-ethereum'
    gosec = checkout/'upstream/105-gosec'
    for repo, revision in ((geth, GETH_REVISION), (gosec, GOSEC_REV)):
        if git(repo, 'rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('unreviewed Go source revision')
    sources = variants(pinned(ROOT, SOURCE, SOURCE_SHA))
    with tempfile.TemporaryDirectory(prefix='nqc-owned-digest-') as tmp:
        work = Path(tmp)
        for name, raw in sources.items():
            (work/name).mkdir()
            (work/name/'main.go').write_bytes(raw)
        for target, digest in MODULE_PINS.items():
            data = pinned(ROOT, 'superhunter/product_supply/header-digest/' + target.replace('.', '-') + '.txt', digest)
            (work/target).write_bytes(data)
        copy_release('gosec', kit/'gosec', work/'gosec', GOSEC_SHA)
        copy_release('Go archive', kit/'go.tgz', work/'go.tgz', GO_SHA, executable=False)
        with tarfile.open(work/'go.tgz') as archive:
            archive.extractall(work, filter='data')
        (work/'geth').mkdir()
        subprocess.run(['git', '--no-replace-objects', '-C', geth, 'archive', '--format=tar',
                        '-o', work/'geth.tar', GETH_REVISION], check=True, timeout=60)
        with tarfile.open(work/'geth.tar') as archive:
            archive.extractall(work/'geth', filter='data')
        (work/'tmp').mkdir()
        env = {'HOME': tmp, 'TMPDIR': str(work/'tmp'), 'GOPATH': str(work/'gopath'), 'GOROOT': str(work/'go'),
               'PATH': str(work/'go/bin') + ':/usr/bin:/bin',
               'GOENV': 'off', 'GOWORK': 'off', 'GOTOOLCHAIN': 'local', 'CGO_ENABLED': '0',
               'GOMAXPROCS': '3', 'GOCACHE': str(work/'buildcache'), 'GOMODCACHE': str(work/'modules'),
               'GOPROXY': (kit/'proxy').resolve(strict=True).as_uri(), 'GOSUMDB': 'off', 'GOFLAGS': '-mod=readonly'}
        subprocess.run([*ISOLATE, work/'gosec', '-include=G401', '-no-fail', '-tags=purego', '-fmt=json',
                        '-out', work/'result.json', './original', './alternate', './changed'],
                       cwd=work, env=env, capture_output=True, check=True, timeout=180)
        result = assess(strict_json(read_artifact(work, 'result.json')), sources, work)
    return {**result, 'gosec_revision': GOSEC_REV, 'gosec_sha256': GOSEC_SHA, 'go_archive_sha256': GO_SHA,
            'geth_revision': GETH_REVISION, 'geth_comparison_sha256': sha(canonical(header))}


def attach(index, checkout, kit):
    index.header_digest = build(checkout, kit, index.geth_header)
    index.repos['securego/gosec']['go_source_receipt'] = {
        'query': 'go-header-digest', 'revision': GOSEC_REV, 'report_sha256': sha(canonical(index.header_digest))}
