"""Pinned secret-pattern scanners on owned fake controls, with no remote verification."""
from pathlib import Path
import subprocess
import tempfile

from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json

REPOSITORIES = {'betterleaks/betterleaks': 'executable',
                'trufflesecurity/trufflehog': 'executable'}
PINS = 'superhunter/product_supply/secrets-native-pins.json'
PINS_SHA = '790a7fd3c95f84dd9542f20a2f377489604163a536f58f2decf8b6841326a20e'
CASES = 'superhunter/product_supply/secrets-native-cases.json'
RELEASES = 'superhunter/product_supply/secrets-native-release-metadata.json'
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def inputs():
    raw = read_artifact(ROOT, PINS)
    if sha(raw) != PINS_SHA:
        raise EvidenceError('secrets native producer pins differ')
    pins = strict_json(raw)
    raw = read_artifact(ROOT, CASES)
    if (sha(raw) != pins['cases_sha256'] or
            sha(read_artifact(ROOT, RELEASES)) != pins['release_metadata_sha256']):
        raise EvidenceError('secrets native owned inputs or release provenance differ')
    return pins, strict_json(raw)


def native_rows(producer, raw):
    """Reject duplicate JSON keys and oversized output before interpreting native evidence."""
    if len(raw) > MAX_BYTES - 32:
        raise EvidenceError('secret scanner output exceeds the artifact limit')
    try:
        if producer == 'betterleaks':
            rows = strict_json(b'{"findings":' + raw + b'}')['findings']
            if type(rows) is not list:
                raise ValueError('findings must be an array')
        elif producer == 'trufflehog':
            rows = [strict_json(line) for line in raw.splitlines() if line.strip()]
        else:
            raise ValueError('unknown secret scanner')
        if any(type(row) is not dict for row in rows) or len(rows) > 32:
            raise ValueError('unexpected secret scanner records')
        return rows
    except (ValueError, KeyError, TypeError) as exc:
        raise EvidenceError('malformed native secret scanner evidence') from exc


def findings(producer, raw, name, cases):
    """Check native locations, detector identities and values against independent owned bytes."""
    if name not in cases['files']:
        raise EvidenceError('unknown owned credential control')
    source = cases['files'][name]
    expected = [row for row in cases['expected'] if row['file'] == name]
    result = []
    try:
        for row in native_rows(producer, raw):
            if producer == 'betterleaks':
                secret, line = row['Secret'], row['StartLine']
                if (row['File'] != 'fixtures/' + name or row['SymlinkFile'] != '' or
                        row['Commit'] != '' or row['Match'] != secret or
                        row['Attributes'] != {'confidence': 'high', 'path': 'fixtures/' + name,
                                              'resource': 'fs.content'} or
                        any(key.startswith('Validation') for key in row)):
                    raise EvidenceError('Betterleaks source or validation state differs')
            else:
                secret = row['Raw']
                location = row['SourceMetadata']['Data']['Filesystem']
                line = location['line']
                if (location != {'file': 'fixtures/' + name, 'line': line} or
                        row['SourceType'] != 15 or row['DecoderName'] != 'PLAIN' or
                        row['Verified'] is not False or row['VerificationFromCache'] is not False):
                    raise EvidenceError('TruffleHog source or verification state differs')
            if type(line) is not int or type(secret) is not str:
                raise EvidenceError('native secret location or value has the wrong type')
            matches = [e for e in expected if e['line'] == line and e['value'] == secret]
            if len(matches) != 1:
                raise EvidenceError('native secret finding does not match an owned positive')
            match = matches[0]
            # Independent location check against the exact source sent to the engine.
            column = match['column']
            text = source.splitlines()[line - 1]
            if text[column - 1:column - 1 + len(secret)] != secret:
                raise EvidenceError('native secret location differs from owned input bytes')
            if producer == 'betterleaks':
                if (row['RuleID'] != match['kind'] or row['EndLine'] != line or
                        type(row['StartColumn']) is not int or row['StartColumn'] != column or
                        type(row['EndColumn']) is not int or row['EndColumn'] != column + len(secret) - 1 or
                        row['Fingerprint'] != f'fixtures/{name}:{match["kind"]}:{line}'):
                    raise EvidenceError('Betterleaks detector or byte span differs')
                detector, confidence, column_origin = row['RuleID'], 'high', 'native'
            else:
                if (row['DetectorName'] != match['trufflehog_detector'] or
                        row['DetectorType'] != match['trufflehog_detector_type'] or
                        row['SecretParts'].get('key') != secret):
                    raise EvidenceError('TruffleHog detector identity or secret parts differ')
                detector, confidence, column_origin = row['DetectorName'], None, 'owned-input-byte-search'
            result.append({'file': name, 'line': line, 'column': column,
                           'column_origin': column_origin, 'kind': match['kind'],
                           'detector': detector, 'native_confidence': confidence,
                           'native_severity': None, 'value_sha256': sha(secret.encode()),
                           'verification': 'disabled', 'synthetic': True})
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise EvidenceError('malformed native secret scanner finding') from exc
    expected_keys = sorted((e['line'], sha(e['value'].encode())) for e in expected)
    actual_keys = sorted((r['line'], r['value_sha256']) for r in result)
    if actual_keys != expected_keys:
        raise EvidenceError('secret scanner missed, duplicated or added an owned control')
    return {'input_sha256': sha(source.encode()), 'findings': sorted(result, key=lambda r: (r['line'], r['kind']))}


