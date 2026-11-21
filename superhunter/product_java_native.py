"""Native Java analysis with an owned bytecode witness and corrected controls."""
from pathlib import Path
import subprocess
import tempfile
from xml.etree import ElementTree

from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json

REPOSITORIES = {'spotbugs/spotbugs': 'executable', 'find-sec-bugs/find-sec-bugs': 'executable'}
PINS = 'superhunter/product_supply/java-native-pins.json'
PINS_SHA = 'b4c4a0e65e9722f44aedc308b4a1d42f9bfae01c3188bb37b2eebff738128bce'
PREFIX = 'superhunter/product_supply/java-native-'
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']
PLUGIN = 'com.h3xstream.findsecbugs'


def inputs():
    raw = read_artifact(ROOT, PINS)
    if sha(raw) != PINS_SHA:
        raise EvidenceError('Java native producer pins differ')
    pins = strict_json(raw)
    artifacts = {}
    for name in ('cases', 'maven', 'provenance'):
        raw = read_artifact(ROOT, PREFIX + name + '.json')
        if sha(raw) != pins[name + '_sha256']:
            raise EvidenceError('Java native owned inputs or provenance differ')
        artifacts[name] = raw
    recipe = read_artifact(ROOT, PREFIX + 'rebuild.txt')
    if sha(recipe) != pins['rebuild_sha256']:
        raise EvidenceError('Java native reconstruction recipe differs')
    return pins, strict_json(artifacts['cases'])


def expected_findings(plugin):
    definitions = [
        ('NP_ALWAYS_NULL', 1, 5, 'CORRECTNESS', 476, 'nullLength', 9, 3),
        ('NP_LOAD_OF_KNOWN_NULL_VALUE', 3, 19, 'STYLE', 476, 'nullLength', 9, 2),
        ('SQL_NONCONSTANT_STRING_PASSED_TO_EXECUTE', 1, 10, 'SECURITY', 89, 'lookup', 13, 14),
    ]
    if plugin:
        definitions.append(('SQL_INJECTION_JDBC', 2, 12, 'SECURITY', 89, 'lookup', 13, 14))
    return sorted([{'type': kind, 'priority': priority, 'rank': rank, 'category': category,
                    'cwe': cwe, 'class': 'OwnedUnsafe', 'method': method,
                    'file': 'OwnedUnsafe.java', 'line': line, 'bytecode_offset': offset}
                   for kind, priority, rank, category, cwe, method, line, offset in definitions],
                  key=lambda r: r['type'])


