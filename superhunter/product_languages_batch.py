"""Review Census integer representations and cross-tool digest evidence on fixed source."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from .product_census_header import FIXTURE, FIXTURE_SHA, pinned
from .product_header_digest import SOURCE, SOURCE_SHA, variants
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .safe_io import canonical, strict_json
from .repository_boundary import git_object

PROJECTS = {
    'Ericsson/codechecker': ('102-codechecker', '53222cd5d7566c553d8d7edbb5134a35a56ef15e'),
    'cppcheck-opensource/cppcheck': ('103-cppcheck', 'e1b5791564c662c7dacbc62835f6abe5431aa00b'),
    'spotbugs/spotbugs': ('109-spotbugs', 'f4544188eb473d60221572fc0d5645325c8b18eb'),
    'find-sec-bugs/find-sec-bugs': ('110-find-sec-bugs', 'aa1293a6339a04ddf954670fc550847d1bcd83be'),
}
CPP = 'cppcheck-opensource/cppcheck'
CC = 'Ericsson/codechecker'
SPOT = 'spotbugs/spotbugs'
FSB = 'find-sec-bugs/find-sec-bugs'
CPP_FILES = tuple('lib/' + n for n in ('platform.cpp', 'platform.h', 'config.h', 'mathlib.h',
    'standards.h', 'utils.h', 'path.h', 'xml.h')) + ('externals/tinyxml2/tinyxml2.h',)
CC_PATH = 'tools/report-converter/codechecker_report_converter/'
CC_FILES = ('__init__.py', 'util.py', 'report/__init__.py', 'report/hash.py')
METADATA = 'findsecbugs-plugin/src/main/resources/metadata/'
SCHEMA = 'spotbugs/etc/findbugsplugin.xsd'
MODELS = {'unix32': (4, 4, 8), 'unix64': (4, 8, 8), 'win64': (4, 4, 8)}
WIDTHS = ('int', 'long', 'long long')
BOUNDS = (0, 2**31-1, 2**31, 2**63-1, 2**63, 2**64-1)
DRIVER = """#include "platform.h"
#include <iostream>
int main() {
    unsigned long long value;
    while (std::cin >> value) {
        for (auto abi : {Platform::Unix32, Platform::Unix64, Platform::Win64}) {
            Platform model;
            if (!model.set(abi)) return 2;
            auto n = MathLib::biguint(value);
            std::cout << model.isIntValue(n) << model.isLongValue(n) << model.isLongLongValue(n) << ' ';
        }
        std::cout << '\\n';
    }
    return !std::cin.eof();
}
"""
CC_WORKER = """import json, sys
sys.path.insert(0, '.')
from codechecker_report_converter.report import File, Report
from codechecker_report_converter.report.hash import get_report_hash, HashType
out = []
for name, content, line, col, message in json.load(sys.stdin):
    report = Report(File(name, content=content), line, col, message, 'nqc-census-integer-width')
    out.append(get_report_hash(report, HashType.CONTEXT_FREE))
