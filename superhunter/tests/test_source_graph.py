"""Actual parsing of benign source fixtures; never imports analyzed code."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import source_graph as sg
from superhunter.safe_io import canonical, strict_json


class SourceGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.sources={'__init__.py':b'', '__main__.py':b'from . import logic\n',
                      'logic.py':b'VALUE = 1\n'}

    def graph(self):return sg.analyze(self.sources)

    def test_real_relative_import_resolved(self):
        g=self.graph()
        self.assertEqual(g['status'],'SOURCE_GRAPH_RESOLVED')
        self.assertIn('superhunter.logic',g['syntactically_reachable'])
        edge=next(e for e in g['local_imports'] if e['to']=='superhunter.logic')
        self.assertEqual((edge['file'],edge['line']),('__main__.py',1))
        self.assertFalse(edge['execution_proven'])

    def test_removed_module_detected(self):
        del self.sources['logic.py']
        g=self.graph()
        self.assertEqual(g['status'],'SOURCE_GRAPH_REVIEW_REQUIRED')
        self.assertIn('superhunter.logic',[r.get('to') for r in g['unresolved']])

    def test_no_analyzed_code_is_executed(self):
        self.sources['logic.py']=b'raise RuntimeError("MUST_NOT_EXECUTE")\n'
        with patch('subprocess.run',side_effect=AssertionError),patch('socket.socket',side_effect=AssertionError):
            self.assertEqual(self.graph()['status'],'SOURCE_GRAPH_RESOLVED')

    def test_absolute_import_and_parent_initialization(self):
        self.sources['__main__.py']=b'import superhunter.logic as x\n'
        g=self.graph()
        self.assertEqual(set(g['syntactically_reachable']),{'superhunter','superhunter.__main__','superhunter.logic'})

    def test_nested_parent_resolution(self):
        self.sources.update({'sub/mod.py':b'from ..logic import VALUE\n','sub/__init__.py':b''})
        self.sources['__main__.py']=b'from .sub import mod\n'
        g=self.graph()
        self.assertIn('superhunter.sub.mod',g['syntactically_reachable'])
        self.assertIn('superhunter.logic',g['syntactically_reachable'])
        self.assertEqual(g['unresolved'],[])

    def test_namespace_package(self):
        self.sources['sub/mod.py']=b'from ..logic import VALUE\n'
        self.sources['__main__.py']=b'from .sub import mod\n'
        self.assertEqual(self.graph()['unresolved'],[])

    def test_explicit_symbol_not_mislabeled_as_missing_module(self):
        self.sources['__init__.py']=b'VALUE=1\n'
        self.sources['__main__.py']=b'from . import VALUE\n'
        self.assertEqual(self.graph()['unresolved'],[])

    def test_imported_symbol_does_not_require_submodule(self):
        self.sources['__main__.py']=b'from .logic import VALUE\n'
        self.assertEqual(self.graph()['unresolved'],[])

    def test_dynamic_loading_remains_unknown(self):
        self.sources['__main__.py']=b'loader.exec_module(x)\n__import__(name)\nexec(source)\n'
        g=self.graph()
        self.assertEqual(len(g['dynamic_loading']),3)
        self.assertEqual(g['status'],'SOURCE_GRAPH_REVIEW_REQUIRED')
        self.assertFalse(g['all_runtime_links_proven'])

    def test_wildcard_remains_explicit(self):
        self.sources['__main__.py']=b'from .logic import *\n'
        self.assertEqual(self.graph()['dynamic_loading'][0]['kind'],'wildcard_import')

    def test_conditional_and_function_imports_not_omitted(self):
        self.sources['__main__.py']=b'if False:\n    from . import logic\ndef f():\n    import superhunter.logic\n'
        g=self.graph()
        self.assertIn('superhunter.logic',g['syntactically_reachable'])
        self.assertTrue(all(e['execution_proven'] is False for e in g['local_imports']))

    def test_unreachable_module_is_not_assumed_called(self):
        self.sources['extra.py']=b'x=1\n'
        self.assertIn('superhunter.extra',self.graph()['not_proven_reachable'])

    def test_cycle_closure_terminates(self):
        self.sources['logic.py']=b'from . import __main__\n'
        g=self.graph()
        self.assertEqual(set(g['syntactically_reachable']),{'superhunter','superhunter.__main__','superhunter.logic'})

    def test_external_dependencies_are_only_references(self):
        self.sources['logic.py']=b'import imaginary_library\nfrom imaginary_library.other import thing\n'
        g=self.graph()
        self.assertEqual(len(g['external_imports']),2)
        self.assertFalse(g['external_dependencies_verified'])
        self.assertEqual(g['unresolved'],[])

    def test_no_entrypoint_is_not_proven_reachability(self):
        del self.sources['__main__.py']
        g=self.graph();self.assertIsNone(g['entrypoint'])
        self.assertEqual(g['syntactically_reachable'],[])

    def test_relative_escape_reported(self):
        self.sources['logic.py']=b'from ...outside import x\n'
        self.assertEqual(self.graph()['unresolved'][0]['reason'],'relative_import_outside_package')

    def test_ambiguous_file_package_rejected(self):
        self.sources['logic/__init__.py']=b''
        with self.assertRaisesRegex(ValueError,'ambiguous'):self.graph()

    def test_bad_syntax_not_silently_dropped(self):
        self.sources['logic.py']=b'def ???\n'
        with self.assertRaisesRegex(ValueError,'parsed'):self.graph()

    def test_unsafe_inventory_rejected(self):
        for p in ('../bad.py','/bad.py','x//bad.py','x\\bad.py','bad.txt'):
            with self.subTest(path=p),self.assertRaises(ValueError):
                sg.analyze({p:b''})

    def test_source_limits_enforced(self):
        with patch.object(sg,'MAX_TOTAL',1),self.assertRaisesRegex(ValueError,'budget'):self.graph()
        with patch.object(sg,'MAX_FILES',1),self.assertRaises(ValueError):self.graph()

    def test_json_identity_depends_on_actual_source_bytes(self):
        before=self.graph()['source_digest'];self.sources['logic.py']+=b'# modified\n'
        self.assertNotEqual(before,self.graph()['source_digest'])

    def test_deterministic_order(self):
        self.assertEqual(self.graph(),sg.analyze(dict(reversed(list(self.sources.items())))))

    def test_capture_rejects_symlink(self):
        (self.root/'a.py').symlink_to('/does-not-matter')
        with self.assertRaises((OSError,ValueError)):sg.capture(self.root)

    def test_capture_omits_tests_but_does_not_execute_sources(self):
        (self.root/'main.py').write_text('raise RuntimeError()')
        (self.root/'tests').mkdir();(self.root/'tests/test_x.py').write_text('INVALID')
        self.assertEqual(set(sg.capture(self.root)),{'main.py'})

    def test_current_own_package_observed(self):
        g=sg.current_graph()
        self.assertIn('superhunter.__main__',[m['module'] for m in g['modules']])
        self.assertGreater(len(g['modules']),10)
        self.assertIn('superhunter.native_runtime',[d['module'] for d in g['dynamic_loading']])
        self.assertFalse(g['vulnerability_confirmed'])

    def test_native_unsupported_rate_limiter_reported(self):
        # Keep the regression ID: omission must still be detected, but the
        # actual imported subset now contains the byte-pinned dependency.
        g=sg.current_graph()
        target='superhunter.native_sources.diablo.ratelimit'
        self.assertFalse(any(r.get('to')==target for r in g['unresolved']))
        captured=sg.capture()
        captured.pop('native_sources/diablo/ratelimit.py')
        missing=sg.analyze(captured)
        self.assertTrue(any(r.get('to')==target for r in missing['unresolved']))

    def test_cli_bundle_roundtrip(self):
        out=self.root/'case'
        with redirect_stdout(io.StringIO()) as output:
            code=sg.main(['audit-wiring','--out',str(out)])
        self.assertEqual(code,1)  # native dynamic loading is not statically resolved
        self.assertFalse(json.loads(output.getvalue())['all_runtime_links_proven'])
        r=sg.verify(out)
        self.assertEqual(r,sg.current_graph())

    def test_resealed_runtime_claim_rejected(self):
        out=self.root/'case';sg.create(out)
        g=strict_json((out/'graph.json').read_bytes());g['all_runtime_links_proven']=True
        raw=canonical(g);(out/'graph.json').write_bytes(raw)
        m=strict_json((out/'COMPLETE.json').read_bytes());m['sha256']['graph.json']=hashlib.sha256(raw).hexdigest()
        (out/'COMPLETE.json').write_bytes(canonical(m))
        with self.assertRaisesRegex(ValueError,'current source'):sg.verify(out)

    def test_new_output_required(self):
        out=self.root/'case';sg.create(out)
        with self.assertRaises(ValueError):sg.create(out)

    def test_no_sensitive_arguments_in_error_output(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            sg.main(['audit-wiring','--out',str(self.root/'case'),'--bad','PRIVATE_VALUE'])
        self.assertNotIn('PRIVATE_VALUE',stream.getvalue())

    def test_package_entrypoint_runs_actual_source_analysis(self):
        from superhunter import __main__
        out = self.root/'entrypoint'
        with patch('sys.argv',['superhunter','audit-wiring','--out',str(out)]), redirect_stdout(io.StringIO()):
            self.assertEqual(__main__.main(),1)
        self.assertEqual(sg.verify(out),sg.current_graph())


    def test_identical_bytes_reuse_parse_but_capture_twice_each_time(self):
        with patch.object(sg, '_GRAPH_CACHE', None), \
             patch.object(sg, 'capture', return_value=self.sources) as capture, \
             patch.object(sg, 'analyze', wraps=sg.analyze) as analyzer:
            first = sg.current_graph()
            second = sg.current_graph()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(capture.call_count, 4)
        self.assertEqual(analyzer.call_count, 1)

    def test_changed_bytes_invalidate_cached_graph(self):
        changed = {**self.sources, 'logic.py': b'VALUE = 2\n'}
        with patch.object(sg, '_GRAPH_CACHE', None), \
             patch.object(sg, 'capture', side_effect=[self.sources, self.sources, changed, changed]), \
             patch.object(sg, 'analyze', wraps=sg.analyze) as analyzer:
            first = sg.current_graph()
            second = sg.current_graph()
        self.assertEqual(analyzer.call_count, 2)
        self.assertNotEqual(first['source_digest'], second['source_digest'])

    def test_changed_bytes_on_cache_hit_second_capture_rejected(self):
        changed = {**self.sources, 'logic.py': b'VALUE = 2\n'}
        with patch.object(sg, '_GRAPH_CACHE', None), \
             patch.object(sg, 'capture', side_effect=[self.sources, self.sources, self.sources, changed]), \
             patch.object(sg, 'analyze', wraps=sg.analyze) as analyzer:
            sg.current_graph()
            with self.assertRaisesRegex(ValueError, 'source changed'):
                sg.current_graph()
        self.assertEqual(analyzer.call_count, 1)

    def test_caller_cannot_mutate_cached_result(self):
        with patch.object(sg, '_GRAPH_CACHE', None), \
             patch.object(sg, 'capture', return_value=self.sources):
            first = sg.current_graph()
            expected = canonical(first)
            first['modules'].clear()
            first['all_runtime_links_proven'] = True
            second = sg.current_graph()
        self.assertEqual(canonical(second), expected)
        self.assertFalse(second['all_runtime_links_proven'])

    def test_failed_parse_does_not_populate_cache(self):
        expected = sg.analyze(self.sources)
        with patch.object(sg, '_GRAPH_CACHE', None), \
             patch.object(sg, 'capture', return_value=self.sources), \
             patch.object(sg, 'analyze', side_effect=[ValueError('parse failed'), expected]) as analyzer:
            with self.assertRaisesRegex(ValueError, 'parse failed'):
                sg.current_graph()
            self.assertIsNone(sg._GRAPH_CACHE)
            self.assertEqual(sg.current_graph(), expected)
        self.assertEqual(analyzer.call_count, 2)

    def test_analyzer_identity_change_invalidates_cache(self):
        original = sg.analyze
        with patch.object(sg, '_GRAPH_CACHE', None), \
             patch.object(sg, 'capture', return_value=self.sources):
            sg.current_graph()
            with patch.object(sg, 'analyze', wraps=original) as analyzer:
                sg.current_graph()
                self.assertEqual(analyzer.call_count, 1)


if __name__=='__main__':unittest.main()
