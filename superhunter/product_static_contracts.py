"""Check whether a selected static interface can supply the actual NQC evidence-reader call."""
import ast
import inspect
import sys
from pathlib import Path
import re
import tempfile
from types import UnionType
from typing import get_args, get_origin, get_type_hints
from zipfile import ZipFile
from io import BytesIO

from . import safe_io
from .product_census_header import FIXTURE, FIXTURE_SHA, pinned
from .product_formats_batch import selected
from .product_languages_batch import run, write_files
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .safe_io import canonical, strict_json

CPG, PYSA, INFER = 'Fraunhofer-AISEC/cpg', 'meta/Pysa', 'meta/infer'
FRONT = 'cpg-language-python/src/main/kotlin/de/fraunhofer/aisec/cpg/frontends/python/'
LOADER = 'tools/generate_taint_models/module_loader.py'
NULLS = 'infer/annotations/src/main/java/com/facebook/infer/annotation/Assertions.java'
JSR = 'dependencies/java/jsr-305/jsr305-src.jar'
MODEL = 'infer/src/bufferoverrun/bufferOverrunModels.ml'
PROJECTS = {
    CPG: ('022-cpg', '8a4bd21ec8591b1bc92ca6174a01ab5159514e09', [FRONT+'Python.kt', FRONT+'DeclarationHandler.kt']),
    PYSA: ('023-pysa', '50ba6ccf2612131033662e0a6bc5e8acffc6ff36', [LOADER]),
    INFER: ('101-infer', '2ebceff7ce3c93480bbc0e8d09d11aeec53595d8', [NULLS, JSR, MODEL]),
}
OWNED = 'superhunter/safe_io.py'
OWNED_SHA = '742bb873c69e2793fa62afa34983efd2ef10066ae525b7a70542407db61c509a'
BASE = 'def read_artifact(root: Path, relative: str) -> bytes: ...\n'
STUBS = {'source': None, 'same_interface': BASE,
         'positional_only': BASE.replace('relative: str)', 'relative: str, /)'),
         'keyword_only': BASE.replace('relative: str', '*, relative: str'),
         'narrowed_input': BASE.replace('relative: str', 'relative: bytes'),
         'nullable_result': BASE.replace(' -> bytes', ' -> bytes | None'),
         'untyped_parameter': BASE.replace('relative: str', 'relative'),
         'renamed_parameter': BASE.replace('relative: str', 'other: str'),
         'missing_parameter': BASE.replace(', relative: str', ''),
         'broken_stub': BASE.replace(') ->', ' ->')}

PY_WORKER = """import ast, json, sys
from pathlib import Path
sys.path.insert(0, '.')
from module_loader import find_all_paths, load_module
schema = json.load(sys.stdin)
out = {}
for folder in sorted(Path('cases').iterdir()):
    selected, = find_all_paths(str(folder))
    tree = load_module(selected)
    result = {'selected': Path(selected).name, 'parsed': tree is not None}
    if tree is not None:
        fn, = [f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == 'read_artifact']
        parameters = []
        for field, mode in schema:
            for arg in getattr(fn.args, field):
                parameters.append([arg.arg, mode, ast.unparse(arg.annotation) if arg.annotation else None])
        result.update(parameters=parameters, returns=ast.unparse(fn.returns))
    out[folder.name] = result
print(json.dumps(out))
"""
JAVA = """import java.util.*;
import java.io.*;
import com.facebook.infer.annotation.Assertions;
class Contract {
    public static void main(String[] args) throws Exception {
        var reader = new BufferedReader(new InputStreamReader(System.in));
        for (String row; (row=reader.readLine())!=null; ) {
            var fields=row.split("\\t", -1); var actual=new HashMap<String,String>();
            for (int i=2;i<fields.length;i++) {
                var slot=fields[i].split(":", -1);
                actual.put(slot[0],slot[1].equals("-") ? null : slot[1]);
            }
            String decision;
            try {
                var root=Assertions.assertGet("root", actual);
                var relative=Assertions.assertGet("relative", actual);
                if (!root.equals("Path") || !relative.equals("str")) decision="incompatible argument type";
                else {
                    String witnessedNull=fields[1].contains("None") ? null : fields[1];
                    Assertions.assertNotNull(witnessedNull,"nullable output");
                    decision="typed witness admitted";
                }
            } catch (AssertionError e) { decision=e.getMessage(); }
            System.out.println(fields[0]+"="+decision);
        }
    }
}
"""


