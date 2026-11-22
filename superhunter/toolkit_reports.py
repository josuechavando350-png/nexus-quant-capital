"""Summarize existing tool output. Keep imported evidence separate from local runs."""
from collections import Counter
from pathlib import Path
import re
from xml.etree import ElementTree

from .safe_io import read_artifact, strict_json

FORMATS = ('slither', 'slitherin', 'aderyn', 'semgrep', 'echidna', 'ityfuzz',
           'halmos', 'kontrol', 'manticore', 'mythril', 'nuclei')


def count_labels(items, field):
    if not isinstance(items, list):
        raise ValueError('expected list of records')
    counts = Counter()
    for item in items:
        value = item[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError('invalid result label')
        counts[value] += 1
    return dict(sorted(counts.items()))


def coverage_count(record, covered, total):
    hits, size = record[covered], record[total]
    if type(hits) is not int or type(size) is not int or not 0 <= hits <= size:
        raise ValueError('invalid coverage counters')
    return hits, size


def summarize(name, raw):
    if name == 'kontrol':
        text = raw.decode()
        if '<!DOCTYPE' in text or '<!ENTITY' in text:
            raise ValueError('document declarations are unsupported')
        root = ElementTree.fromstring(text)
        if root.tag not in ('testsuite', 'testsuites'):
            raise ValueError('expected JUnit testsuites')
        cases = root.findall('.//testcase')
        if not cases:
            raise ValueError('empty JUnit report')
        outcomes = Counter()
        for case in cases:
            status = next((key for key in ('error', 'failure', 'skipped') if case.find(key) is not None), 'passed')
            outcomes[status] += 1
        return {'test_outcomes': dict(outcomes)}
    if name == 'manticore':
        lines = raw.decode().splitlines()
        if not lines or lines[0] != 'Global runtime coverage:':
            raise ValueError('expected Manticore global.summary')
        percentages = []
        for line in lines[1:]:
            if line.startswith('Known for '):
                break
            match = re.fullmatch(r'[0-9a-fA-F]+:\s*(\d+(?:\.\d+)?)%', line)
            if not match or not 0 <= float(match[1]) <= 100:
                raise ValueError('invalid Manticore coverage row')
            percentages.append(float(match[1]))
        return {'contract_coverage_percent': percentages}
    if name == 'nuclei':
        rows = [strict_json(line) for line in raw.splitlines() if line.strip()]
        counts = Counter()
        for row in rows:
            if not isinstance(row['template-id'], str) or type(row['matcher-status']) is not bool:
                raise ValueError('invalid Nuclei event')
            if row['matcher-status']:
                counts.update(count_labels([row['info']], 'severity'))
        return {'events': len(rows), 'matched_by_severity': dict(counts)}

    data = strict_json(raw)
    if name in ('slither', 'slitherin', 'mythril'):
        if data['success'] is not True:
            raise ValueError('producer reported a failed analysis')
        if name == 'mythril':
            return {'issues_by_severity': count_labels(data['issues'], 'severity')}
        rows = data['results'].get('detectors', [])
        counts = count_labels(rows, 'check')
        if name == 'slitherin':
            counts = {key: count for key, count in counts.items() if key.startswith('pess-')}
        return {'detectors': counts}
    if name == 'semgrep':
        return {'checks': count_labels(data['results'], 'check_id'), 'errors': len(data['errors'])}
    if name == 'aderyn':
        return {level: count_labels(data[level + '_issues']['issues'], 'detector_name') for level in ('high', 'low')}
    if name == 'echidna':
        return {'test_statuses': count_labels(data['tests'], 'status'), 'success': data['success']}
    if name == 'halmos':
        counts = Counter()
        for group in data['test_results'].values():
            for case in group:
                code = case['exitcode']
                if type(code) is not int or not 0 <= code <= 5:
                    raise ValueError('unknown Halmos exit code')
                counts[('pass', 'counterexample', 'timeout', 'stuck', 'revert_all', 'exception')[code]] += 1
        return {'test_outcomes': dict(counts)}
    if name == 'ityfuzz':
        records = data['coverage'].values()
        instructions = [coverage_count(row, 'instruction_coverage', 'total_instructions') for row in records]
        branches = [coverage_count(row, 'branch_coverage', 'total_branches') for row in records]
        return {'contracts': len(instructions),
                'instructions': {'covered': sum(a for a, b in instructions), 'total': sum(b for a, b in instructions)},
                'branches': {'covered': sum(a for a, b in branches), 'total': sum(b for a, b in branches)}}
    raise ValueError('unsupported report format')


def read_reports(pairs):
    output = {}
    for name, path in pairs:
        if name not in FORMATS or name in output:
            raise ValueError('unknown or duplicate report producer: ' + name)
        source = Path(path)
        try:
            output[name] = summarize(name, read_artifact(source.parent, source.name))
        except (KeyError, AttributeError, TypeError, ValueError, ElementTree.ParseError) as exc:
            raise ValueError('invalid ' + name + ' report: ' + str(exc)) from exc
    return output
