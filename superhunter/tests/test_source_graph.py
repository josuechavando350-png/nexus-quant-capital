"""Import-syntax analysis tests: harmless sources, never import target code."""
from copy import deepcopy
from pathlib import Path
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from superhunter import source_graph as sg
from superhunter.safe_io import canonical, strict_json


class SourceGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'checkout/superhunter'
        self.source.mkdir(parents=True)
        self.files = {'__init__.py':b'', '__main__.py':b'from . import logic\n',
                      'logic.py':b'from .store import VALUE\n', 'store.py':b'VALUE = 1\n'}
        self.out = self.root/'evidence'

    def graph(self):
        return sg.analyze(self.files)

    def write(self):
        for name, raw in self.files.items():
            path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

    def make(self):
        self.write()
        return sg.create_audit(self.out,root=self.source)

    def reseal(self,name,edit):
        value=strict_json((self.out/name).read_bytes());edit(value)
        raw=canonical(value);(self.out/name).write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][name]=sg.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def registry(self,depends):
        components={
            'entry':{'files':['__init__.py','__main__.py'],'tests':['test_entry.'],'depends':['logic']},
            'logic':{'files':['logic.py'],'tests':['test_logic.'],'depends':depends},
            'store':{'files':['store.py'],'tests':['test_store.'],'depends':[]},
            'quality':{'files':['quality.py'],'tests':['test_quality.'],'depends':[]}}
        self.files['quality.py']=('COMPONENTS = '+repr(components)+'\n').encode()

    def test_actual_imports_resolve_transitively(self):
        r=self.graph()
        self.assertEqual(r['status'],'SOURCE_GRAPH_INVENTORIED')
        self.assertEqual(r['syntactically_reachable'],['superhunter','superhunter.__main__','superhunter.logic','superhunter.store'])
        self.assertEqual(len(r['import_edges']),2)
        self.assertFalse(r['runtime_reachability_proven'])
        self.assertFalse(r['target_executed'])

    def test_strings_comments_do_not_create_edges(self):
        self.files['store.py']=b'# import missing\nx="from . import absent"\n'
        self.assertEqual(len(self.graph()['import_edges']),2)

    def test_source_code_is_not_executed(self):
        self.files['store.py']=b'raise RuntimeError("TARGET_MUST_NEVER_EXECUTE")\n'
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.make();sg.verify_audit(self.out)

    def test_relative_parent_import(self):
        self.files['nested/helper.py']=b'from .. import store\n'
        edge=next(e for e in self.graph()['import_edges'] if e['file']=='nested/helper.py')
        self.assertEqual(edge['target'],'superhunter.store')

    def test_relative_package_initializer(self):
        self.files['nested/__init__.py']=b'from .. import store\n'
        self.assertTrue(any(e['target']=='superhunter.store' and e['source']=='superhunter.nested' for e in self.graph()['import_edges']))

    def test_absolute_package_import(self):
        self.files['logic.py']=b'import superhunter.store as storage\n'
        self.assertTrue(any(e['target']=='superhunter.store' for e in self.graph()['import_edges']))

    def test_external_dependency_not_assumed_installed(self):
        self.files['logic.py']=b'import imaginary_library as il\n'
        self.assertEqual(self.graph()['external_imports'][0]['target'],'imaginary_library')
        self.assertNotIn('installed',self.graph()['external_imports'][0])

    def test_deferred_missing_module_explicit(self):
        self.files['logic.py']=b'def future():\n    from .missing import Thing\n'
        row=self.graph()['unresolved_imports'][0]
        self.assertEqual((row['phase'],row['reason']),('DEFERRED','MODULE_NOT_IN_SNAPSHOT'))

    def test_conditional_not_assumed_executed(self):
        self.files['logic.py']=b'if False:\n    from . import store\n'
        e=next(e for e in self.graph()['import_edges'] if e['file']=='logic.py')
        self.assertEqual(e['phase'],'CONDITIONAL')

    def test_function_in_conditional_remains_deferred(self):
        self.files['logic.py']=b'if True:\n    def later():\n        from . import store\n'
        self.assertEqual(next(e for e in self.graph()['import_edges'] if e['file']=='logic.py')['phase'],'DEFERRED')

    def test_async_function_import_is_deferred(self):
        self.files['logic.py']=b'async def later():\n    from . import store\n'
        self.assertEqual(next(e for e in self.graph()['import_edges'] if e['file']=='logic.py')['phase'],'DEFERRED')

    def test_dynamic_loader_flagged_not_resolved(self):
        self.files['logic.py']=b'import importlib\nimportlib.import_module(name)\n'
        self.assertEqual(len(self.graph()['dynamic_sites']),1)
        self.assertFalse(self.graph()['all_dependencies_resolved'])

    def test_exec_flagged_without_echoing_argument(self):
        self.files['logic.py']=b'exec("SECRET_MARKER")\n'
        r=self.graph()
        self.assertNotIn('SECRET_MARKER',json.dumps(r))
        self.assertEqual(r['dynamic_sites'][0]['call_syntax'],'exec')

    def test_decorator_dynamic_call_is_enclosing_phase(self):
        self.files['logic.py']=b'@eval(name)\ndef later():\n    pass\n'
        self.assertEqual(self.graph()['dynamic_sites'][0]['phase'],'MODULE')

    def test_wildcard_export_unknown(self):
        self.files['logic.py']=b'from .store import *\n'
        self.assertEqual(self.graph()['dynamic_sites'][0]['reason'],'WILDCARD_EXPORTS_NOT_RESOLVED')

    def test_cycle_detection(self):
        self.files['store.py']=b'from . import logic\n'
        self.assertEqual(self.graph()['module_phase_cycles'],[['superhunter.logic','superhunter.store']])

    def test_lazy_cycle_not_claimed_startup_cycle(self):
        self.files['store.py']=b'def f():\n    from . import logic\n'
        r=self.graph();self.assertEqual(r['module_phase_cycles'],[])
        self.assertEqual(r['all_phase_cycles'],[['superhunter.logic','superhunter.store']])

    def test_unreachable_module_not_called_dead_code(self):
        self.files['plugin.py']=b'VALUE=2\n'
        self.assertEqual(self.graph()['not_reached_by_static_imports'],['superhunter.plugin'])
        self.assertNotIn('dead_code',self.graph())

    def test_direct_component_dependency(self):
        self.registry(['store'])
        row=next(e for e in self.graph()['component_edges'] if e['source_component']=='logic')
        self.assertEqual(row['declared_relation'],'DIRECT')

    def test_missing_component_edge_reported(self):
        self.registry([])
        r=self.graph()
        self.assertEqual(r['undeclared_component_edges'],1)
        self.assertFalse(r['vulnerability_confirmed'])

    def test_transitive_component_not_falsely_missing(self):
        self.registry(['quality'])
        text=self.files['quality.py'].decode().replace("'depends': []}}", "'depends': ['store']}}")
        self.files['quality.py']=text.encode()
        row=next(e for e in self.graph()['component_edges'] if e['source_component']=='logic')
        self.assertEqual(row['declared_relation'],'TRANSITIVE')

    def test_registry_expression_never_evaluated(self):
        self.files['quality.py']=b'COMPONENTS = open("DO_NOT_OPEN")\n'
        with self.assertRaisesRegex(ValueError,'NOT_LITERAL'):self.graph()

    def test_invalid_syntax_fails_closed(self):
        self.files['logic.py']=b'def broken(\n'
        with self.assertRaisesRegex(ValueError,'PARSE_FAILED'):self.graph()

    def test_ambiguous_module_layout_rejected(self):
        self.files['logic/__init__.py']=b''
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):self.graph()

    def test_source_path_traversal_rejected(self):
        self.files['../oops.py']=b''
        with self.assertRaisesRegex(ValueError,'SOURCE_PATH'):self.graph()

    def test_relative_import_cannot_escape_package(self):
        self.files['logic.py']=b'from ..outside import name\n'
        self.assertEqual(self.graph()['unresolved_imports'][0]['reason'],'RELATIVE_IMPORT_ESCAPES_PACKAGE')

    def test_bundle_self_contained_and_originals_unchanged(self):
        result=self.make()
        import shutil
        self.assertEqual((self.source/'logic.py').read_bytes(),self.files['logic.py'])
        shutil.rmtree(self.source)
        self.assertEqual(sg.verify_audit(self.out),result)

    def test_capture_skips_tests_and_cache(self):
        self.write();(self.source/'tests').mkdir();(self.source/'tests/test_x.py').write_text('raise RuntimeError')
        self.assertEqual(sg.capture(self.source),self.files)

    def test_symlink_file_rejected(self):
        self.write();(self.source/'logic.py').unlink();(self.source/'logic.py').symlink_to(self.source/'store.py')
        with self.assertRaises((OSError,ValueError)):sg.capture(self.source)

    def test_symlink_directory_rejected(self):
        self.write();(self.source/'alias').symlink_to(self.source,target_is_directory=True)
        with self.assertRaises(ValueError):sg.capture(self.source)

    def test_existing_output_not_overwritten(self):
        self.make();before=(self.out/'COMPLETE.json').read_bytes()
        with self.assertRaises(ValueError):sg.create_audit(self.out,root=self.source)
        self.assertEqual(before,(self.out/'COMPLETE.json').read_bytes())

    def test_resealed_false_confirmation_rejected(self):
        self.make();self.reseal('graph.json',lambda v:v.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(ValueError,'RECOMPUTATION'):sg.verify_audit(self.out)

    def test_resealed_removed_edge_rejected(self):
        self.make();self.reseal('graph.json',lambda v:v['import_edges'].pop())
        with self.assertRaisesRegex(ValueError,'RECOMPUTATION'):sg.verify_audit(self.out)

    def test_resealed_boolean_schema_rejected(self):
        self.make();self.reseal('graph.json',lambda v:v.update(schema_version=True))
        with self.assertRaisesRegex(ValueError,'RECOMPUTATION'):sg.verify_audit(self.out)

    def test_extra_bundle_file_rejected(self):
        self.make();(self.out/'extra').write_text('extra')
        with self.assertRaisesRegex(ValueError,'SET_MISMATCH'):sg.verify_audit(self.out)

    def test_missing_manifest_rejected(self):
        self.make();(self.out/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):sg.verify_audit(self.out)

    def test_output_permissions(self):
        self.make();self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_cli_verification_recomputes(self):
        self.make()
        with redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(sg.main(['verify-source-graph','--bundle',str(self.out)]),0)
        self.assertFalse(json.loads(stream.getvalue())['target_executed'])

    def test_cli_does_not_echo_bad_argument(self):
        with redirect_stderr(io.StringIO()) as stream,self.assertRaises(SystemExit):
            sg.main(['verify-source-graph','--bundle','SECRET_MARKER','--unsupported','SECRET_MARKER'])
        self.assertNotIn('SECRET_MARKER',stream.getvalue())

    def test_shared_core_tests_remain_present(self):
        import ast
        cases={}
        for path in (Path(sg.ROOT)/'tests').glob('test*.py'):
            tree=ast.parse(path.read_bytes())
            cases[path.name]={n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
        self.assertIn('test_forge_wrong_target',cases['test_bridge.py'])
        self.assertIn('test_native_roundtrip_always_requires_review',cases['test_integration.py'])

    def test_current_graph_cache_invalidates_changed_bytes(self):
        self.write()
        first=sg.current_graph(self.source)
        (self.source/'logic.py').write_bytes(b'import math\n')
        self.assertNotEqual(first['source_digest'],sg.current_graph(self.source)['source_digest'])

    def test_current_graph_cache_returns_fresh_result(self):
        self.write()
        first=sg.current_graph(self.source);first['vulnerability_confirmed']=True
        self.assertFalse(sg.current_graph(self.source)['vulnerability_confirmed'])

    def test_bundle_verifier_bypasses_report_cache(self):
        self.make()
        with patch.object(sg,'_cached_graph_bytes',side_effect=AssertionError('cache must not be used')):
            self.assertFalse(sg.verify_audit(self.out)['vulnerability_confirmed'])


if __name__ == '__main__':unittest.main()