print(json.dumps({"keys": out}))
"""
VALIDATOR = """import java.io.File;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.SchemaFactory;
import org.xml.sax.SAXParseException;
class Validate {
    public static void main(String[] args) throws Exception {
        var factory = SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        var schema = factory.newSchema(new File("plugin.xsd"));
        for (String path : args) {
            try {
                schema.newValidator().validate(new StreamSource(new File(path)));
                System.out.println("PASS");
            } catch (SAXParseException ex) { System.out.println("REJECT"); }
        }
    }
}
"""


def run(work, args, data=b''):
    return subprocess.run([*ISOLATE, *args], cwd=work, input=data, capture_output=True,
                          env={'HOME': str(work), 'TMPDIR': str(work), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                          check=True, timeout=40).stdout


def source_files(root, name, files):
    directory, revision = PROJECTS[name]
    repo = root/directory
    if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD').decode().strip() != revision:
        raise EvidenceError('unreviewed source revision for ' + name)
    listed = git(repo, 'ls-tree', '-z', revision, '--', *files)
    blobs = {}
    for entry in listed.split(b'\0'):
        if not entry:
            continue
        meta, name_bytes = entry.split(b'\t', 1)
        mode, kind, oid = meta.split()
        path = name_bytes.decode()
        if path not in files or mode != b'100644' or kind != b'blob':
            raise EvidenceError('unexpected source object for ' + path)
        data = git(repo, 'cat-file', 'blob', oid.decode())
        if git_object('blob', data) != oid.decode():
            raise EvidenceError('corrupt upstream blob for ' + path)
        blobs[path] = data
    if set(blobs) != set(files):
        raise EvidenceError('missing source objects for ' + name)
    return blobs


def receipt(name, kind, operation, blobs, result):
    return {'revision': PROJECTS[name][1], 'role': kind, 'operation': operation,
            'upstream_sha256': {path: sha(raw) for path, raw in blobs.items()}, 'result': result}


def write_files(work, files):
    for path, raw in files.items():
        out = work/path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)


def quantities(block):
    names = ('number', 'gasLimit', 'gasUsed', 'baseFeePerGas', 'timestamp', 'excessBlobGas', 'blobGasUsed')
    result = {k: (k, int(block[k], 16)) for k in names}
    result['timestamp_milliseconds'] = ('timestamp', result['timestamp'][1] * 1000)
    result['base_fee_for_gas_used'] = ('gasUsed', result['gasUsed'][1] * result['baseFeePerGas'][1])
    result['base_fee_for_gas_limit'] = ('gasLimit', result['gasLimit'][1] * result['baseFeePerGas'][1])
    if any(not 0 <= n < 2**64 for _, n in result.values()):
        raise EvidenceError('input exceeds the unsigned 64-bit review domain')
    return result


def fits(value, width):
    try:
        struct.pack({4: '>i', 8: '>q'}[width], value)
        return True
    except struct.error:
        return False


def verify_widths(output, quantities_by_name):
    values = [value for _, value in quantities_by_name.values()] + list(BOUNDS)
    rows = [line.split() for line in output.splitlines()]
    if len(rows) != len(values):
        raise EvidenceError('Cppcheck omitted an observation')
    flags = []
    for value, row in zip(values, rows):
        expected = [''.join('1' if fits(value, width) else '0' for width in sizes) for sizes in MODELS.values()]
        if row != expected:
            raise EvidenceError('Cppcheck ABI and independent signed encodings disagree')
        flags.append(row)
    rejected = {}
    for name, row in zip(quantities_by_name, flags):
        rejected[name] = [abi + '/' + ctype for abi, bits in zip(MODELS, row)
                          for ctype, bit in zip(WIDTHS, bits) if bit == '0']
    return rejected


def cppcheck(work, files, raw):
    write_files(work, files)
    (work/'driver.cc').write_text(DRIVER)
    run(work, ['/usr/bin/g++', '-std=c++17', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
               '-Ilib', '-Iexternals/tinyxml2', 'lib/platform.cpp', 'driver.cc', '-o', 'widths'])
    q = quantities(strict_json(raw)['block'])
    values = [value for _, value in q.values()] + list(BOUNDS)
    output = run(work, ['./widths'], ''.join(f'{v}\n' for v in values).encode()).decode()
    exclusions = verify_widths(output, q)
    return q, {'input_sha256': sha(raw), 'values': {k: v for k, (_, v) in q.items()},
               'incompatible_signed_encodings': exclusions, 'checked_abis': list(MODELS),
               'boundary_values': list(BOUNDS), 'comparisons': len(values) * len(MODELS) * len(WIDTHS),
               'stdout_sha256': sha(output.encode())}


def codechecker(work, files, raw, q, widths):
    write_files(work, {'codechecker_report_converter/' + p[len(CC_PATH):]: data for p, data in files.items()})
    content = raw.decode()
    basename = Path(FIXTURE).name
    source_lines = content.splitlines()
    samples, labels = [], []
    for name, exclusions in widths['incompatible_signed_encodings'].items():
        if not exclusions:
            continue
        key = json.dumps(q[name][0])
        line, = [i for i, text in enumerate(source_lines, 1) if text.lstrip().startswith(key + ':')]
        col = source_lines[line - 1].index(key) + 1
        message = name + ' outside signed representations ' + ', '.join(exclusions)
        samples.append([basename, content, line, col, message])
        indented = '\n'.join('   ' + s for s in source_lines)
        samples.append([basename, indented, line, col + 3, message])
        labels.append(name)
    if not labels:
        raise EvidenceError('no integer representations available to reconcile')
    keys = strict_json(run(work, [sys.executable, '-B', '-I', '-S', '-c', CC_WORKER], canonical(samples)))["keys"]
    # CodeChecker uses MD5 as an issue key. SHA-256 identifies the complete evidence.
    expected = []
    for filename, text, line, col, message in samples:
        witness = text.splitlines()[line-1]
        relative = str(sum(not c.isspace() for c in witness[:col]))
        normalized = ''.join(c for c in witness if not c.isspace())
        segments = [filename, message, normalized, relative, relative]
        expected.append(hashlib.md5('|||'.join(segments).encode(), usedforsecurity=False).hexdigest())
    if keys != expected or keys[::2] != keys[1::2] or len(set(keys)) != len(labels):
        raise EvidenceError('diagnostic identity differs across independent comparison or indentation')
    return {'source_sha256': sha(raw), 'cppcheck_sha256': sha(canonical(widths)), 'scope': FIXTURE,
            'source_anchored_keys': dict(zip(labels, keys[::2])), 'input_reports': len(samples),
            'distinct_reports': len(labels)}


def descriptor_order(descriptor):
    root = ET.fromstring(descriptor)
    registrars, detectors = root.findall('EngineRegistrar'), root.findall('Detector')
    if len(registrars) != 1 or not detectors or list(root).index(registrars[0]) > list(root).index(detectors[0]):
        raise EvidenceError('expected reviewed upstream component order')
    original_elements = sorted(ET.tostring(e) for e in root)
    root.remove(registrars[0])
    root.insert(list(root).index(detectors[-1])+1, registrars[0])
    if original_elements != sorted(ET.tostring(e) for e in root):
        raise EvidenceError('semantic content changed during order normalization')
    return root


def plugin_schema(work, schema, descriptor):
    normalized = descriptor_order(descriptor)
    bad = copy.deepcopy(normalized)
    pattern, = bad.findall("BugPattern[@type='WEAK_MESSAGE_DIGEST_MD5']")
    pattern.set('cweid', '0')
    duplicated = copy.deepcopy(normalized)
    duplicated.append(copy.deepcopy(duplicated.findall('BugPattern')[-1]))
    files = {'original.xml': descriptor, 'normalized.xml': ET.tostring(normalized),
             'invalid-cwe.xml': ET.tostring(bad), 'duplicate-id.xml': ET.tostring(duplicated)}
    write_files(work, {**files, 'plugin.xsd': schema, 'Validate.java': VALIDATOR.encode()})
    statuses = run(work, ['/usr/bin/java', '-Xmx128m', 'Validate.java', *files]).decode().splitlines()
    if statuses != ['REJECT', 'PASS', 'REJECT', 'REJECT']:
        raise EvidenceError('unexpected plugin compatibility or XML controls')
    return normalized, {'descriptor_sha256': sha(descriptor), 'validated_projection_sha256': sha(files['normalized.xml']),
                        'schema_results': dict(zip(files, statuses)), 'preserved_elements': len(normalized)}


def digest_patterns(descriptor, messages, sources):
    names = ('WEAK_MESSAGE_DIGEST_MD5', 'WEAK_MESSAGE_DIGEST_SHA1')
    callback, = [r for r in descriptor.findall('Detector') if r.get('class', '').endswith('.WeakMessageDigestDetector')]
    if callback.get('reports', '').split(',') != list(names):
        raise EvidenceError('digest detector registration differs')
    translations = {}
    catalog = ET.fromstring(messages)
    for name in names:
        pattern, = descriptor.findall(f"BugPattern[@type='{name}']")
        message, = catalog.findall(f"BugPattern[@type='{name}']/ShortDescription")
        title = (message.text or '').strip()
        if pattern.get('category') != 'SECURITY' or pattern.get('cweid') != '328' or not title:
            raise EvidenceError('digest class lacks corroborated category, CWE or explanation')
        translations[name] = {'cwe': int(pattern.get('cweid')), 'explanation': title}
    signatures = {b'md5.Sum(encoded)': ('MD5', names[0]), b'sha256.Sum256(encoded)': ('SHA-256', None),
                  b'sha512.Sum512_256(encoded)': ('SHA-512/256', None)}
    cases = {}
    for case, raw in sources.items():
        matches = [(algorithm, rule, index) for token, (algorithm, rule) in signatures.items()
                   for index, line in enumerate(raw.splitlines(), 1) if line.strip() == b'digest := ' + token]
        if len(matches) != 1:
            raise EvidenceError('digest source witness missing or ambiguous')
        algorithm, rule, line = matches[0]
        cases[case] = {'algorithm': algorithm, 'line': line, 'source_sha256': sha(raw),
                       'pattern': rule, 'taxonomy': translations[rule] if rule else None}
    if {case for case, row in cases.items() if row['pattern']} != {'changed'}:
        raise EvidenceError('unexpected classification on Census digest controls')
    return {'classification': cases, 'descriptor_detector': callback.get('class'),
            'usage': 'rule taxonomy for fixed Go digest observations'}


def review(source_root: Path):
    cpp = source_files(source_root, CPP, CPP_FILES)
    cc = source_files(source_root, CC, [CC_PATH+p for p in CC_FILES])
    spot = source_files(source_root, SPOT, [SCHEMA])
    fsb = source_files(source_root, FSB, [METADATA+'findbugs.xml', METADATA+'messages.xml'])
    header = pinned(ROOT, FIXTURE, FIXTURE_SHA)
    sources = variants(pinned(ROOT, SOURCE, SOURCE_SHA))
    with tempfile.TemporaryDirectory(prefix='nqc-static-languages-') as folder:
        work = Path(folder)
        q, ranges = cppcheck(work, cpp, header)
        keys = codechecker(work, cc, header, q, ranges)
        descriptor, schema = plugin_schema(work, spot[SCHEMA], fsb[METADATA+'findbugs.xml'])
    digest = digest_patterns(descriptor, fsb[METADATA+'messages.xml'], sources)
    digest['schema_result_sha256'] = sha(canonical(schema))
    return {CPP: receipt(CPP, 'execution', 'census_integer_ranges', cpp, ranges),
            CC: receipt(CC, 'execution', 'reconcile_source_anchored_diagnostics', cc, keys),
            SPOT: receipt(SPOT, 'reference', 'validate_plugin_interchange', spot, schema),
            FSB: receipt(FSB, 'reference', 'classify_digest_evidence', fsb, digest)}
