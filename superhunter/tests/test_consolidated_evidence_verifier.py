"""Refute false credits using archived inputs; replaying a receipt never counts as a new execution."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT
from superhunter.safe_io import canonical, strict_json
from superhunter.tools import render_product_matrix as renderer
from superhunter.tools import verify_native_session as native_verifier
from superhunter.tools import verify_review_115 as verifier


class ConsolidatedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = verifier.unpack((ROOT/'superhunter/product_supply/native-session-70.json').read_bytes())
        cls.keys = verifier.response_keys(cls.archive)

    def test_historical_archive_preserves_its_own_acceptance_scope(self):
        result = native_verifier.verify(self.archive)
        self.assertEqual((result['session'], result['executables'], result['reference_data']), (70, 58, 12))
        with self.assertRaisesRegex(EvidenceError, 'incomplete consolidated session'):
            verifier.verify(self.archive, require_consolidated=True)

    def test_old_runtime_is_accepted_only_in_the_exact_archived_session(self):
        lines = self.archive.splitlines()
        report = strict_json(lines[self.keys.index('native-capabilities')])
        with self.assertRaisesRegex(EvidenceError, 'native producer bytes'):
            verifier.native_bindings({'native-capabilities': report})
        self.assertTrue(verifier.native_bindings({'native-capabilities': report}, version=70))
        lines[0] += b' '
        with self.assertRaisesRegex(EvidenceError, 'published 70-identity session'):
            native_verifier.verify(b'\n'.join(lines) + b'\n')

    def test_interim_component_session_verifies_individual_negative_controls(self):
        raw = verifier.unpack((ROOT/'superhunter/product_supply/component-session-99.json').read_bytes())
        self.assertEqual(len(verifier.negative_controls(raw)), 14)
        with self.assertRaisesRegex(EvidenceError, 'published 99-identity session'):
            verifier.verify(raw.rstrip(b'\n') + b' \n')

    def test_native_receipt_without_the_group_report_is_rejected(self):
        raw = b'\n'.join(self.archive.splitlines()[:-1]) + b'\n'
        with self.assertRaisesRegex(EvidenceError, 'no matching producer receipt'):
            verifier.verify(raw)

    def test_source_digest_substitution_is_rejected(self):
        lines = self.archive.splitlines()
        idx = self.keys.index('source-inventory')
        value = strict_json(lines[idx])
        value['snapshot_sha256'] = '0' * 64
        lines[idx] = canonical(value).rstrip(b'\n')
        with self.assertRaisesRegex(EvidenceError, 'unknown source inventory'):
            verifier.verify(b'\n'.join(lines) + b'\n')

    def test_native_failure_gets_no_credit_and_cannot_also_be_a_success(self):
        value = strict_json(self.archive.splitlines()[self.keys.index('native-capabilities')])
        failure = {'web': {'error_type': 'ValueError', 'message': 'deliberate offline failure'}}
        value['blocked_groups'] = failure
        with self.assertRaisesRegex(EvidenceError, 'group membership or scope'):
            verifier.native_bindings({'native-capabilities': value})
        value.update(groups={}, repositories=[], functional_participations=0)
        self.assertEqual(verifier.native_bindings({'native-capabilities': value}), {})

    def test_two_producer_rows_credit_the_identity_once_and_reject_resealed_loss(self):
        from superhunter.product_batches import coverage
        from superhunter.product_component_controls import validate_group
        from superhunter.product_matrix import build

        # Reconstruct the accounting input from actual archived results. This exercise
        # checks the evidence consumer only, and must not be counted as a producer run.
        docs = {k: strict_json(b'{"r":' + line + b'}')['r']
                for k, line in zip(self.keys, self.archive.splitlines(), strict=True)}
        repos = {r['repository'].casefold(): r for r in docs.values() if isinstance(r, dict) and 'catalog_id' in r}
        # The modern consumer needs the official Node report. Retain the real archive
        # unchanged and update only this reconstructed test input and its receipts.
        from superhunter.product_native_capabilities import contracts, expected_receipt
        evm = contracts()['evm']
        docs['native-capabilities']['groups']['evm'] = strict_json(
            (ROOT/'superhunter/product_supply/evm-native-result.json').read_bytes())
        for name in evm['repositories']:
            repos[name.casefold()]['native_capability_receipt'] = expected_receipt('evm', name, evm)
        index = SimpleNamespace(repos=repos, lookup=lambda name: repos[name.casefold()],
                                source_inventory=docs['source-inventory'], root_declarations=docs['root-declarations'],
                                owned_source_checks=docs['owned-source-checks'], census_header=docs['census-header'],
                                geth_header=docs['geth-census'], source_references=docs['source-references'],
                                score_comparison=docs['score-comparison'], fork_headers=docs['fork-headers'])
        results = strict_json((ROOT/'superhunter/product_supply/formats-batch.json').read_bytes())
        for name, receipt in validate_group('object-format', results).items():
            repos[name.casefold()]['component_control_receipt'] = receipt
        docs['component-controls'] = {'requested': ['object-format'], 'blocked': {},
                                      'observations': results, 'digest_corroboration': {}}
        docs['integration-matrix'] = build(index)
        docs['integration-coverage'] = coverage(index)

        def transcript():
            return b''.join(canonical(value) for value in docs.values())

        verified = verifier.verify(transcript())
        self.assertEqual((verified['session'], verified['operations'], verified['multiple_operations']), (71, 72, 1))
        caps = index.lookup('capstone-engine/capstone')['catalog_id'] - 1
        docs['integration-matrix']['rows'][caps]['session_operations'].pop()
        docs['integration-coverage']['identities'][caps]['session_operations'].pop()
        docs['integration-matrix'].update(session_operation_count=71, session_multi_operation_repositories=0)
        with self.assertRaisesRegex(EvidenceError, 'operation ledger'):
            verifier.verify(transcript())

    def test_duplicate_or_out_of_order_supplemental_responses_are_rejected(self):
        lines = self.archive.splitlines()
        for tail in ([lines[-1], lines[-1]], [lines[-2], lines[-3], lines[-1]]):
            with self.subTest():
                raw = b'\n'.join(lines[:-3] + tail) + b'\n'
                with self.assertRaisesRegex(EvidenceError, 'missing or extra responses'):
                    verifier.verify(raw)

    def test_historical_matrix_keeps_all_identities_and_both_receipts(self):
        text = renderer.historical_markdown()
        has_dossier = any((ROOT / path).exists() for path, _ in renderer.PROFILES.values())
        published = renderer.accepted_markdown() if has_dossier else text
        self.assertEqual(published.encode(), renderer.MATRIX.read_bytes())
        rows = [line.split(' | ') for line in text.splitlines() if line.startswith('| ') and line[2:3].isdigit()]
        self.assertEqual([int(row[0][2:]) for row in rows], list(range(1, 201)))
        self.assertIn('Aceptación conjunta pendiente', text)
        with_both = [row for row in rows if row[3] != '—' and row[4] != '— |']
        self.assertEqual(len(with_both), 63)
        self.assertEqual(sum('Ejecución' in ' '.join(row[3:]) for row in rows), 71)
        self.assertEqual(sum('Referencia' in ' '.join(row[3:]) for row in rows), 35)
        different_producers = [int(row[0][2:]) for row in with_both
                               if 'component_control_receipt' in row[3] and 'native_capability_receipt' in row[4]]
        self.assertEqual(different_producers, [20, 92, 103, 132])
        left, right = rows[140][3:]
        self.assertIn('license_file_evidence', left)
        self.assertIn('license_file_evidence', right)
        self.assertIn('75dc6e9563c60a8e6f31792e7ce309b7f87abad6325c8a8849ed38f612b0e3d5', left)
        self.assertIn('f99668677b36becf646fbfe9b99658ec29b2a8186f0e7dc50005a95ef8ce4f4a', right)

    def test_historical_matrix_rejects_changed_producer_with_intact_transcript(self):
        name = 'component-session-99.json'
        archive = strict_json((verifier.SUPPLY / name).read_bytes())
        archive['producer_commit'] = '0' * 40
        forged = canonical(archive)
        self.assertEqual(verifier.sha(verifier.unpack(forged)), verifier.INTERIM_99)
        with TemporaryDirectory() as tmp, patch.object(verifier, 'SUPPLY', Path(tmp)):
            (Path(tmp) / name).write_bytes(forged)
            with self.assertRaisesRegex(EvidenceError, 'differs from reviewed bytes'):
                verifier.pinned_file(name, verifier.ARCHIVE_99_SHA)

    def test_historical_matrix_rejects_identity_change_between_sessions(self):
        row = {'id': 1, 'repository': 'local/example', 'commit': 'a' * 40, 'tree': 'b' * 40}
        for key in row:
            with self.subTest(key=key), self.assertRaisesRegex(EvidenceError, 'identity, revision or tree'):
                renderer.render(({}, [row], {}), ({}, [{**row, key: 'changed'}], {}))

    def historical_rows_for_accounting(self):
        # Build independent ledger inputs from the two actual frozen matrices.
        # No producer runs in these tests of the final cross-session comparison.
        rows = {}
        for raw, _ in verifier.historical_archives():
            matrix = strict_json(raw.splitlines()[verifier.response_keys(raw).index('integration-matrix')])
            for old in matrix['rows']:
                row = rows.setdefault(old['id'], {'id': old['id'], 'repository': old['repository'],
                                                  'session_operations': []})
                if old['receipt']:
                    op = {'role': old['session'], 'receipt': old['receipt'],
                          'evidence_sha256': old['session_evidence_sha256']}
                    if op not in row['session_operations']:
                        row['session_operations'].append(op)
        return rows

    def test_covered_history_requires_the_same_identity_even_at_identical_totals(self):
        rows = self.historical_rows_for_accounting()
        self.assertFalse(rows[2]['session_operations'])
        rows[2]['session_operations'] = rows[1]['session_operations']
        rows[1]['session_operations'] = []
        with self.assertRaisesRegex(EvidenceError, 'usestrix/strix'):
            verifier.check_historical_coverage(rows.values())

    def test_covered_history_requires_both_operations_of_all_four_shared_producers(self):
        rows = self.historical_rows_for_accounting()
        for number in (20, 92, 103, 132):
            operations = rows[number]['session_operations']
            self.assertEqual(len(operations), 2)
            for kept in operations:
                rows[number]['session_operations'] = [kept]
                with self.subTest(number=number, kept=kept['receipt']), self.assertRaisesRegex(
                        EvidenceError, r'historical operations missing \(1\)'):
                    verifier.check_historical_coverage(rows.values())
                rows[number]['session_operations'] = operations

    def test_covered_history_accepts_the_union_and_proven_role_promotion(self):
        rows = self.historical_rows_for_accounting()
        result = verifier.check_historical_coverage(rows.values())
        self.assertEqual(result, {'historical_identities_preserved': 106, 'historical_operations_preserved': 110})
        reference = next(op for row in rows.values() for op in row['session_operations']
                         if op['role'] == 'reference_data')
        reference.update(role='executable', evidence_sha256='1' * 64)
        self.assertEqual(verifier.check_historical_coverage(rows.values()), result)
        rows[1]['session_operations'][0]['role'] = 'reference_data'
        with self.assertRaisesRegex(EvidenceError, 'usestrix/strix'):
            verifier.check_historical_coverage(rows.values())

    def test_current_receipt_column_preserves_each_role_field_and_digest(self):
        self.assertEqual(renderer.current_receipts([]), '—')
        operations = [{'role': 'reference_data', 'receipt': 'source', 'evidence_sha256': '1' * 64},
                      {'role': 'executable', 'receipt': 'code', 'evidence_sha256': '2' * 64}]
        self.assertEqual(renderer.current_receipts(operations),
                         f"Referencia · `source` · `{'1' * 64}` / Ejecución · `code` · `{'2' * 64}`")

    def test_acceptance_rejects_repeat_checkout_before_reading_its_data(self):
        act = {'schema_version': 1, 'same_host': True, 'runs': [
            {'id': name, 'checkout': 'single/checkout'} for name in ('first', 'second')]}
        with TemporaryDirectory() as tmp, patch.object(renderer, 'ROOT', Path(tmp)):
            folder = Path(tmp) / renderer.DOSSIER
            folder.mkdir(parents=True)
            (folder / 'acceptance.json').write_bytes(canonical(act))
            with self.assertRaisesRegex(EvidenceError, 'distinct checkouts'):
                renderer.accepted_markdown()

    def test_unverified_publication_or_truncated_output_cannot_render_acceptance(self):
        # Deliberately incomplete native run. The compressed bytes, result metadata and
        # manifest agree, so an implementation that compared only hashes would admit it.
        archived = (ROOT / 'superhunter/product_supply/native-session-70.json').read_bytes()
        raw = verifier.unpack(archived)
        result = {'commit': 'f' * 40, 'tree': 'a' * 40, 'returncode': 0, 'responses': len(raw.splitlines()),
                  'bytes': len(raw), 'sha256': verifier.sha(raw), 'clean_after': True}
        inputs = {'checkout_clean_before': True, 'commit': result['commit'], 'tree': result['tree'],
                  'argv': list(renderer.PORTABLE_ARGV)}
        record = {'id': 'first', 'checkout': 'first/checkout'}
        with TemporaryDirectory() as tmp, patch.object(renderer, 'ROOT', Path(tmp)):
            folder = Path(tmp) / renderer.DOSSIER / 'first'
            folder.mkdir(parents=True)
            for filename, data, field in [('run-inputs.json', canonical(inputs), 'inputs_sha256'),
                                          ('result.json', canonical(result), 'result_sha256'),
                                          ('session.json', archived, 'archive_sha256')]:
                (folder / filename).write_bytes(data)
                record[field] = verifier.sha(data)
            with self.assertRaisesRegex(EvidenceError, 'run result'):
                renderer.run_evidence(record, 'first')
            record['archive_sha256'] = '0' * 64
            with self.assertRaisesRegex(EvidenceError, 'dossier digest'):
                renderer.run_evidence(record, 'first')

    def test_producer_is_checked_in_git_and_missing_shallow_objects_have_a_diagnosis(self):
        import subprocess

        def git(*args):
            return subprocess.check_output(['git', '-C', str(ROOT), *args])
        commit = git('rev-parse', 'HEAD').decode().strip()
        tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
        inputs = {'git_source_tree': git('rev-parse', 'HEAD:upstream').decode().strip(),
                  'native_contract_sha256': verifier.sha(git('show', 'HEAD:superhunter/product_supply/native-capability-contracts.json'))}
        renderer.require_producer(commit, tree, inputs, 'accounting')
        with self.assertRaisesRegex(EvidenceError, 'selected acceptance profile'):
            renderer.require_producer(commit, tree, inputs, 'core-eight')
        with self.assertRaisesRegex(EvidenceError, 'tree differs'):
            renderer.require_producer(commit, '0' * 40, inputs, 'accounting')
        with self.assertRaisesRegex(EvidenceError, 'producer Git objects unavailable'):
            renderer.require_producer('0' * 40, tree, inputs, 'accounting')

    def test_two_identical_historical_transcripts_cannot_be_promoted_by_the_renderer(self):
        # Even if a launcher reported two successful jobs, the strict session verifier
        # must independently enforce the current producer/operation requirements.
        act = {'schema_version': 1, 'same_host': True, 'runs': [
            {'id': n, 'checkout': n + '/checkout', 'result_sha256': n} for n in ('first', 'second')]}
        result = {'commit': '1' * 40, 'tree': '2' * 40, 'sha256': verifier.sha(self.archive)}
        recorded = [({'raw_run_inputs_sha256': n}, result, self.archive) for n in ('first', 'second')]
        with patch.object(renderer, 'read_artifact', return_value=canonical(act)), \
                patch.object(renderer, 'run_evidence', side_effect=recorded), \
                self.assertRaisesRegex(EvidenceError, 'incomplete consolidated session'):
            renderer.accepted_markdown()

    def test_latest_dossier_does_not_fall_back_if_accounting_is_incomplete(self):
        with TemporaryDirectory() as tmp, patch.object(renderer, 'ROOT', Path(tmp)):
            self.assertEqual(renderer.selected_profile('latest'), 'core-eight')
            core = Path(tmp) / renderer.DOSSIER
            core.mkdir(parents=True)
            (core / 'acceptance.json').write_bytes(canonical({'schema_version': 0}))
            expanded = Path(tmp) / renderer.ACCOUNTING_DOSSIER
            expanded.mkdir()
            self.assertEqual(renderer.selected_profile('latest'), 'accounting')
            with self.assertRaises(FileNotFoundError):
                renderer.accepted_markdown()
            with self.assertRaisesRegex(EvidenceError, 'two same-host'):
                renderer.accepted_markdown('core-eight')
            expanded.rmdir()
            expanded.symlink_to('missing-dossier')
            self.assertEqual(renderer.selected_profile('latest'), 'accounting')
            with self.assertRaises(OSError):
                renderer.accepted_markdown()

    def test_renaming_a_historical_dossier_does_not_promote_its_transcript_to_accounting(self):
        act = {'schema_version': 1, 'same_host': True, 'runs': [
            {'id': n, 'checkout': n + '/checkout', 'result_sha256': n} for n in ('first', 'second')]}
        result = {'commit': '1' * 40, 'tree': '2' * 40, 'sha256': verifier.sha(self.archive)}
        recorded = [({'raw_run_inputs_sha256': n}, result, self.archive) for n in ('first', 'second')]
        with patch.object(renderer, 'read_artifact', return_value=canonical(act)), \
                patch.object(renderer, 'run_evidence', side_effect=recorded), \
                patch.object(verifier, 'verify', wraps=verifier.verify) as check, \
                self.assertRaises(EvidenceError):
            renderer.accepted_markdown('accounting')
        check.assert_called_once_with(self.archive, result['sha256'], require_accounting=True)

    def test_resealed_command_with_extra_flag_missing_input_or_alternate_entry_is_rejected(self):
        argv = list(renderer.PORTABLE_ARGV)
        module = argv.index('superhunter.tools.catalog_session')
        options = argv.index('--source-references')
        candidates = [
            [*argv, '--net'], argv[:options] + argv[options + 2:],
            argv[:module] + ['unreviewed.entry'] + argv[module + 1:],
            argv[:-1] + ['/different/bundle'], [argv[1], argv[0], *argv[2:]],
        ]
        with TemporaryDirectory() as tmp, patch.object(renderer, 'ROOT', Path(tmp)):
            folder = Path(tmp) / renderer.DOSSIER / 'first'
            folder.mkdir(parents=True)
            for modified in candidates:
                data = canonical({'argv': modified})
                (folder / 'run-inputs.json').write_bytes(data)
                record = {'id': 'first', 'checkout': 'first/checkout', 'inputs_sha256': verifier.sha(data)}
                with self.subTest(argv=modified), self.assertRaisesRegex(EvidenceError, 'reviewed portable argv'):
                    renderer.run_evidence(record, 'first')

    def test_act_requires_exact_recomputed_verdict_and_each_mutation_explanation(self):
        # This control checks only the act comparator. Native acceptance is verified separately.
        verified = native_verifier.verify(self.archive)
        controls = {'changed_receipt': 'receipt differs', 'removed_operation': 'missing operation'}
        complete = {'independent_verification': verified, 'refuted_mutations': controls}
        with patch.object(verifier, 'negative_controls', return_value=controls) as recompute:
            renderer.check_act_verdict(complete, verified, self.archive)
            recompute.assert_called_once_with(self.archive)
            for forged_verdict in (None, {**verified, 'session': 200}, {**verified, 'original_vulnerabilities_confirmed': False}):
                with self.subTest(verdict=forged_verdict), self.assertRaisesRegex(EvidenceError, 'recomputed verdict'):
                    renderer.check_act_verdict({**complete, 'independent_verification': forged_verdict},
                                               verified, self.archive)
            for claims in (None, {'changed_receipt': 'receipt differs'}, {**controls, 'changed_receipt': 'different'},
                           {**controls, 'invented': 'passed'}):
                with self.subTest(claims=claims), self.assertRaisesRegex(EvidenceError, 'recomputed controls'):
                    renderer.check_act_verdict({**complete, 'refuted_mutations': claims}, verified, self.archive)