def analysis_report(raw, plugin, cases, source_directory):
    """Accept complete native analysis only when every issue maps to the owned source."""
    if len(raw) > MAX_BYTES or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
        raise EvidenceError('invalid Java analyzer XML size or declaration')
    try:
        root = ElementTree.fromstring(raw)
        if root.tag != 'BugCollection' or root.get('version') != '4.10.5':
            raise EvidenceError('Java analyzer version or output schema differs')
        for tag in ('Project', 'Errors', 'FindBugsSummary'):
            if len(root.findall(tag)) != 1:
                raise EvidenceError('Java analysis lacks an unambiguous completion record')
        project, errors, summary = root.find('Project'), root.find('Errors'), root.find('FindBugsSummary')
        if ([x.text for x in project.findall('Jar')] != ['classes/OwnedUnsafe.class', 'classes/OwnedSafe.class'] or
                [x.text for x in project.findall('AuxClasspathEntry')] != ['classes'] or
                [x.text for x in project.findall('SrcDir')] != [source_directory]):
            raise EvidenceError('Java analyzer project is outside the owned controls')
        plugins = [x.attrib for x in project.findall('Plugin')]
        if plugins != ([{'id': PLUGIN, 'enabled': 'true'}] if plugin else []):
            raise EvidenceError('FindSecBugs plugin activation differs')
        if errors.attrib != {'errors': '0', 'missingClasses': '0'} or len(errors):
            raise EvidenceError('Java analysis has errors or unresolved classes')
        if (summary.get('total_classes') != '2' or summary.get('java_version') != '21.0.13' or
                summary.get('vm_version') != '21.0.13+9-1-deb13u2-Debian'):
            raise EvidenceError('Java analysis class coverage or runtime differs')
        diagnostics = []
        for bug in root.findall('BugInstance'):
            def primary(tag):
                rows = [r for r in bug.findall(tag) if r.get('primary') == 'true']
                if len(rows) != 1:
                    raise EvidenceError('Java finding has an ambiguous primary location')
                return rows[0]
            klass, method, line = primary('Class'), primary('Method'), primary('SourceLine')
            class_name, source_name = klass.attrib['classname'], line.attrib['sourcefile']
            start, end = int(line.attrib['start']), int(line.attrib['end'])
            offset, offset_end = int(line.attrib['startBytecode']), int(line.attrib['endBytecode'])
            if (class_name != 'OwnedUnsafe' or method.get('classname') != class_name or
                    line.get('classname') != class_name or source_name != class_name + '.java' or
                    line.get('sourcepath') != source_name or line.get('relSourcepath') != source_name or
                    method.get('isStatic') != 'true' or start != end or offset != offset_end or
                    not 1 <= start <= len(cases['sources'][source_name].splitlines())):
                raise EvidenceError('Java finding source or bytecode span differs')
            method_name = method.attrib['name']
            signature = {'nullLength': '()I', 'lookup': '(Ljava/sql/Connection;Ljava/lang/String;)Z'}
            if method.get('signature') != signature.get(method_name):
                raise EvidenceError('Java method signature differs')
            expression = cases['sources'][source_name].splitlines()[start - 1].strip()
            expected_expression = {
                'nullLength': 'return missing.length();',
                'lookup': 'return statement.execute("SELECT id FROM accounts WHERE name = \'" + name + "\'");',
            }
            if expression != expected_expression.get(method_name):
                raise EvidenceError('Java finding does not identify the owned unsafe expression')
            diagnostics.append({'type': bug.attrib['type'], 'priority': int(bug.attrib['priority']),
                                'rank': int(bug.attrib['rank']), 'category': bug.attrib['category'],
                                'cwe': int(bug.attrib['cweid']), 'class': class_name,
                                'method': method_name, 'file': source_name, 'line': start,
                                'bytecode_offset': offset})
        diagnostics.sort(key=lambda row: row['type'])
        if diagnostics != expected_findings(plugin) or int(summary.attrib['total_bugs']) != len(diagnostics):
            raise EvidenceError('Java native positive or clean control disagrees')
        stats = summary.findall('.//ClassStats')
        expected_stats = [('OwnedSafe', 'OwnedSafe.java', 0), ('OwnedUnsafe', 'OwnedUnsafe.java', len(diagnostics))]
        observed_stats = sorted((r.attrib['class'], r.attrib['sourceFile'], int(r.attrib['bugs'])) for r in stats)
        if observed_stats != expected_stats:
            raise EvidenceError('Java clean class was not analyzed or has unexpected findings')
    except (ElementTree.ParseError, KeyError, TypeError, ValueError) as exc:
        raise EvidenceError('malformed native Java analysis evidence') from exc
    return {'version': '4.10.5', 'findsecbugs_enabled': plugin,
            'classes_analyzed': ['OwnedSafe', 'OwnedUnsafe'], 'clean_class_findings': 0,
            'analysis_errors': 0, 'missing_classes': 0, 'diagnostics': diagnostics}


def witness_result(raw):
    try:
        result = strict_json(raw)
    except (ValueError, TypeError) as exc:
        raise EvidenceError('malformed owned Java witness') from exc
    expected = {'unsafe_null_throws': True, 'safe_length': 4, 'unsafe_sql_inlines_input': True,
                'safe_sql_uses_placeholder': True, 'safe_bound_parameter_matches': True,
                'database_connections_opened': 0}
    # Canonical bytes keep booleans and integers distinct.
    if canonical(result) != canonical(expected):
        raise EvidenceError('owned Java witness contradicts the analyzer controls')
    return result


