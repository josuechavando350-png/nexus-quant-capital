"""Synthetic unit observations only; real two-EVM acceptance runs separately."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import random
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import owned_authority_evm_cases as cases, owned_authority_cross_evm as cross
from superhunter import owned_authority_spec_worker as eels_worker, owned_authority_geth as geth_worker
from superhunter.safe_io import canonical, write_new_bundle


def synthetic_executions(digest):
    """Clearly synthetic test fixture, never used by the acceptance command."""
    builds = [{'variant': v, 'codegen': c, 'source_sha256': cases.sha(cases.owned_source(v).encode()),
               'input_sha256': cases.sha(canonical(cases.compile_input(v, c))),
               'output_sha256': '1' * 64, 'creation_sha256': '2' * 64, 'runtime_sha256': '3' * 64}
              for v in cases.model.VARIANTS for c in cases.CODEGEN]
    constructors, rows = [], []
    for case, codegen in cases.inventory():
        state = deepcopy(cases.INITIAL)
        constructors.append({'case_id': case['case_id'], 'codegen': codegen,
                             'initial_state': deepcopy(state), 'runtime_sha256': '3' * 64})
        abstract = cases.model.simulate(case['variant'], case['events'])
        for call_index, item in enumerate(cases.schedule(case['events'])):
            before = deepcopy(state); index = item['event_index']; event = case['events'][index]
            if not item['probe']:
                row = abstract['observations'][index]
                state['phase'] += 1; state['accepted'] = int(row['accepted'])
                state['effects'] = [row['effects_after'][key] for key in cases.model.EFFECT_KEYS]
                key = (cases.model.PRINCIPALS.index(event['principal']) * 4 +
                       cases.model.TENANTS.index(event['tenant']) * 2 + cases.model.ACTIONS.index(event['action']))
                if event['op'] == 'grant':
                    state['enabled'] |= 1 << key; state['generations'][key] += 1
                elif event['op'] == 'revoke' and case['variant'] != 'revoke_noop':
                    state['enabled'] &= ~(1 << key); state['generations'][key] += 1
            rows.append({'case_id': case['case_id'], 'codegen': codegen, 'call_index': call_index,
                'event_index': index, 'probe': item['probe'], 'state_root': '4' * 64, 'stdout_sha256': '5' * 64,
                'observation': {'before': before, 'after': deepcopy(state), 'word': item['word'], 'gas': item['gas'],
                    'status': 'OUT_OF_GAS' if item['probe'] else 'COMMITTED',
                    'return_data': '0x' if item['probe'] else '0x' + format(state['accepted'], '064x')}})
    first = {'schema_version': 1, 'profile': cases.PROFILE, 'source_digest': digest, 'engine': 'geth',
        'fork': 'Cancun', 'solc_sha256': cases.compiler.PIN['sha256'], 'geth_sha256': cases.evm.PIN['sha256'],
        'builds': builds, 'constructors': constructors, 'rows': rows, 'compiler_runs': len(builds),
        'constructor_executions': len(constructors), 'runtime_calls': len(rows)}
    second = {k: deepcopy(v) for k, v in first.items() if k != 'geth_sha256'}
    second.update(engine='execution-specs', dependencies={n: {k: p[k] for k in ('version', 'files', 'runtime_sha256')}
                  for n, p in cross.PINS.items()},
                  rows=[{k: deepcopy(v) for k, v in r.items() if k not in ('state_root', 'stdout_sha256')}
                        for r in rows])
    return first, second


class AuthorityEVMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.digest = cross.sha(canonical(cross.quality.source_snapshot()))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.first, self.second = synthetic_executions(self.digest)

    def assess(self):
        return cross.compare(self.first, self.second, self.digest)

    def execute(self, engine, *args):
        return deepcopy(self.first if engine == 'geth' else self.second)

    def make(self):
        with patch.object(cross, '_run_worker', side_effect=self.execute):
            return cross.create(self.root / 'bundle', self.root / 'solc', self.root / 'geth', self.digest)

    def verify(self):
        with patch.object(cross, '_run_worker', side_effect=self.execute):
            return cross.verify(self.root / 'bundle', self.root / 'solc', self.root / 'geth', self.digest)

    def reseal(self, name, change):
        folder = self.root / 'bundle'; obj = json.loads((folder / name).read_bytes()); change(obj)
        raw = canonical(obj); (folder / name).write_bytes(raw)
        marker = json.loads((folder / 'COMPLETE.json').read_bytes()); marker['sha256'][name] = cross.sha(raw)
        (folder / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_known_cases_keep_the_latent_omission(self):
        report, traces = self.assess()
        counts = report['metrics']['full']['counts']
        self.assertEqual(tuple(counts[k] for k in ('tp', 'tn', 'fp', 'fn')), (6, 4, 0, 1))
        self.assertEqual(report['missed_case_ids'], ['latent_revocation'])
        self.assertFalse(report['all_seeded_cases_detected'])
        self.assertEqual(len(traces['cases']), 11)

    def test_vm_success_is_not_application_authorization(self):
        report, _ = self.assess()
        counts = report['vm_success_as_authorization_metrics']['counts']
        self.assertEqual(tuple(counts[k] for k in ('tp', 'tn', 'fp', 'fn')), (6, 1, 3, 1))
        denied = [r for r in self.first['rows'] if not r['probe'] and not r['observation']['after']['accepted']]
        self.assertTrue(denied)
        self.assertTrue(all(r['observation']['status'] == 'COMMITTED' for r in denied))

    def test_replays_codegen_and_probes_do_not_inflate_case_count(self):
        report, _ = self.assess()
        self.assertEqual((report['known_case_count'], report['model_observations']), (11, 42))
        self.assertEqual((report['compiler_runs_per_engine'], report['constructor_executions_per_engine'],
                          report['runtime_calls_per_engine'], report['out_of_gas_probes_per_engine']), (14, 22, 106, 22))
        for key in ('independent_producers_proved', 'all_evm_semantics_certified', 'caller_identity_authenticated',
                    'cryptographic_credential_authentication_implemented', 'blind_benchmark',
                    'generalization_established', 'platform_complete', 'vulnerability_confirmed'):
            self.assertIs(report[key], False)

    def test_abstract_traces_omit_variant_and_truth(self):
        _, execution = self.assess()
        for row in execution['cases']:
            self.assertEqual(set(row), {'case_id', 'trace'})
            self.assertEqual(set(row['trace']), {'schema_version', 'profile', 'events', 'observations'})

    def test_all_fixed_inputs_encode_without_collisions(self):
        words = set()
        for principal in cases.model.PRINCIPALS:
            for tenant in cases.model.TENANTS:
                for action in cases.model.ACTIONS:
                    for op in ('grant', 'revoke'):
                        word = cases.encode(cases.corpus.event(op, principal, tenant, action))
                        self.assertNotIn(word, words); words.add(word)
                    for cp in cases.model.PRINCIPALS:
                        for ct in cases.model.TENANTS:
                            for ca in cases.model.ACTIONS:
                                for generation in range(65):
                                    event = cases.corpus.event('use', principal, tenant, action,
                                        credential={'principal': cp, 'tenant': ct, 'action': ca, 'generation': generation})
                                    word = cases.encode(event); self.assertNotIn(word, words); words.add(word)
                                    self.assertLess(word, 65536)
        self.assertEqual(len(words), 4176)

    def test_encoding_rejects_boolean_generation_and_extra_fields(self):
        for event in (cases.corpus.event('use', generation=True),
                      {**cases.corpus.event('grant'), 'caller': 'third-party'}):
            with self.assertRaises(ValueError): cases.encode(event)

    def test_independent_byte_and_bit_decoders_match_all_fields(self):
        randomizer = random.Random(678031)
        for _ in range(1000):
            values = [randomizer.randrange(65), randomizer.randrange(2), randomizer.randrange(256)]
            values += [randomizer.randrange(65) for _ in range(8)] + [randomizer.randrange(129) for _ in range(4)]
            word = sum(value << (8 * index) for index, value in enumerate(values))
            self.assertEqual(cases.decode_word(word), eels_worker.decode_word(word))
            self.assertEqual(cases.decode_word(word)['effects'], values[11:15])

    def test_decoders_reject_boolean_high_bits_and_invalid_state(self):
        for word in (True, -1, 2**120, 65, 2 << 8, 65 << 24, 129 << 88):
            for decoder in (cases.decode_word, eels_worker.decode_word):
                with self.assertRaises(ValueError): decoder(word)

    def test_schedule_inserts_only_one_probe_without_consuming_an_event(self):
        for case in cases.corpus.cases():
            rows = cases.schedule(case['events'])
            self.assertEqual(sum(row['probe'] for row in rows), 1)
            self.assertEqual([r['event_index'] for r in rows if not r['probe']], list(range(len(case['events']))))
            i = next(i for i, row in enumerate(rows) if row['probe'])
            self.assertEqual(rows[i]['word'], rows[i + 1]['word'])
            self.assertEqual(rows[i]['event_index'], rows[i + 1]['event_index'])

    def test_probe_that_changes_any_state_field_is_rejected(self):
        pristine = deepcopy(self.second)
        for field in cases.INITIAL:
            self.second = deepcopy(pristine)
            row = next(r for r in self.second['rows'] if r['probe'])
            if isinstance(row['observation']['after'][field], list): row['observation']['after'][field][0] += 1
            else: row['observation']['after'][field] ^= 1
            with self.assertRaises(ValueError): self.assess()

    def test_committed_return_must_match_application_flag(self):
        self.second['rows'][0]['observation']['return_data'] = '0x' + '0' * 64
        with self.assertRaisesRegex(ValueError, 'APPLICATION_RETURN'): self.assess()

    def test_probe_cannot_be_relabelled_as_an_application_denial(self):
        row = next(r for r in self.second['rows'] if r['probe'])
        row['observation']['status'] = 'COMMITTED'; row['observation']['return_data'] = '0x' + '0' * 64
        with self.assertRaisesRegex(ValueError, 'PROBE_PERSISTED'): self.assess()

    def test_each_native_row_is_bound_to_fixed_input(self):
        original = deepcopy(self.second['rows'])
        for index in range(106):
            self.second['rows'] = deepcopy(original); self.second['rows'][index]['observation']['word'] ^= 4
            with self.assertRaisesRegex(ValueError, 'FIXED_INPUT'): self.assess()

    def test_missing_duplicate_or_reordered_rows_are_rejected(self):
        original = deepcopy(self.second['rows'])
        for rows in (original[:-1], original + [original[0]], list(reversed(original))):
            self.second['rows'] = rows
            with self.assertRaises(ValueError): self.assess()

    def test_state_chain_and_phase_must_match_consumed_events(self):
        self.second['rows'][0]['observation']['after']['phase'] = 2
        with self.assertRaisesRegex(ValueError, 'APPLICATION_RETURN'): self.assess()

    def test_engine_agreement_does_not_replace_python_model_comparison(self):
        for execution in (self.first, self.second):
            for row in execution['rows']:
                if row['case_id'] == 'valid_denied' and not row['probe'] and row['event_index'] == 1:
                    row['observation']['after']['accepted'] = 1
                    row['observation']['after']['effects'][0] = 1
                    row['observation']['return_data'] = '0x' + format(1, '064x')
        with self.assertRaisesRegex(ValueError, 'PYTHON_MODEL_DISAGREEMENT'): self.assess()

    def test_internal_state_disagreement_is_not_hidden_by_equal_projection(self):
        self.second['rows'][-1]['observation']['after']['generations'][0] += 1
        with self.assertRaisesRegex(ValueError, 'ENGINE_DISAGREEMENT'): self.assess()

    def test_engine_fork_source_and_dependency_identity_are_required(self):
        original = deepcopy(self.second)
        for key, value in (('engine', 'geth'), ('fork', 'Prague'), ('source_digest', '0' * 64),
                           ('solc_sha256', '0' * 64), ('dependencies', {})):
            self.second = deepcopy(original); self.second[key] = value
            with self.assertRaises(ValueError): self.assess()

    def test_native_hashes_and_constructor_identity_are_required(self):
        original = deepcopy(self.first)
        for key in ('geth_sha256', 'solc_sha256'):
            self.first = deepcopy(original); self.first[key] = '0' * 64
            with self.assertRaises(ValueError): self.assess()
        self.first = deepcopy(original); self.first['constructors'][0]['runtime_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'CONSTRUCTOR_IDENTITY'): self.assess()

    def test_build_difference_and_unreviewed_source_are_rejected(self):
        self.second['builds'][0]['output_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'BUILD_DISAGREEMENT'): self.assess()
        self.second['builds'][0]['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'BUILD_IDENTITY'): self.assess()

    def test_boolean_counters_metadata_and_state_are_rejected(self):
        original = deepcopy(self.second)
        for key in ('schema_version', 'compiler_runs', 'constructor_executions', 'runtime_calls'):
            self.second = deepcopy(original); self.second[key] = True
            with self.assertRaises(ValueError): self.assess()
        self.second = deepcopy(original); self.second['rows'][0]['event_index'] = False
        with self.assertRaises(ValueError): self.assess()
        self.second = deepcopy(original); self.second['rows'][0]['observation']['before']['accepted'] = False
        with self.assertRaises(ValueError): self.assess()

    def test_bundle_replays_both_engines_and_preserves_existing_output(self):
        self.make(); before = (self.root / 'bundle/COMPLETE.json').read_bytes()
        with patch.object(cross, '_run_worker', side_effect=self.execute) as worker:
            cross.verify(self.root / 'bundle', self.root / 'solc', self.root / 'geth', self.digest)
            self.assertEqual([call.args[0] for call in worker.call_args_list], ['geth', 'execution-specs'])
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT'): self.make()
        self.assertEqual((self.root / 'bundle/COMPLETE.json').read_bytes(), before)

    def test_rehashed_omission_removal_is_rejected_by_replay(self):
        self.make(); self.reseal('comparison.json', lambda r: r.update(missed_case_ids=[], all_seeded_cases_detected=True))
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): self.verify()

    def test_wrong_external_digest_blocks_before_native_execution(self):
        self.make()
        with patch.object(cross, '_run_worker', side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError, 'SOURCE_MISMATCH'):
                cross.verify(self.root / 'bundle', self.root / 'solc', self.root / 'geth', '0' * 64)

    def test_extra_file_and_raw_tamper_block_before_replay(self):
        self.make(); folder = self.root / 'bundle'; original = (folder / 'traces.json').read_bytes()
        (folder / 'traces.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'BUNDLE_HASH'): self.verify()
        (folder / 'traces.json').write_bytes(original); (folder / 'extra').write_bytes(b'own')
        with self.assertRaisesRegex(ValueError, 'BUNDLE_INVENTORY'): self.verify()

    def test_marker_byte_change_during_replay_is_rejected(self):
        self.make(); original = self.execute
        def mutate(engine, *args):
            if engine == 'execution-specs':
                marker = self.root / 'bundle/COMPLETE.json'
                value = json.loads(marker.read_bytes()); value['schema_version'] = True
                marker.write_bytes(canonical(value))
            return original(engine, *args)
        with patch.object(cross, '_run_worker', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'EVIDENCE_CHANGED_DURING_REPLAY'):
                cross.verify(self.root / 'bundle', self.root / 'solc', self.root / 'geth', self.digest)

    def test_symlink_bundle_and_symlink_artifact_are_rejected(self):
        self.make(); link = self.root / 'link'; link.symlink_to(self.root / 'bundle', target_is_directory=True)
        with self.assertRaises(ValueError): cross.verify(link, self.root / 'solc', self.root / 'geth', self.digest)
        file = self.root / 'bundle/geth.json'; other = self.root / 'outside'; file.rename(other); file.symlink_to(other)
        with self.assertRaises((ValueError, OSError)): self.verify()

    def test_optional_runtime_not_loaded_for_wrong_source(self):
        with patch.object(eels_worker, 'dependency_identity', side_effect=AssertionError('must not import')):
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                eels_worker.execute_fixed(self.root / 'solc', '0' * 64)
        with patch.object(geth_worker.compiler, 'read_pinned_binary', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                geth_worker.execute_fixed(self.root / 'solc', self.root / 'geth', '0' * 64, 0)

    def test_only_closed_variants_and_codegen_profiles_are_accepted(self):
        for value in ('arbitrary.sol', '../third-party', None, True):
            with self.assertRaises(ValueError): cases.owned_source(value)
            with self.assertRaises(ValueError): cases.compile_input('correct', value)

    def test_source_change_during_execution_is_rejected(self):
        before = cross.quality.source_snapshot()
        with patch.object(cross, '_run_worker', side_effect=self.execute), \
             patch.object(cross.quality, 'source_snapshot', side_effect=[before, before, before, before, {}]):
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED_DURING_RUN'):
                cross._execute(self.root / 'solc', self.root / 'geth', self.digest)

    def test_worker_timeout_uses_fixed_wall_limit(self):
        with patch.object(cross.owned_process, 'run', side_effect=subprocess.TimeoutExpired('own', 180)) as run:
            with self.assertRaisesRegex(ValueError, 'WORKER_TIMEOUT'):
                cross._run_worker('execution-specs', self.root / 'solc', self.root / 'geth', self.digest)
            self.assertEqual(run.call_args.kwargs['timeout'], 180)

    def test_cli_redacts_private_paths_and_preserves_failed_exit(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            rc = cross.main(['verify-owned-authority-engines', '--bundle', '/private/own/path',
                             '--solc', '/private/solc', '--evm', '/private/evm', '--expected-source', '0' * 64])
        self.assertEqual(rc, 2); self.assertNotIn('/private', output.getvalue() + errors.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'], 'OWNED_AUTHORITY_CROSS_EVM_BLOCKED')