def cpg_fields(files):
    types = files[FRONT+'Python.kt'].decode()
    shape = re.search(r'class arguments\(pyObject: PyObject\).*?\n        }', types, re.S)
    if shape is None:
        raise EvidenceError('missing CPG argument record')
    slots = re.findall(r'val (\w+): kotlin\.collections\.List<arg> by lazy \{ "(\w+)" of pyObject }', shape[0])
    if any(name != prop for name, prop in slots):
        raise EvidenceError('CPG parameter mapping is not identity-preserving')
    handler = files[FRONT+'DeclarationHandler.kt'].decode()
    positional = re.search(r'var positionalArguments = args\.(\w+) \+ args\.(\w+)', handler)
    keyword = re.search(r'for \(idx in args\.(\w+)\.indices\) \{\s*val arg = args\.\1\[idx\]', handler)
    if positional is None or keyword is None:
        raise EvidenceError('CPG argument classification missing')
    fields = [[positional[1], 'positional-only'], [positional[2], 'positional-or-keyword'],
              [keyword[1], 'keyword-only']]
    if {name for name, _ in fields} != {name for name, _ in slots}:
        raise EvidenceError('CPG handler and frontend type disagree')
    return fields


def oracle(source, text, actual):
    # Independently reconstruct only the callable signature. No callable body is evaluated.
    try:
        module = ast.parse(text or source)
    except SyntaxError:
        return {'binds': False, 'accepts_types': False, 'infer': None}
    fn, = [n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'read_artifact']
    fn.decorator_list = []
    fn.body = [ast.copy_location(ast.Pass(), fn)]
    scope = {'Path': Path}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<sealed-signature>', 'exec', dont_inherit=True), scope)
    target = scope['read_artifact']
    try:
        inspect.signature(target).bind(*actual)
        binds = True
    except TypeError:
        binds = False
    hints = get_type_hints(target)
    names = list(inspect.signature(target).parameters)
    if len(names) < len(actual):
        decision = 'Key not found'
    elif not all(k in hints for k in names):
        decision = 'Null value'
    elif not all(isinstance(v, hints[k]) for v,k in zip(actual, names)):
        decision = 'incompatible argument type'
    else:
        result = hints['return']
        possible = get_args(result) if get_origin(result) is UnionType else (result,)
        decision = 'typed witness admitted' if all(issubclass(t, (bytes,str)) for t in possible) else 'nullable output'
    return {'binds': binds, 'accepts_types': decision == 'typed witness admitted', 'infer': decision}


def java_guard(work, files, interfaces):
    model = files[MODEL].decode()
    if not (re.search(r'&:: "assertGet" <>\$ capt_exp \$\+ capt_exp \$--> InferAnnotation\.assert_get', model)
            and re.search(r'&:: "assertNotNull".*?\$--> id', model)):
        raise EvidenceError('unreviewed Infer model binding')
    # Compile authenticated sources, including the annotation API. No vendor jar is executed.
    classes = work/'classes'
    classes.mkdir()
    (work/'Assertions.java').write_bytes(files[NULLS])
    (work/'Contract.java').write_text(JAVA)
    with ZipFile(BytesIO(files[JSR])) as archive:
        annotations = [n for n in archive.namelist() if re.fullmatch(r'javax/annotation/(?:meta/)?\w+\.java', n)]
        write_files(work, {name: archive.read(name) for name in annotations})
    run(work, ['/usr/bin/java', '-Xmx160m', 'com.sun.tools.javac.Main', '-proc:none', '-d', 'classes',
               '-sourcepath', '.', 'Assertions.java', 'Contract.java'])
    records = []
    for name, data in interfaces.items():
        if data['parsed']:
            # The real caller uses positional arguments. A formal rename preserves that contract.
            slots = [origin + ':' + (parameter[2] or '-') for origin, parameter in
                     zip(('root','relative'), data['parameters'])]
            records.append('\t'.join([name, data['returns'], *slots]))
    result = run(work, ['/usr/bin/java','-Xmx64m','-cp','classes','Contract'], ('\n'.join(records)+'\n').encode())
    return dict(row.split('=',1) for row in result.decode().splitlines())