def plugin_difference(baseline, enhanced):
    before = {r['type']: r for r in baseline['diagnostics']}
    after = {r['type']: r for r in enhanced['diagnostics']}
    if (any(after.get(kind) != row for kind, row in before.items()) or
            set(after) - set(before) != {'SQL_INJECTION_JDBC'}):
        raise EvidenceError('FindSecBugs contribution is not an isolated native detector result')
    return {'added_detector': 'SQL_INJECTION_JDBC', 'cwe': 89,
            'baseline_diagnostics_preserved': True, 'corrected_class_findings': 0}


def run(kit):
    """Compile fixed owned Java, analyze it with both producers and execute its local witness."""
    pins, cases = inputs()
    kit = Path(kit)
    with tempfile.TemporaryDirectory(prefix='nqc-java-native-') as tmp:
        work = Path(tmp)
        for name, pin in pins['files'].items():
            (work/name).parent.mkdir(parents=True, exist_ok=True)
            copy_release(name, kit/name, work/name, pin['sha256'], limit=pin['bytes'],
                         executable=pin['executable'])
        (work/'src').mkdir()
        (work/'classes').mkdir()
        for name, source in cases['sources'].items():
            (work/'src'/name).write_text(source)
        env = {'HOME': tmp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TMPDIR': tmp}
        command = [*ISOLATE, str(work/'runtime/bin/java'), '-Xshare:off', '-Xmx512m',
                   '-Duser.language=en', '-Duser.country=US', '-Duser.timezone=UTC']

        def execute(args):
            process = subprocess.run([*command, *args], cwd=work, env=env,
                                     stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=90)
            if process.stderr or len(process.stdout) > MAX_BYTES:
                raise EvidenceError('Java producer emitted unexpected diagnostics or oversized output')
            return process.stdout

        output = execute(['-m', 'jdk.compiler/com.sun.tools.javac.Main', '-g', '-d', 'classes',
                          *('src/' + name for name in sorted(cases['sources']))])
        classes = {p.name: sha(p.read_bytes()) for p in sorted((work/'classes').glob('*.class'))}
        if output or classes != pins['owned_classes']:
            raise EvidenceError('owned Java compilation differs from pinned source and compiler')
        witness = witness_result(execute(['-cp', 'classes', 'OwnedWitness']))
        reports = {}
        for plugin in (False, True):
            name = 'with-plugin' if plugin else 'baseline'
            args = ['-cp', 'lib/*', 'edu.umd.cs.findbugs.LaunchAppropriateUI', '-textui',
                    '-effort:max', '-low', '-xml:withMessages', '-auxclasspath', 'classes', '-sourcepath', 'src']
            if plugin:
                args += ['-pluginList', str(work/'plugin/findsecbugs-plugin-1.14.0.jar')]
            args += ['-output', name + '.xml', 'classes/OwnedUnsafe.class', 'classes/OwnedSafe.class']
            if execute(args):
                raise EvidenceError('Java analyzer emitted unexpected standard output')
            raw = read_artifact(work, name + '.xml')
            reports[name] = analysis_report(raw, plugin, cases, str(work/'src'))
        sections = {'spotbugs': reports['baseline'], 'spotbugs_with_findsecbugs': reports['with-plugin'],
                    'findsecbugs_contribution': plugin_difference(reports['baseline'], reports['with-plugin']),
                    'compiled_class_sha256': classes, 'owned_execution_witness': witness}
    return {'schema_version': 1, 'query': 'java-native', 'producers': pins['sources'],
            'pins_sha256': PINS_SHA, 'cases_sha256': pins['cases_sha256'],
            'sections': sections, 'sections_sha256': sha(canonical(sections)),
            'scope': {'owned_fixed_sources_only': True, 'network_namespace': 'isolated',
                      'detectors': 'Unmodified native detectors; maximum effort and all confidence levels.',
                      'real_databases_accessed': 0, 'original_vulnerabilities_confirmed': 0,
                      'limitation': 'Owned positive and corrected controls demonstrate this data flow only; '
                                    'they do not measure general Java analysis precision or prove arbitrary code safe.'}}
