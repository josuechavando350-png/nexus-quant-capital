"""Check the NQC header worker's locked dependencies, source artifacts and CPE attribution."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote

from .product_reasoning import EvidenceError
from .safe_io import canonical, read_artifact

SUPPLY = Path(__file__).parent / 'product_supply'
LOCK = 'header-npm-lock.json'
OWNED = (LOCK, 'header-check.txt', 'header-digest/go-mod.txt', 'header-digest/go-sum.txt')
GRYPE = 'anchore/grype'
DC = 'dependency-check/DependencyCheck'
OSSF = 'ossf/package-analysis'
SCHEMA = 'core/src/main/resources/schema/dependency-suppression.1.4.xsd'
RULES = 'core/src/main/resources/dependencycheck-base-suppression.xml'
PINS = {
    GRYPE: ('137-grype', '8b2987cf575c69fb715ae4d3b15bb470e3e8f83b', (
        'grype/version/operator.go', 'grype/version/range.go', 'internal/stringutil/parse.go')),
    DC: ('138-dependencycheck', 'ae861fc07f84e3d0be75c2ed2e46b498bc03bcc1', (SCHEMA, RULES)),
    OSSF: ('144-package-analysis', 'a149a6f2e1179b8f0c05da6845d8513d360e3b1a', (
        'internal/utils/hash_file.go', 'internal/staticanalysis/linelengths/line_lengths.go')),
}
BUILD_SHA256 = 'bb5e0e05d85e038113c359b4cf9b196e35e52b72aab3e5eaf25e421698843435'
GO_SHA256 = '5f5eb6d0b2fb6aa0bb5d5f8c5f1c944e0de955c925f0111af92a9d8f79680b5b'
GO_WRAPPER = '''package version

func CheckLocked(phrase, actual string, compare func(string, string) (int, error)) (bool, error) {
	unit, err := parseRange(phrase)
	if err != nil || unit == nil {
		return false, err
	}
	if unit.Operator == EQ {
		comparison := 1
		if actual == unit.Version {
			comparison = 0
		}
		return unit.Satisfied(comparison), nil
	}
	comparison, err := compare(actual, unit.Version)
	if err != nil {
		return false, err
	}
	return unit.Satisfied(comparison), nil
}
'''
GO_MAIN = '''package main

import (
	"encoding/json"
	"fmt"
	v "github.com/anchore/grype/grype/version"
	"github.com/ossf/package-analysis/internal/staticanalysis/linelengths"
	"github.com/ossf/package-analysis/internal/utils"
	"os"
	"strconv"
	"strings"
)

type query struct {
	Bounds []string
	Actual string
}
type request struct {
	Cases []query
	Files []string
}
type fileFact struct {
	Digest string
	Lines  []int
}

func cmp(a, b string) (int, error) {
	if a == b {
		return 0, nil
	}
	aa, bb := strings.Split(a, "."), strings.Split(b, ".")
	if len(aa) != 3 || len(bb) != 3 {
		return 0, fmt.Errorf("incomparable non-release")
	}
	for i := range aa {
		n, e := strconv.Atoi(aa[i])
		if e != nil {
			return 0, e
		}
		m, e := strconv.Atoi(bb[i])
		if e != nil {
			return 0, e
		}
		if n < m {
			return -1, nil
		}
		if n > m {
			return 1, nil
		}
	}
	return 0, nil
}
func run() error {
	var r request
	if err := json.NewDecoder(os.Stdin).Decode(&r); err != nil {
		return err
	}
	verdicts := make([]bool, 0, len(r.Cases))
	files := make([]fileFact, 0, len(r.Files))
	for _, q := range r.Cases {
		match := true
		for _, bound := range q.Bounds {
			ok, err := v.CheckLocked(bound, q.Actual, cmp)
			if err != nil {
				return err
			}
			match = match && ok
		}
		verdicts = append(verdicts, match)
	}
	for _, path := range r.Files {
		h, err := utils.SHA256Hash(path)
		if err != nil {
			return err
		}
		lines, err := linelengths.GetLineLengths(path, "")
		if err != nil {
			return err
		}
		files = append(files, fileFact{h, lines})
	}
	return json.NewEncoder(os.Stdout).Encode(struct {
		Verdicts []bool
		Files    []fileFact
	}{verdicts, files})
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
'''


def digest(data):
    return sha256(data).hexdigest()


def original_sources(root):
    sources = {}
    for repo, (folder, revision, names) in PINS.items():
        checkout = Path(root) / folder
        cmd = ['git', '--no-replace-objects', '-C', str(checkout)]
        def git(*args):
            return subprocess.run([*cmd, *args], capture_output=True, check=True, timeout=15).stdout
        if git('rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError(f'{repo} checkout differs from its approved commit')
        sources[repo] = {name: git('cat-file', 'blob', revision + ':' + name) for name in names}
    return sources


def build_native(work, sources):
    go = shutil.which('go')
    if go is None or digest(Path(go).read_bytes()) != GO_SHA256:
        raise EvidenceError('trust batch requires the Linux x86-64 Go 1.27.3 compiler from the vetted Go kit on PATH')
    for repo in (GRYPE, OSSF):
        base = work / 'src' / 'github.com' / repo
        for path, blob in sources[repo].items():
            target = base / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
    (work / 'src/github.com/anchore/grype/grype/version/nqc_contract.go').write_text(GO_WRAPPER)
    driver = work / 'src/github.com/ossf/package-analysis/cmd/nqc'
    driver.mkdir(parents=True)
    (driver / 'main.go').write_text(GO_MAIN)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'GOPATH': str(work),
           'GOROOT': str(Path(go).resolve().parents[1]), 'GO111MODULE': 'off', 'GOTOOLCHAIN': 'local',
           'GOENV': 'off', 'CGO_ENABLED': '0', 'GOOS': 'linux', 'GOARCH': 'amd64', 'GOMAXPROCS': '2'}
    temporary_cache = work / 'go-cache'
    env['GOCACHE'] = str(temporary_cache)
    built = work / 'review'
    subprocess.run([go, 'build', '-trimpath', '-buildvcs=false', '-o', str(built), '.'],
                   cwd=driver, env=env, check=True, capture_output=True, timeout=150)
    return built


def native(work, sources, queries, files):
    external = os.environ.get('NQC_TRUST_BINARY')
    if external:
        # Snapshot the cached bytes before validation to avoid executing a replaced path.
        built = work / 'review'
        with Path(external).open('rb') as reader:
            data = reader.read(5_000_001)
        if len(data) > 5_000_000 or digest(data) != BUILD_SHA256:
            raise EvidenceError('cached trust adapter differs from the pinned build')
        built.write_bytes(data)
        built.chmod(0o500)
    else:
        built = build_native(work, sources)
    binary_hash = digest(built.read_bytes())
    if binary_hash != BUILD_SHA256:
        raise EvidenceError('trust adapter differs from the reproducible build')
    data = {'Cases': queries, 'Files': [str(file) for file in files]}
    output = subprocess.run([str(built)], input=canonical(data), cwd=work, env={'HOME': str(work)},
                            check=True, capture_output=True, timeout=10)
    return json.loads(output.stdout), binary_hash


def version_bounds(selector):
    match = re.fullmatch(r'([~^]?)(\d+)\.(\d+)\.(\d+)(-[\w.]+)?', selector)
    if not match or (match[1] and match[5]):
        raise EvidenceError('unsupported NQC lock selector')
    op = match[1]
    if not op:
        return ['=' + selector]
    major, minor, patch = map(int, match.groups()[1:4])
    if op == '~' or (op == '^' and major == 0 and minor != 0):
        upper = (major, minor + 1, 0)
    elif major != 0:
        upper = (major + 1, 0, 0)
    else:
        upper = (0, 0, patch + 1)
    return ['>=' + selector[1:], '<' + '.'.join(map(str, upper))]


def oracle(selector, actual):
    """Independently decide membership via required pre-fix components and the floor."""
    if not selector.startswith(('^', '~')):
        return actual == selector
    floor = tuple(map(int, selector[1:].split('.')))
    value = tuple(map(int, actual.split('.')))
    if selector.startswith('~'):
        stable = 2
    else:
        stable = next((i + 1 for i, part in enumerate(floor) if part), 3)
    return value >= floor and value[:stable] == floor[:stable]


def locked_edges(packages):
    rows = []
    for path, record in sorted(packages.items()):
        for name, requirement in sorted(record.get('dependencies', {}).items()):
            base = path
            while True:
                child = (base + '/' if base else '') + 'node_modules/' + name
                if child in packages:
                    break
                if not base:
                    raise EvidenceError('unresolved dependency in the header lock')
                base = base.rpartition('node_modules/')[0].rstrip('/')
            actual = packages[child]['version']
            rows.append({'parent': path, 'name': name, 'selector': requirement, 'child': child, 'actual': actual})
    if not rows:
        raise EvidenceError('empty dependency graph')
    return rows


def cases_for(edges):
    cases, expected = [], []
    for edge in edges:
        selector, actual = edge['selector'], edge['actual']
        bounds = version_bounds(selector)
        mutated = str(int(actual.split('.')[0]) + 1) + '.0.0'
        cases.extend(({'Bounds': bounds, 'Actual': actual}, {'Bounds': bounds, 'Actual': mutated}))
        expected.extend((oracle(selector, actual), oracle(selector, mutated)))
    return cases, expected


def attribution(packages, roots):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    schema = etree.XMLSchema(etree.fromstring(roots[SCHEMA], parser))
    rules = etree.fromstring(roots[RULES], parser)
    schema.assertValid(rules)
    ns = '{https://jeremylong.github.io/DependencyCheck/dependency-suppression.1.4.xsd}'
    matches = [row for row in rules.findall(ns + 'suppress') if '#5454' in row.findtext(ns + 'notes', '')]
    if len(matches) != 1 or matches[0].get('base') != 'true':
        raise EvidenceError('ambiguous CPE rule')
    patterns = []
    for key in ('packageUrl', 'cpe'):
        element = matches[0].find(ns + key)
        if element is None or element.get('regex') != 'true':
            raise EvidenceError('missing upstream CPE matcher')
        patterns.append(re.compile(element.text))
    def rejects(purl, cpe):
        return bool(patterns[0].fullmatch(purl) and patterns[1].fullmatch(cpe))
    purls = sorted({'pkg:npm/' + quote(k.rsplit('node_modules/', 1)[1], safe='/') + '@' + r['version']
                    for k, r in packages.items() if k})
    incompatible = 'cpe:/a:flat_project:flat:5.0.2'
    invalid = [item for item in purls if rejects(item, incompatible)]
    if invalid != [p for p in purls if not p.startswith('pkg:npm/flat@')]:
        raise EvidenceError('suppression scope disagrees with package identity')
    if (not invalid or rejects('pkg:npm/flat@5.0.2', incompatible)
            or any(rejects(p, 'cpe:/a:other:unrelated:5.0.2') for p in purls)):
        raise EvidenceError('wrong identity suppressed')
    return {'package_urls': purls, 'rejected_flat_cpe_candidates': len(invalid),
            'flat_identity_control_preserved': True, 'unrelated_cpe_controls_preserved': len(purls),
            'rule_issue': 5454, 'schema': 'dependency-suppression.1.4.xsd'}


def check_files(files, facts):
    if len(facts) != len(files):
        raise EvidenceError('file record count differs')
    rows = {}
    for (name, data), record in zip(files.items(), facts, strict=True):
        expected = [len(line.removesuffix(b'\r')) for line in data.split(b'\n')[:-1]]
        tail = data.rsplit(b'\n', 1)[-1]
        if tail or not expected:
            expected.append(len(tail))
        if record['Digest'] != digest(data) or record['Lines'] != expected:
            raise EvidenceError('OpenSSF file evidence differs from independently read bytes')
        rows[name] = {'sha256': record['Digest'], 'bytes': len(data), 'lines': len(expected),
                      'max_line_bytes': max(expected), 'line_lengths_sha256': digest(canonical(expected))}
    return rows


def review(source_root: Path):
    sources = original_sources(source_root)
    owned = {name: read_artifact(SUPPLY, name) for name in OWNED}
    packages = json.loads(owned[LOCK])['packages']
    edges = locked_edges(packages)
    queries, expected = cases_for(edges)
    # Change one character without changing any line length, then fold whitespace
    # without changing any dependency. Each control challenges a different signal.
    owned['same-width-change'] = owned[LOCK].replace(b'nqc-header-review', b'nqc-header-Review', 1)
    owned['compacted'] = canonical(json.loads(owned[LOCK]))
    with tempfile.TemporaryDirectory(prefix='nqc-trust-') as folder:
        work = Path(folder)
        for name, data in owned.items():
            destination = work / 'inputs' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        output, binary = native(work, sources, queries, [work / 'inputs' / name for name in owned])
    if output['Verdicts'] != expected or not all(expected[::2]) or any(expected[1::2]):
        raise EvidenceError('range evaluation differs from lock requirements')
    rows = check_files(owned, output['Files'])
    unchanged_shape = rows[LOCK]['line_lengths_sha256'] == rows['same-width-change']['line_lengths_sha256']
    if (not unchanged_shape or rows[LOCK]['sha256'] == rows['same-width-change']['sha256']
            or rows['compacted']['lines'] != 1 or rows[LOCK]['lines'] <= 1):
        raise EvidenceError('file-evidence controls did not distinguish the mutations')
    output = {
        GRYPE: {'operation': 'evaluate normalized version bounds for resolved NQC npm dependency edges',
                'checked_edges': len(edges), 'edges': edges, 'out_of_range_controls_rejected': len(edges),
                'native_build_sha256': binary},
        OSSF: {'operation': 'verify content digest and line-byte profile of NQC source and dependency inputs',
               'files': rows, 'native_build_sha256': binary, 'same_width_mutation_detected': True,
               'semantic_equivalent_reformat_detected': True},
        DC: {'operation': 'reject a controlled CPE misattribution against locked NQC package identities',
             **attribution(packages, sources[DC])},
    }
    for repo, row in output.items():
        row.update(revision=PINS[repo][1], input_lock_sha256=digest(owned[LOCK]),
                   source_sha256={name: digest(blob) for name, blob in sources[repo].items()})
    return output
