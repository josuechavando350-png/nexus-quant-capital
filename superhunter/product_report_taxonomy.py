"""Resolve citations in existing report exports against two pinned WSTG editions."""
from collections import Counter
from io import BytesIO
import re
from xml.etree import ElementTree
from zipfile import ZipFile

from .product_reasoning import EvidenceError
from .product_review import sha
from .product_sources import git
from .safe_io import canonical, strict_json

GUIDE = 'OWASP/wstg'
EXPORTER = 'wapiti-scanner/wapiti'
CURRENT = 'checklists/checklist.json'
RELEASE = 'checklists/WSTG-Checklist_v4.2.xlsx'
EXPORTS = {name: 'tests/reports/data/' + name + '.json'
           for name in ('report', 'report_level1', 'report_level2')}
SOURCES = {
    GUIDE: ('049-wstg', '97d915fa54f0c21b99094acdc5af677be3dc780f', {
        CURRENT: '0970568c4219f5c8f3cdaf120bb08d8502153eb3b49abeb1999b3e0fad3b5c7b',
        RELEASE: '03d487cf4ef975973f1246c01937de8d5cf22f32c6ffdf44493f6b7dc01963eb'}),
    EXPORTER: ('067-wapiti', 'e786fdb0e4b581e501e1a04c27f2e59eb41bdbbb', {
        EXPORTS['report']: 'eabafbcdc509bca51d6e585313ab062d72da203c0886522fee6bd5354ffb52d9',
        EXPORTS['report_level1']: 'ba811573b78a8cebbdb505f49d5dc913d70fe957c68c57247a0675f6ff72517f',
        EXPORTS['report_level2']: 'b97003798cdee22a2887386e6b2be75b00be58f2cabd7625ad9b3487ff9d2891'}),
}
CODE = re.compile(r'WSTG-[A-Z]{3,5}-[0-9]{2}')
SECTIONS = ('vulnerabilities', 'anomalies', 'additionals')


def load_files(root, name):
    folder, revision, pins = SOURCES[name]
    checkout = root / folder
    if checkout.is_symlink() or git(checkout, 'rev-parse', 'HEAD').decode().strip() != revision:
        raise EvidenceError('report taxonomy source revision differs')
    data = {}
    for path, digest in pins.items():
        raw = git(checkout, 'show', revision + ':' + path)
        if sha(raw) != digest:
            raise EvidenceError('report taxonomy source bytes differ')
        data[path] = raw
    return data


def current_codes(raw):
    groups = strict_json(raw)['categories']
    result = set()
    for group in groups.values():
        for test in group['tests']:
            code = test['id']
            if not CODE.fullmatch(code) or not code.startswith(group['id'] + '-') or code in result:
                raise EvidenceError('ambiguous WSTG checklist entry')
            result.add(code)
    return result


def release_codes(raw):
    # This function reads two known members of the hash-verified release workbook.
    # Only column A of the testing checklist declares identifiers.
    with ZipFile(BytesIO(raw)) as book:
        def xml(name):
            member = book.getinfo(name)
            if member.file_size > 120_000:
                raise EvidenceError('release worksheet exceeds its read limit')
            return ElementTree.fromstring(book.read(member))
        strings = [''.join(s.itertext()) for s in xml('xl/sharedStrings.xml')]
        cells = xml('xl/worksheets/sheet1.xml').iterfind('.//{*}c[@t="s"]')
        codes = []
        for cell in cells:
            if re.fullmatch(r'A[1-9][0-9]*', cell.attrib['r']):
                text = strings[int(cell.findtext('{*}v'))]
                if CODE.fullmatch(text):
                    codes.append(text)
    if not codes or len(codes) != len(set(codes)):
        raise EvidenceError('empty or ambiguous WSTG release checklist')
    return set(codes)


def cited_codes(values):
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise EvidenceError('invalid citation list')
    if len(set(values)) != len(values):
        raise EvidenceError('duplicate citation in one entry')
    if any(v.startswith('WSTG-') and not CODE.fullmatch(v) for v in values):
        raise EvidenceError('malformed WSTG citation')
    return {v for v in values if CODE.fullmatch(v)}


def summarize(data, current, release):
    classifications = {k: cited_codes(v['wstg']) for k, v in data['classifications'].items()}
    catalog = set().union(*classifications.values())
    cited = Counter()
    counts = {}
    for section in SECTIONS:
        counts[section] = 0
        for name, rows in data[section].items():
            if not isinstance(rows, list):
                raise EvidenceError('unexpected export record collection')
            for row in rows:
                codes = cited_codes(row['wstg'])
                if name not in classifications or not codes <= classifications[name]:
                    raise EvidenceError('record cites a different classification')
                cited.update(codes)
                counts[section] += 1
    if data['suppressed_findings']:
        raise EvidenceError('suppression semantics unverified for this export')
    # Report membership of a *cited ID*, never assert that a test was performed.
    resolved = {'both': [], 'release_4_2_only': [], 'current_only': [], 'neither': []}
    editions = {(True, True): 'both', (True, False): 'current_only',
                (False, True): 'release_4_2_only', (False, False): 'neither'}
    for code in sorted(cited):
        resolved[editions[code in current, code in release]].append(code)
    return {'records_by_section': counts, 'citations_in_records': dict(sorted(cited.items())),
            'classified_ids': len(catalog), 'edition_membership': resolved}


def review(root):
    guide = load_files(root, GUIDE)
    current = current_codes(guide[CURRENT])
    release = release_codes(guide[RELEASE])
    reports = load_files(root, EXPORTER)
    summaries = {key: summarize(strict_json(reports[path]), current, release)
                 for key, path in EXPORTS.items()}
    classifications = {'current_ids': len(current), 'release_4_2_ids': len(release),
                       'shared_ids': len(current & release),
                       'edition_membership_by_export': {k: v['edition_membership']
                                                        for k, v in summaries.items()}}
    def observation(name, operation, result):
        return {'revision': SOURCES[name][1], 'upstream_sha256': SOURCES[name][2],
                'operation': operation, 'result': result}
    return {GUIDE: observation(GUIDE, 'resolve cited test identifiers by checklist edition', classifications),
            EXPORTER: observation(EXPORTER, 'extract item citations from three offline exports', {
                'summaries': summaries, 'edition_decisions_sha256': sha(canonical(classifications))})}
