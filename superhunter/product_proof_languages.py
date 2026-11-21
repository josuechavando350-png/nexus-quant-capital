"""Emit only closed license obligations built from bounded Boolean trees and generated variable names."""


def render(node, operators, values, false='false', *, prefix=False):
    if node is None:
        return false
    if isinstance(node, int):
        return values[node]
    kind, left, right = node
    op = operators[0 if kind == 'and' else 1]
    a = render(left, operators, values, false, prefix=prefix)
    b = render(right, operators, values, false, prefix=prefix)
    return f'({op} {a} {b})' if prefix else f'({a} {op} {b})'


def expressions(c, names, false='false', operators=('&&', '||'), prefix=False):
    return [render(c[k], operators, names, false, prefix=prefix) for k in ('original', 'candidate')]


def c_program(tool, claims):
    variables = max(len(c['names']) for c in claims)
    init = [f'  _Bool p{i} = __VERIFIER_nondet_bool();' for i in range(variables)]
    rows = []
    for i, c in enumerate(claims):
        a, b = expressions(c, [f'p{j}' for j in range(len(c['names']))], '0')
        if tool == 'cbmc':
            rows.append(f'  __CPROVER_assert({a} == {b}, "nqc_{i}");')
        elif tool == 'esbmc':
            rows.append(f'  assert({a} == {b});')
        else:
            rows.append(f'  if ({a} != {b}) __VERIFIER_error();')
    header = '#include <assert.h>' if tool == 'esbmc' else 'extern void __VERIFIER_error(void);'
    return '\n'.join([header, 'extern _Bool __VERIFIER_nondet_bool(void);', 'int main(void) {', *init,
                     *rows, '  return 0;', '}', ''])


def rocq_program(claims):
    rows = ['Inductive bit : Type := yes : bit | no : bit.',
            'Definition both (a b:bit) := match a with yes => b | no => no end.',
            'Definition either (a b:bit) := match a with yes => yes | no => b end.',
            'Inductive Same (x:bit) : forall (_ : bit), Prop := same : Same x x.']
    for i, c in enumerate(claims):
        for mask in range(1 << len(c['names'])):
            values = ['yes' if mask & (1 << j) else 'no' for j in range(len(c['names']))]
            a, b = expressions(c, values, 'no', ('both', 'either'), prefix=True)
            rows.append(f'Definition claim_{i}_{mask} : Same {a} {b} := same {a}.')
    return '\n'.join(rows) + '\n'


def program(tool, claims):
    if tool == 'alive2':
        return alive_program(claims)
    if tool == 'klee':
        return klee_program(claims)
    if tool in ('cbmc', 'esbmc', 'seahorn'):
        return 'claims.c', c_program(tool, claims)
    if tool == 'rocq':
        return 'Nqc.v', rocq_program(claims)
    rows = []
    for i, c in enumerate(claims):
        names = [f'p{j}' for j in range(len(c['names']))]
        a, b = expressions(c, names, 'False' if tool == 'saw' else 'false')
        params = ', '.join(n + ': bool' for n in names)
        if tool == 'dafny':
            rows.append(f'lemma Claim{i}({params}) ensures {a} == {b} {{}}')
        elif tool == 'fstar':
            args = ' '.join(f'({n}:bool)' for n in names)
            rows.append(f'let claim{i} {args} : Lemma ({a} == {b}) = ()')
        elif tool == 'saw':
            args = ' '.join(f'({n} : Bit)' for n in names)
            rows.append('prove_print abc {{ ' + chr(92) + args + ' -> ' + a + ' == ' + b + ' }};')
            rows.append(f'print "nqc_{i}_proved";')
        elif tool == 'verifast':
            params = ', '.join('int ' + n for n in names)
            a, b = expressions(c, [f'({n} != 0)' for n in names], '(0 != 0)')
            rows.append(f'void claim{i}({params})\n//@ requires true;\n//@ ensures true;\n{{\n  //@ assert {a} == {b};\n}}')
        elif tool == 'verus':
            rows.append(f'proof fn claim{i}({params}) ensures {a} == {b} {{}}')
        elif tool == 'kani':
            init = ' '.join(f'let {n}:bool = kani::any();' for n in names)
            rows.append(f'#[kani::proof] fn claim{i}() {{ {init} assert!({a} == {b}); }}')
        else:
            raise ValueError('unknown license proof language')
    body = '\n'.join(rows) + '\n'
    if tool == 'verus':
        return 'claims.rs', 'use vstd::prelude::*;\nverus! {\n' + body + '}\nfn main(){}\n'
    if tool == 'fstar':
        return 'Nqc.fst', 'module Nqc\n' + body
    suffix = {'dafny': 'dfy', 'saw': 'saw', 'verifast': 'c', 'kani': 'rs'}
    return 'claims.' + suffix[tool], body


def ir_value(node, lines, names):
    if node is None:
        return '0'
    if isinstance(node, int):
        return names[node]
    op, left, right = node
    a = ir_value(left, lines, names)
    b = ir_value(right, lines, names)
    dest = f'%t{len(lines)}'
    lines.append(f'  {dest} = {op} i1 {a}, {b}')
    return dest


def alive_program(claims):
    def body(node, names):
        lines = [f'  %input{i} = or i1 {name}, 0' for i, name in enumerate(names)]
        value = ir_value(node, lines, names)
        return [*lines, f'  %r = or i1 {value}, 0']
    lines = []
    for i, claim in enumerate(claims):
        names = [f'%p{j}' for j in range(len(claim['names']))]
        a, b = (body(claim[key], names) for key in ('original', 'candidate'))
        for direction, left, right in [('forward', a, b), ('reverse', b, a)]:
            lines.extend([f'Name: nqc_{i}_{direction}', *left, '  =>', *right, ''])
    return 'licenses.opt', '\n'.join(lines)


def klee_program(claims):
    lines = ['target triple = "x86_64-unknown-linux-gnu"',
             'declare void @klee_make_symbolic(ptr, i64, ptr)',
             'declare void @klee_report_error(ptr, i32, ptr, ptr)',
             '@file = constant [4 x i8] c"nqc\\00"',
             '@message = constant [19 x i8] c"NQC license choice\\00"',
             '@suffix = constant [8 x i8] c"nqc.err\\00"']
    names = [f'%p{i}' for i in range(max(len(c['names']) for c in claims))]
    for i, _ in enumerate(names):
        label = f'identifier_{i}'
        lines.append(f'@id{i} = constant [{len(label)+1} x i8] c"{label}\\00"')
    lines.extend(['define i32 @main() {', 'entry:'])
    for i, name in enumerate(names):
        lines.extend([f'  %v{i} = alloca i8', f'  call void @klee_make_symbolic(ptr %v{i}, i64 1, ptr @id{i})',
                      f'  %raw{i} = load i8, ptr %v{i}', f'  {name} = trunc i8 %raw{i} to i1'])
    previous = '1'
    for i, c in enumerate(claims):
        a, b = (ir_value(c[key], lines, names) for key in ('original', 'candidate'))
        lines.extend([f'  %equal{i} = icmp eq i1 {a}, {b}', f'  %all{i} = and i1 {previous}, %equal{i}'])
        previous = f'%all{i}'
    lines.extend([f'  br i1 {previous}, label %accepted, label %missing',
                  'accepted:', '  ret i32 0', 'missing:',
                  '  call void @klee_report_error(ptr @file, i32 1, ptr @message, ptr @suffix)',
                  '  unreachable', '}', ''])
    return 'licenses.ll', '\n'.join(lines)
