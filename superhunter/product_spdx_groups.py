"""Compare Dependency-Track SPDX expression semantics on real NQC license observations."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

from .product_reasoning import EvidenceError
from .product_review import copy_release, sha

DIGEST = '86e9d252952f94c173c3c5e5283e09d4220d9b3d7577f57a641770272b8ebaf9'
JAVA = """import java.io.*;
import java.util.*;
import org.dependencytrack.parser.spdx.expression.SpdxExpressionParser;
import org.dependencytrack.parser.spdx.expression.model.SpdxExpression;

class CheckLicenses {
    static void visit(SpdxExpression expression, List<String> stack) {
        if (expression == SpdxExpression.INVALID) throw new IllegalArgumentException("invalid expression");
        var op = expression.getOperation();
        if (op == null) {
            stack.add(Objects.requireNonNull(expression.getSpdxLicenseId()));
        } else {
            for (var child : op.getArguments()) visit(child, stack);
            stack.add(op.getOperator().name());
        }
    }
    public static void main(String[] args) throws Exception {
        var input = new BufferedReader(new InputStreamReader(System.in));
        for (String line; (line = input.readLine()) != null;) {
            var stack = new ArrayList<String>();
            visit(SpdxExpressionParser.getInstance().parse(line), stack);
            System.out.println(String.join(" ", stack));
        }
    }
}
"""
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9.:-]*|[()]')


def semantics(expression, postfix):
    tokens = TOKEN.findall(expression)
    if ''.join(tokens) != ''.join(expression.split()):
        raise EvidenceError('unsupported SPDX expression in the verified inventory')
    names = sorted(set(tokens) - {'AND', 'OR', '(', ')'})
    if not 1 <= len(names) <= 12:
        raise EvidenceError('unsupported SPDX expression size')
    assignments = 1 << len(names)
    values = {name: sum(1 << case for case in range(assignments) if case & (1 << i)) for i, name in enumerate(names)}
    native = []
    for token in postfix.split():
        if token in values:
            native.append(values[token])
        elif token in ('AND', 'OR') and len(native) >= 2:
            right, left = native.pop(), native.pop()
            native.append(left & right if token == 'AND' else left | right)
        else:
            raise EvidenceError('unexpected Dependency-Track expression token')
    if set(names) != set(postfix.split()) - {'AND', 'OR'}:
        raise EvidenceError('Dependency-Track changed the license identifiers')
    aliases = {name: f'l{i}' for i, name in enumerate(names)}
    python = ' '.join(aliases.get(t, t.lower()) for t in tokens)
    def evaluate(node):
        if isinstance(node, ast.Name):
            return values[names[int(node.id[1:])]]
        if isinstance(node, ast.BoolOp):
            bits = evaluate(node.values[0])
            for part in node.values[1:]:
                bits = bits & evaluate(part) if isinstance(node.op, ast.And) else bits | evaluate(part)
            return bits
        raise EvidenceError('invalid SPDX alternative or conjunction')
    try:
        truth = evaluate(ast.parse(python, mode='eval').body)
    except SyntaxError as exc:
        raise EvidenceError('unsupported SPDX expression syntax') from exc
    if native != [truth]:
        raise EvidenceError('Dependency-Track and independent evaluator disagree')
    return {'identifiers': names, 'assignments_checked': assignments,
            'truth_table_sha256': sha(truth.to_bytes((assignments + 7) // 8, 'little'))}


def build(release, scanned, cargo):
    sources = {name: row['detected_expression'] for name, row in scanned['notices'].items()}
    for pkg in cargo['packages']:
        key = f"pkg:cargo/{pkg['name']}@{pkg['version']}"
        original = pkg['declared_expression']
        sources[key] = original.replace('/', ' OR ') if original else None
    expressions = sorted({s for s in sources.values() if s})
    if not expressions:
        raise EvidenceError('missing SPDX expressions for Dependency-Track')
    with tempfile.TemporaryDirectory(prefix='nqc-spdx-groups-') as temp:
        work = Path(temp)
        jar = work/'distribution.jar'
        copy_release('Dependency-Track', release, jar, DIGEST, executable=False)
        with zipfile.ZipFile(jar) as archive:
            root = 'org/dependencytrack/parser/spdx/expression/'
            for suffix in ('SpdxExpressionParser', 'model/SpdxExpression', 'model/SpdxExpressionOperation', 'model/SpdxOperator'):
                path = root + suffix + '.class'
                dest = work/path
                dest.parent.mkdir(exist_ok=True, parents=True)
                dest.write_bytes(archive.read('WEB-INF/classes/' + path))
            raw_groups = archive.read('WEB-INF/classes/default-objects/licenseGroups.json')
        groups = json.loads(raw_groups)
        (work/'CheckLicenses.java').write_text(JAVA)
        result = subprocess.run(['/usr/bin/unshare', '--user', '--map-current-user', '--net', '/usr/bin/java',
                                 '--class-path', str(work), 'CheckLicenses.java'], cwd=work, check=True,
                                input='\n'.join(expressions) + '\n', capture_output=True, text=True, timeout=60,
                                env={'HOME': temp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C.UTF-8'})
    trees = result.stdout.splitlines()
    if len(trees) != len(expressions):
        raise EvidenceError('incomplete Dependency-Track expression inventory')
    parsed = {expr: semantics(expr, tree) for expr, tree in zip(expressions, trees, strict=True)}
    ids = sorted({term for row in parsed.values() for term in row['identifiers']})
    return {'version': '4.14.7', 'jar_sha256': DIGEST, 'groups_sha256': sha(raw_groups),
            'sources': dict(sorted(sources.items())), 'expressions': parsed, 'groups_by_id': {
                term: sorted(g['name'] for g in groups if term in g['licenses']) for term in ids}}