def review(source_root: Path):
    blobs, manifests = {}, {}
    for name,(directory,revision,files) in PROJECTS.items():
        repo = source_root/directory
        if repo.is_symlink() or git(repo,'rev-parse','HEAD').decode().strip() != revision:
            raise EvidenceError('unreviewed source for ' + name)
        blobs[name], manifests[name] = selected(repo, revision, files.__contains__)
        if set(blobs[name]) != set(files):
            raise EvidenceError('incomplete upstream static contract')
    raw = pinned(ROOT, OWNED, OWNED_SHA)
    source = raw.decode()
    fn, = [f for f in ast.parse(source).body if isinstance(f, ast.FunctionDef) and f.name == 'read_json']
    call, = [s for s in fn.body if isinstance(s, ast.Return)]
    if ast.unparse(call.value) != 'strict_json(read_artifact(path.parent, path.name))':
        raise EvidenceError('owned reader call site differs')
    actual_path = ROOT/FIXTURE
    if safe_io.read_json(actual_path) != strict_json(pinned(ROOT,FIXTURE,FIXTURE_SHA)):
        raise EvidenceError('owned typed reader stimulus differs')
    try:
        safe_io.strict_json(None)
    except TypeError:
        pass
    else:
        raise EvidenceError('actual downstream reader accepted null')
    groups = cpg_fields(blobs[CPG])
    with tempfile.TemporaryDirectory(prefix='nqc-static-contracts-') as folder:
        work = Path(folder)
        (work/'module_loader.py').write_bytes(blobs[PYSA][LOADER])
        for label,stub in STUBS.items():
            base = work/'cases'/label
            base.mkdir(parents=True)
            (base/'safe_io.py').write_bytes(raw)
            if stub is not None:
                (base/'safe_io.pyi').write_text(stub)
        interfaces = strict_json(run(work,[sys.executable,'-B','-I','-S','-c',PY_WORKER],canonical(groups)))
        inferred = java_guard(work,blobs[INFER],interfaces)
    if set(interfaces) != set(STUBS):
        raise EvidenceError('incomplete AST review')
    decisions = {}
    for label,stub in STUBS.items():
        iface = interfaces[label]
        if iface['selected'] != ('safe_io.py' if stub is None else 'safe_io.pyi'):
            raise EvidenceError('Pysa source/stub resolution changed')
        oracle_result = oracle(source,stub,(actual_path.parent,actual_path.name))
        binds = iface['parsed'] and len([p for p in iface['parameters'] if p[1] != 'keyword-only']) == 2
        if binds != oracle_result['binds'] or inferred.get(label) != oracle_result['infer']:
            raise EvidenceError('reader contract differs from independent runtime binding or type witnesses')
        decisions[label] = {'selected':iface['selected'],'positional_call_binds':binds,
                            'type_diagnostic':inferred.get(label),'accepted':binds and inferred.get(label)=='typed witness admitted'}
    if {label for label,r in decisions.items() if r['accepted']} != {'source','same_interface','positional_only','renamed_parameter'}:
        raise EvidenceError('static reader contract accepted a changed interface')
    results = {PYSA: ('execution','resolve_and_parse_evidence_reader_interfaces',{'interfaces':interfaces}),
               CPG: ('reference','bind_owned_call_to_parameter_modes',{'fields':groups,'interfaces_sha256':sha(canonical(interfaces)),
                     'positional_binding':{n:r['positional_call_binds'] for n,r in decisions.items()}}),
               INFER: ('execution','enforce_required_typed_evidence_arguments',{'decisions':decisions,
                       'source_sha256':sha(raw),'stimulus_sha256':FIXTURE_SHA,'null_rejected_by_consumer':True,
                       'upstream_scope':'nullability assertion library and model binding'})}
    return {name:{'revision':PROJECTS[name][1],'role':role,'operation':operation,
                  'source_manifest_sha256':manifests[name],'result':result}
            for name,(role,operation,result) in results.items()}
