"""Native dependency repair and safe local-admission regressions; no targets/network."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import local_lab, native_runtime, quality, source_graph
from superhunter.rate_control import AdmissionError, ScopedRateLimiter
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class RateControlTests(unittest.TestCase):
    def setUp(self):
        self.native = native_runtime.load_components()
        self.time = 0.0
        self.audit = self.native.audit.AuditLog()
        self.scope = self.native.scope.ScopeGuard(['*.lab.invalid'], ['blocked.lab.invalid'],
                                                 rps=2, audit_log=self.audit)

    def gate(self, **kwargs):
        return ScopedRateLimiter(self.scope, clock=lambda:self.time, **kwargs)

    def test_native_factory_resolves_original_dependency(self):
        limiter = self.scope.rate_limiter(capacity=1, clock=lambda:0)
        self.assertIsInstance(limiter, self.native.ratelimit.RateLimiter)
        self.assertTrue(limiter.try_acquire('a.lab.invalid'))
        self.assertFalse(limiter.try_acquire('a.lab.invalid'))

    def test_original_fifth_source_identity(self):
        rows=native_runtime.source_inventory()
        self.assertEqual(len(rows),5)
        row=next(r for r in rows if r['path']=='diablo/ratelimit.py')
        self.assertEqual(row['git_blob'],'ab5dc6292f4837376ee6f0849377f560839e5a99')
        raw=(native_runtime.ROOT/'diablo/ratelimit.py').read_bytes()
        self.assertEqual(len(raw),3554)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])

    def test_missing_fifth_source_fails_even_with_cached_modules(self):
        original=native_runtime.read_artifact
        def missing(root,path):
            if path=='diablo/ratelimit.py':raise FileNotFoundError()
            return original(root,path)
        with patch.object(native_runtime,'read_artifact',side_effect=missing),self.assertRaises(OSError):
            native_runtime.load_components()

    def test_changed_fifth_source_rejected_before_execution(self):
        original=native_runtime.read_artifact
        def changed(root,path):
            raw=original(root,path)
            return raw+b'\nraise RuntimeError("not executable")\n' if path=='diablo/ratelimit.py' else raw
        with patch.object(native_runtime,'read_artifact',side_effect=changed),self.assertRaisesRegex(ValueError,'source mismatch'):
            native_runtime.load_components()

    def test_original_native_sources_have_unchanged_identities(self):
        expected={'diablo/models.py':'bd832c728e71dc18bb4e9fa76bca7b36bf714a8b',
                  'diablo/audit.py':'b2f153b4f9f3157b385c47915fdae07db4888017',
                  'diablo/scope.py':'76ad323c59b60fd519d5446254662df1e8135082',
                  'nqc/capacity.py':'bbdcc5373adde03f0cad090e88bb9044aca8432a'}
        actual={r['path']:r['git_blob'] for r in native_runtime.source_inventory()}
        self.assertEqual(expected,{p:actual[p] for p in expected})

    def test_scope_factory_and_native_consumption_are_executed(self):
        cls=self.native.ratelimit.RateLimiter
        with patch.object(self.scope,'rate_limiter',wraps=self.scope.rate_limiter) as factory, \
             patch.object(cls,'try_acquire',autospec=True,side_effect=cls.try_acquire) as acquire:
            gate=self.gate();gate.try_admit('a.lab.invalid');gate.try_admit('a.lab.invalid')
        self.assertEqual(factory.call_count,1);self.assertEqual(acquire.call_count,2)

    def test_scope_denial_cannot_consume_tokens(self):
        gate=self.gate()
        with patch.object(gate._limiter,'try_acquire',wraps=gate._limiter.try_acquire) as acquire:
            with self.assertRaisesRegex(AdmissionError,'SCOPE_DENIED'):
                gate.try_admit('blocked.lab.invalid')
        acquire.assert_not_called()
        self.assertEqual(gate.stats().keys,0)
        self.assertEqual(self.audit.entries[-1].data['decision'],'DENY')

    def test_invalid_tokens_cannot_increase_available_credit(self):
        gate=self.gate();self.assertTrue(gate.try_admit('a.lab.invalid'))
        for tokens in (-1,0,True,False,float('nan'),float('inf'),-float('inf'),10**1000,'1',None):
            with self.subTest(value=repr(tokens)[:40]):
                with self.assertRaises(AdmissionError):gate.try_admit('a.lab.invalid',tokens)
                self.assertFalse(gate.try_admit('a.lab.invalid'))
        self.assertEqual(gate.stats().admitted,1)

    def test_over_capacity_request_cannot_block_forever(self):
        gate=self.gate()
        with self.assertRaisesRegex(AdmissionError,'REQUEST_EXCEEDS_CAPACITY'):
            gate.try_admit('a.lab.invalid',2)
        self.assertTrue(gate.try_admit('a.lab.invalid'))

    def test_refill_boundary_is_observable_without_sleep(self):
        gate=self.gate();self.assertTrue(gate.try_admit('a.lab.invalid'))
        self.time=0.25;self.assertFalse(gate.try_admit('a.lab.invalid'))
        self.time=0.5;self.assertTrue(gate.try_admit('a.lab.invalid'))
        self.assertFalse(gate.try_admit('a.lab.invalid'))

    def test_aliases_share_the_same_bucket(self):
        gate=self.gate();self.assertTrue(gate.try_admit('A.LAB.INVALID.'))
        for target in ('a.lab.invalid',' a.lab.invalid ','A.lab.INVALID'):
            self.assertFalse(gate.try_admit(target))
        self.assertEqual(gate.stats().keys,1)

    def test_per_key_overrides_are_not_global_rate(self):
        self.scope.rps_per_host={'a.lab.invalid':1.0,'b.lab.invalid':4.0}
        gate=self.gate()
        self.assertTrue(gate.try_admit('a.lab.invalid'));self.assertTrue(gate.try_admit('b.lab.invalid'))
        self.time=0.25
        self.assertFalse(gate.try_admit('a.lab.invalid'));self.assertTrue(gate.try_admit('b.lab.invalid'))

    def test_noncanonical_override_rejected_instead_of_ignored(self):
        self.scope.rps_per_host={'A.LAB.INVALID.':0.1}
        with self.assertRaisesRegex(AdmissionError,'NONCANONICAL_RATE_KEY'):self.gate()

    def test_invalid_native_rate_configuration_fails_closed(self):
        for rate in (float('nan'),float('inf'),0,-1,10**1000):
            with self.subTest(rate=repr(rate)[:40]):
                self.scope.rps=rate
                with self.assertRaises(AdmissionError):self.gate()
        self.scope.rps=1
        for rate in (0,-2,float('nan'),True):
            self.scope.rps_per_host={'a.lab.invalid':rate}
            with self.assertRaises(AdmissionError):self.gate()

    def test_capacity_and_key_budget_require_bounded_integers(self):
        for capacity in (0,-1,True,1.5,1000001):
            with self.assertRaises(AdmissionError):self.gate(capacity=capacity)
        for maximum in (0,True,4097,1.5):
            with self.assertRaises(AdmissionError):self.gate(max_keys=maximum)

    def test_host_budget_prevents_unbounded_bucket_growth(self):
        gate=self.gate(max_keys=1)
        self.assertTrue(gate.try_admit('a.lab.invalid'))
        with self.assertRaisesRegex(AdmissionError,'KEY_BUDGET'):
            gate.try_admit('b.lab.invalid')
        self.assertEqual(gate.stats().keys,1)

    def test_invalid_clock_and_backwards_time_abort(self):
        gate=self.gate();self.time=1;self.assertTrue(gate.try_admit('a.lab.invalid'))
        self.time=0
        with self.assertRaisesRegex(AdmissionError,'CLOCK_MOVED_BACKWARDS'):gate.try_admit('a.lab.invalid')
        for t in (float('nan'),float('inf'),-1,True,1e13):
            self.time=t
            with self.assertRaisesRegex(AdmissionError,'INVALID_CLOCK'):self.gate()

    def test_native_clock_failure_not_returned_as_permission(self):
        gate=self.gate()
        with patch.object(gate,'_clock',side_effect=RuntimeError('private clock failure')):
            with self.assertRaisesRegex(AdmissionError,'INVALID_CLOCK'):gate.try_admit('a.lab.invalid')
        self.assertEqual(gate.stats().admitted,0)

    def test_changed_rates_require_new_gate(self):
        gate=self.gate();self.scope.rps=10
        with self.assertRaisesRegex(AdmissionError,'CONFIGURATION_CHANGED'):gate.try_admit('a.lab.invalid')

    def test_changed_scope_requires_new_gate(self):
        gate=self.gate()
        self.scope._out.append(self.native.scope._Rule.parse('a.lab.invalid'))
        with self.assertRaisesRegex(AdmissionError,'CONFIGURATION_CHANGED'):gate.try_admit('a.lab.invalid')

    def test_native_exceptions_do_not_expose_private_keys(self):
        gate=self.gate()
        with patch.object(gate._limiter,'try_acquire',side_effect=RuntimeError('SECRET_MARKER')):
            with self.assertRaises(AdmissionError) as caught:gate.try_admit('a.lab.invalid')
        self.assertNotIn('SECRET_MARKER',str(caught.exception))

    def test_native_nonboolean_decision_cannot_be_truthy_success(self):
        gate=self.gate()
        with patch.object(gate._limiter,'try_acquire',return_value=1):
            with self.assertRaisesRegex(AdmissionError,'INVALID_NATIVE_DECISION'):gate.try_admit('a.lab.invalid')

    def test_real_threads_share_one_fixed_capacity(self):
        gate=self.gate(capacity=3)
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes=list(pool.map(lambda _:gate.try_admit('a.lab.invalid'),range(64)))
        self.assertEqual(sum(outcomes),3)
        self.assertEqual((gate.stats().admitted,gate.stats().deferred),(3,61))

    def test_exact_fraction_reference_for_seeded_schedule(self):
        rng=random.Random(20261104);now=Fraction(0);state={}
        self.scope.rps_per_host={'a.lab.invalid':0.5,'b.lab.invalid':2.0}
        gate=self.gate(capacity=3)
        for _ in range(512):
            now+=Fraction(rng.randrange(3),4);self.time=float(now)
            key=rng.choice(('a.lab.invalid','b.lab.invalid'))
            rate=Fraction(1,2) if key.startswith('a') else Fraction(2)
            tokens,updated=state.get(key,(Fraction(3),now))
            tokens=min(Fraction(3),tokens+(now-updated)*rate)
            allowed=tokens>=1
            state[key]=(tokens-1 if allowed else tokens,now)
            self.assertIs(gate.try_admit(key),allowed)

    def test_gate_does_not_send_sleep_or_execute_callbacks(self):
        with patch('socket.socket',side_effect=AssertionError('network')), \
             patch('subprocess.run',side_effect=AssertionError('process')), \
             patch('time.sleep',side_effect=AssertionError('sleep')):
            gate=self.gate();self.assertTrue(gate.try_admit('a.lab.invalid'))
            self.assertFalse(gate.try_admit('a.lab.invalid'))

    def test_solver_not_called_when_gate_defers(self):
        with patch.object(local_lab.ScopedRateLimiter,'try_admit',return_value=False), \
             patch.object(self.native.capacity,'solve',wraps=self.native.capacity.solve) as solve:
            with self.assertRaisesRegex(ValueError,'calculation not run'):local_lab.execute_local()
        solve.assert_not_called()

    def test_every_valid_lab_case_uses_the_gate(self):
        actual=local_lab.ScopedRateLimiter.try_admit
        with patch.object(local_lab.ScopedRateLimiter,'try_admit',autospec=True,side_effect=actual) as gate:
            output=local_lab.execute_local()
        self.assertEqual(gate.call_count,5)
        result=strict_json(output['lab-result.json'])
        self.assertEqual(result['local_rate_control']['admitted'],5)
        self.assertEqual(len(strict_json(output['source-provenance.json'])['sources']),5)
        self.assertIn('DIABLO.RateLimiter.try_acquire',result['native_functions'])

    def test_rate_claim_tampering_rejected_after_resigning_manifest(self):
        output=local_lab.execute_local()
        result=strict_json(output['lab-result.json']);result['local_rate_control']['admitted']=True
        output['lab-result.json']=canonical(result)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'changed';write_new_bundle(root,output)
            with self.assertRaisesRegex(ValueError,'rate-control evidence'):local_lab.verify_local_bundle(root)

    def test_graph_includes_fixed_dependency_and_dynamic_uncertainty(self):
        graph=source_graph.current_graph()
        target='superhunter.native_sources.diablo.ratelimit'
        self.assertTrue(any(e['to']==target for e in graph['local_imports']))
        self.assertFalse(any(e.get('to')==target for e in graph['unresolved']))
        self.assertFalse(graph['all_runtime_links_proven'])

    def test_quality_registers_both_original_and_wrapper(self):
        self.assertIn('native_sources/diablo/ratelimit.py',quality.COMPONENTS['native']['files'])
        self.assertIn('rate_control.py',quality.COMPONENTS['rate_control']['files'])
        self.assertIn('rate_control',quality.COMPONENTS['lab']['depends'])
        self.assertIn('test_rate_control.RateControlTests.test_solver_not_called_when_gate_defers',quality.REQUIRED_TESTS)

    def test_no_fake_guard_or_control_characters(self):
        with self.assertRaises(AdmissionError):ScopedRateLimiter(object())
        gate=self.gate()
        for target in ('a.lab.invalid\n',object(),'.','a.\tlab.invalid'):
            with self.assertRaises(AdmissionError):gate.try_admit(target)

    def test_default_monotonic_clock_can_admit_locally(self):
        gate=ScopedRateLimiter(self.scope,capacity=1)
        self.assertTrue(gate.try_admit('real-clock.lab.invalid'))
        # No assertion about the second call's timing: scheduling may delay it.
        self.assertEqual(gate.stats().admitted,1)


if __name__=='__main__':unittest.main()
