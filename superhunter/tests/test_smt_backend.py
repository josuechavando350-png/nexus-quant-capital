"""Calls the actual installed native Z3 library. No mock success substitutes."""
import unittest
from unittest.mock import patch
from superhunter import smt_backend as smt

BASE='(set-logic QF_LIA)\n(declare-fun x0 () Bool)\n'


class NativeSMTTests(unittest.TestCase):
    def test_native_sat_unsat_and_model(self):
        sat=smt.solve_generated(BASE+'(assert x0)\n',1)
        unsat=smt.solve_generated(BASE+'(assert (and x0 (not x0)))\n',1)
        self.assertEqual(sat['status'],'SAT');self.assertEqual(sat['assignment'],[True])
        self.assertEqual(unsat['status'],'UNSAT');self.assertIsNone(unsat['assignment'])
        self.assertEqual(sat['engine']['engine'],'Z3')
        self.assertEqual(len(sat['engine']['library_sha256']),64)

    def test_native_unknown_at_resource_limit(self):
        result=smt.solve_generated(BASE+'(assert x0)\n',1,resource_limit=1)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['unknown_reason'],'RESOURCE_LIMIT')
        self.assertIsNone(result['assignment'])

    def test_invalid_smt_is_controlled_error(self):
        with self.assertRaisesRegex(smt.SolverError,'REJECTED_GENERATED_QUERY'):
            smt.solve_generated(BASE+'(assert missing_symbol)\n',1)
        self.assertEqual(smt.solve_generated(BASE+'(assert true)\n',1)['status'],'SAT')

    def test_invalid_budgets_not_coerced(self):
        for field,value in [('timeout_ms',True),('timeout_ms',0),('timeout_ms',5001),
                            ('resource_limit',False),('resource_limit',0)]:
            with self.subTest(field=field,value=value),self.assertRaises(smt.SolverError):
                smt.solve_generated(BASE+'(assert true)\n',1,**{field:value})

    def test_generated_language_profile_required(self):
        with self.assertRaises(smt.SolverError):smt.solve_generated('(assert true)',1)

    def test_input_size_bounded(self):
        with self.assertRaises(smt.SolverError):smt.solve_generated(BASE+' '*1_000_001,1)

    def test_variable_count_bounded(self):
        for count in (-1,17,True):
            with self.subTest(count=count),self.assertRaises(smt.SolverError):
                smt.solve_generated(BASE+'(assert true)\n',count)

    def test_unavailable_engine_not_fallback_success(self):
        with patch.object(smt,'PATHS',()),self.assertRaisesRegex(smt.SolverError,'UNAVAILABLE'):
            smt.engine_identity()

    def test_model_completion_covers_unused_boolean(self):
        result=smt.solve_generated(BASE+'(declare-fun x1 () Bool)\n(assert x0)\n',2)
        self.assertEqual(result['assignment'][0],True)
        self.assertEqual(len(result['assignment']),2)
        self.assertIs(type(result['assignment'][1]),bool)

    def test_engine_identity_reproducible(self):
        self.assertEqual(smt.engine_identity(),smt.engine_identity())

    def test_native_false_model(self):
        self.assertEqual(smt.solve_generated(BASE+'(assert (not x0))\n',1)['assignment'],[False])

    def test_no_socket_or_child_program(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.assertEqual(smt.solve_generated(BASE+'(assert true)\n',1)['status'],'SAT')