def agreement(sections):
    def identities(producer):
        return sorted((r['file'], r['line'], r['column'], r['kind'], r['value_sha256'])
                      for case in sections[producer]['cases'].values() for r in case['findings'])
    left, right = identities('betterleaks'), identities('trufflehog')
    if left != right:
        raise EvidenceError('native scanners disagree on the owned credential controls')
    return {'matching_synthetic_findings': len(left), 'locations_and_value_hashes_agree': True,
            'real_credentials_verified': 0, 'original_vulnerabilities_confirmed': 0}


def run(kit):
    """Execute native built-in rules only on three fixed fake-credential controls."""
    pins, cases = inputs()
    kit = Path(kit)
    with tempfile.TemporaryDirectory(prefix='nqc-secrets-native-') as tmp:
        work = Path(tmp)
        for name, pin in pins['files'].items():
            copy_release(name, kit/name, work/name, pin['sha256'], limit=pin['bytes'])
        (work/'fixtures').mkdir()
        for name, content in cases['files'].items():
            (work/'fixtures'/name).write_text(content)
        # No inherited tokens, proxy settings, scanner configs, or home-directory state.
        env = {'HOME': tmp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TMPDIR': tmp}

        def execute(producer, args):
            process = subprocess.run([*ISOLATE, str(work/producer), *args], cwd=work, env=env,
                                     stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=60)
            if process.stderr or len(process.stdout) > MAX_BYTES:
                raise EvidenceError('secret scanner emitted unexpected diagnostics or oversized output')
            return process.stdout

        versions = {'betterleaks': ('version', b'1.10.1\n'),
                    'trufflehog': ('--version', b'trufflehog 3.100.0\n')}
        sections = {}
        for producer, (flag, expected) in versions.items():
            if execute(producer, [flag]) != expected:
                raise EvidenceError('secret scanner runtime version differs from pinned release')
            sections[producer] = {'version': expected.decode().strip(),
                                  'rules': 'unmodified built-in defaults', 'cases': {}}
        for name in sorted(cases['files']):
            # Each call receives one fixed owned file. No repository or history scan occurs.
            raw = execute('betterleaks', ['dir', 'fixtures/' + name, '--validation=false',
                          '--no-banner', '--no-color', '--log-level', 'error', '--exit-code', '0',
                          '--report-format', 'json', '--report-path', '-'])
            sections['betterleaks']['cases'][name] = findings('betterleaks', raw, name, cases)
            raw = execute('trufflehog', ['filesystem', 'fixtures/' + name, '--no-verification',
                          '--no-update', '--json', '--no-color', '--concurrency', '1',
                          '--fail-on-scan-errors', '--force-skip-archives', '--force-skip-binaries',
                          '--max-decode-depth', '1', '--log-level=-1'])
            sections['trufflehog']['cases'][name] = findings('trufflehog', raw, name, cases)
        sections['agreement'] = agreement(sections)
    return {'schema_version': 1, 'query': 'secrets-native', 'producers': pins['sources'],
            'pins_sha256': PINS_SHA, 'cases_sha256': pins['cases_sha256'],
            'sections': sections, 'sections_sha256': sha(canonical(sections)),
            'scope': {'owned_fixed_controls_only': True, 'network_namespace': 'isolated',
                      'remote_verification': False, 'credential_revocation': False,
                      'native_default_rules': True, 'arbitrary_target_scanning': False,
                      'limitation': 'Synthetic pattern detection demonstrates these controls only; '
                                    'it does not establish real credential validity or scanner-wide precision.'}}
