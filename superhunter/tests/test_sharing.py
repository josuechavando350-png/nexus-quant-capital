"""Shareable review derivatives; native/fuzz execution is real, QA rows are fixtures.

The separate release check runs the real complete suite. These unit-test
receipts deliberately do not claim authenticated execution of their listed IDs.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_review as fixtures
from superhunter import quality, review, sharing
from superhunter.privacy import REPLACEMENT
from superhunter.safe_io import canonical, strict_json

CANARY = 'SYNTHETIC_SHARED_SECRET_DO_NOT_USE_4829'


class SharingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ReviewTests.setUpClass.__func__(cls)

    _write_qa = fixtures.ReviewTests._write_qa

    def setUp(self):
        fixtures.ReviewTests.setUp(self)
        self.source = self.out
        self.out = self.root / 'shared'
        self.source_result = review.create_review(self.qa, self.lab, self.fuzz, self.source)

    def make(self):
        return sharing.create_shared(self.source, self.out)

    def rewrite(self, root, filename, raw):
        (root / filename).write_bytes(raw)
        marker = strict_json((root / 'COMPLETE.json').read_bytes())
        marker['sha256'][filename] = hashlib.sha256(raw).hexdigest()
        (root / 'COMPLETE.json').write_bytes(canonical(marker))

    def alter(self, filename, fn):
        value = strict_json((self.out / filename).read_bytes())
        fn(value)
        self.rewrite(self.out, filename, canonical(value))

    def test_private_artifacts_never_exported(self):
        result = self.make()
        self.assertEqual(result['status'], 'SHARED_REVIEW_CREATED')
        self.assertTrue(result['source_reverified'])
        self.assertEqual({p.name for p in self.out.iterdir()}, sharing.OUTPUT_FILES | {'COMPLETE.json'})
        self.assertFalse(any(p.name.startswith(('qa--', 'lab--', 'fuzz--')) for p in self.out.iterdir()))
        self.assertFalse(result['original_evidence_included'])
        self.assertFalse(result['producer_authenticated'])

    def test_all_77_checklist_ids_preserved_without_internal_test_names(self):
        self.make()
        data = strict_json((self.out / 'summary.json').read_bytes())
        self.assertEqual([x['id'] for x in data['integration']['items']], [f'B{i:02d}' for i in range(1, 28)])
        self.assertEqual([x['id'] for x in data['capabilities']['items']], list(range(1, 51)))
        self.assertEqual((data['integration']['bounded'], data['integration']['pending']), (12, 12))
        self.assertFalse(any('tests' in x for x in data['integration']['items']))
        self.assertEqual(data['capabilities']['complete'], 0)

    def test_source_originals_are_unchanged(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        self.make()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})
        self.assertEqual(review.verify_review(self.source), self.source_result)

    def test_raw_log_canary_is_not_copied_even_if_unlabelled(self):
        # A legacy review log can legitimately contain arbitrary captured text.
        qa_marker = strict_json((self.source / 'qa--COMPLETE.json').read_bytes())
        raw = ('private unlabelled marker ' + CANARY).encode()
        self.rewrite(self.source, 'qa--tests.log', raw)
        qa_marker['sha256']['tests.log'] = hashlib.sha256(raw).hexdigest()
        self.rewrite(self.source, 'qa--COMPLETE.json', canonical(qa_marker))
        # Regenerate the private review rather than bypass its section/fact checks.
        self.rewrite(self.qa, 'tests.log', raw)
        import shutil
        shutil.rmtree(self.source)
        self.source_result = review.create_review(self.qa, self.lab, self.fuzz, self.source)
        self.make()
        self.assertIn(CANARY.encode(), (self.source / 'qa--tests.log').read_bytes())
        for file in self.out.iterdir():
            self.assertNotIn(CANARY.encode(), file.read_bytes())

    def test_labelled_secrets_in_projected_text_are_redacted(self):
        captured = sharing._capture(self.source, review.ALL_FILES)
        plan = strict_json(captured['milestones.json'])
        plan['items'][0]['boundary'] = 'password=' + CANARY
        captured['milestones.json'] = canonical(plan)
        # Unit projection test only; create_shared never skips the real source verifier.
        files = sharing._project(captured, self.source_result)
        for raw in files.values():
            self.assertNotIn(CANARY.encode(), raw)
        meta = strict_json(files['export.json'])
        self.assertTrue(meta['redaction']['redactions_present'])
        self.assertTrue(meta['manual_review_required'])
        self.assertFalse(meta['redaction']['all_secrets_detected'])

    def test_self_consistency_is_not_source_authentication(self):
        self.make()
        result = sharing.verify_shared(self.out)
        self.assertEqual(result['status'], 'SHARED_REVIEW_CONSISTENT')
        self.assertFalse(result['source_reverified'])
        self.assertFalse(result['producer_authenticated'])
        self.assertFalse(result['production_certified'])

    def test_private_source_reverification_matches_projection(self):
        self.make()
        result = sharing.verify_shared(self.out, self.source)
        self.assertEqual(result['status'], 'SHARED_REVIEW_SOURCE_MATCH')
        self.assertTrue(result['source_reverified'])
        self.assertFalse(result['vulnerability_confirmed'])

    def test_projection_without_source_can_outlive_private_files(self):
        self.make()
        import shutil
        shutil.rmtree(self.source)
        self.assertEqual(sharing.verify_shared(self.out)['status'], 'SHARED_REVIEW_CONSISTENT')
        with self.assertRaises((ValueError, OSError)):
            sharing.verify_shared(self.out, self.source)

    def test_fully_resealed_counts_need_source_to_verify_truth(self):
        self.make()
        data = strict_json((self.out / 'summary.json').read_bytes())
        data['unit_tests'] += 1
        markdown = sharing.render_summary(data)
        self.rewrite(self.out, 'summary.json', canonical(data))
        self.rewrite(self.out, 'SUMMARY.md', markdown.encode())
        self.rewrite(self.out, 'index.html', review.render_html(markdown))
        self.assertFalse(sharing.verify_shared(self.out)['source_reverified'])
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out, self.source)

    def test_source_manifest_binding_cannot_be_reassigned(self):
        self.make()
        self.alter('export.json', lambda v: v.update(source_manifest_sha256='d' * 64))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out, self.source)

    def test_cannot_claim_certification_after_rehash(self):
        self.make()
        for field in ('production_certified', 'producer_authenticated', 'vulnerability_confirmed'):
            with self.subTest(field=field):
                original = (self.out / 'summary.json').read_bytes()
                self.alter('summary.json', lambda v: v.update({field: True}))
                with self.assertRaises(ValueError):
                    sharing.verify_shared(self.out)
                self.rewrite(self.out, 'summary.json', original)

    def test_cannot_claim_secret_detection_is_complete(self):
        self.make()
        self.alter('export.json', lambda v: v['redaction'].update(all_secrets_detected=True))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_extra_summary_field_rejected(self):
        self.make()
        self.alter('summary.json', lambda v: v.update(api_key=CANARY))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_unknown_redaction_metadata_cannot_hold_a_secret(self):
        self.make()
        self.alter('export.json', lambda v: v['redaction']['matches_by_rule'].update({CANARY: 1}))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_bad_policy_fingerprint_rejected(self):
        self.make()
        self.alter('export.json', lambda v: v.update(policy_code_sha256='e' * 64))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_boolean_unit_test_count_rejected(self):
        self.make()
        self.alter('summary.json', lambda v: v.update(unit_tests=True))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_removed_milestone_rejected(self):
        self.make()
        self.alter('summary.json', lambda v: v['integration']['items'].pop())
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_capability_completion_not_earned_by_export(self):
        self.make()
        self.alter('summary.json', lambda v: v['capabilities']['items'][0].update(status='COMPLETE'))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_unredacted_recognizable_value_rejected_even_resealed(self):
        self.make()
        self.alter('summary.json', lambda v: v['integration']['items'][0].update(boundary='password=' + CANARY))
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_plain_unlabelled_text_is_not_promised_secret_free(self):
        self.make()
        data = strict_json((self.out / 'summary.json').read_bytes())
        data['integration']['items'][0]['boundary'] = CANARY
        sharing._validate_summary(data)
        self.assertTrue(data['manual_review_required'])

    def test_rendered_html_cannot_inject_active_content(self):
        self.make()
        data = strict_json((self.out / 'summary.json').read_bytes())
        data['integration']['items'][0]['boundary'] = '<script>alert(1)</script> ![img](https://x.invalid/a)'
        markdown = sharing.render_summary(data)
        self.assertNotIn('<script>', markdown)
        self.assertNotIn('![img]', markdown)
        html = review.render_html(markdown)
        self.assertNotIn(b'<script>', html)
        self.assertNotIn(b'<img ', html)
        self.assertIn(b"default-src 'none'", html)

    def test_ansi_control_sequences_rejected(self):
        self.make()
        data = strict_json((self.out / 'summary.json').read_bytes())
        data['integration']['items'][0]['boundary'] = '\x1b[2J'
        with self.assertRaises(ValueError):
            sharing.render_summary(data)

    def test_private_artifact_changed_without_rehash_blocks_export(self):
        (self.source / 'qa--tests.log').write_text('changed')
        with self.assertRaises(ValueError):
            self.make()
        self.assertFalse(self.out.exists())

    def test_failed_source_verifier_blocks_any_output(self):
        with patch('superhunter.review.verify_review', side_effect=ValueError('invalid')):
            with self.assertRaises(ValueError):
                self.make()
        self.assertFalse(self.out.exists())

    def test_source_mutation_during_verification_aborts(self):
        original = sharing._verify_captured
        def mutate(captured):
            result = original(captured)
            (self.source / 'REVIEW.md').write_text('changed during verification')
            return result
        with patch('superhunter.sharing._verify_captured', side_effect=mutate):
            with self.assertRaises(ValueError):
                self.make()
        self.assertFalse(self.out.exists())

    def test_source_code_change_during_projection_aborts(self):
        original = sharing._project
        old_snapshot = quality.source_snapshot()
        def project(*args):
            result = original(*args)
            self.snapshot_patch = patch('superhunter.quality.source_snapshot', return_value={**old_snapshot, 'changed.py': 'a' * 64})
            self.snapshot_patch.start()
            self.addCleanup(self.snapshot_patch.stop)
            return result
        with patch('superhunter.sharing._project', side_effect=project), self.assertRaises(ValueError):
            self.make()
        self.assertFalse(self.out.exists())

    def test_extra_private_files_fail_instead_of_being_packaged(self):
        (self.source / 'credentials.txt').write_text(CANARY)
        with self.assertRaises(ValueError):
            self.make()
        self.assertFalse(self.out.exists())

    def test_extra_public_file_is_rejected(self):
        self.make()
        (self.out / 'untracked.txt').write_text(CANARY)
        with self.assertRaises(ValueError):
            sharing.verify_shared(self.out)

    def test_symlink_source_directory_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            sharing.create_shared(alias, self.out)

    def test_symlink_private_artifact_rejected(self):
        item = self.source / 'qa--tests.log'
        raw = item.read_bytes(); item.unlink()
        external = self.root / 'external.log'; external.write_bytes(raw)
        item.symlink_to(external)
        with self.assertRaises((OSError, ValueError)):
            self.make()

    def test_source_total_limit_enforced(self):
        with patch('superhunter.sharing.MAX_TOTAL_BYTES', 10), self.assertRaises(ValueError):
            self.make()
        self.assertFalse(self.out.exists())

    def test_existing_export_is_never_overwritten(self):
        self.make()
        before = (self.out / 'COMPLETE.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.make()
        self.assertEqual((self.out / 'COMPLETE.json').read_bytes(), before)

    def test_nested_output_rejected(self):
        with self.assertRaises(ValueError):
            sharing.create_shared(self.source, self.source / 'shared')
        self.assertFalse((self.source / 'shared').exists())

    def test_output_in_checkout_rejected(self):
        bad = quality.ROOT / 'private-output-test'
        with self.assertRaises(ValueError):
            sharing.create_shared(self.source, bad)
        self.assertFalse(bad.exists())

    def test_export_permissions_remain_private_until_human_shares(self):
        self.make()
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        for p in self.out.iterdir():
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_no_network_or_child_process(self):
        with patch('socket.socket', side_effect=AssertionError('network')), patch('subprocess.run', side_effect=AssertionError('child')):
            self.make()
            self.assertTrue(sharing.verify_shared(self.out, self.source)['source_reverified'])

    def test_cli_roundtrip_via_main_entrypoint(self):
        base = Path(__file__).resolve().parents[2]
        commands = [['share-review', '--review', str(self.source), '--out', str(self.out)],
                    ['verify-shared', '--bundle', str(self.out), '--review', str(self.source)]]
        for args in commands:
            proc = subprocess.run([sys.executable, '-B', '-m', 'superhunter', *args], cwd=base,
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(json.loads(proc.stdout)['source_reverified'])

    def test_cli_diagnostics_never_echo_private_paths(self):
        with patch('sys.stdout', new_callable=io.StringIO) as stream:
            code = sharing.main(['verify-shared', '--bundle', str(self.root / CANARY)])
        self.assertEqual(code, 2)
        self.assertNotIn(CANARY, stream.getvalue())

    def test_all_public_argument_routes_use_private_diagnostics(self):
        base = Path(__file__).resolve().parents[2]
        for command in ('share-review', 'verify-shared', 'review', 'verify-review', 'fuzz-lab', 'verify-fuzz'):
            with self.subTest(command=command):
                proc = subprocess.run([sys.executable, '-B', '-m', 'superhunter', command, '--not-valid', CANARY],
                                      cwd=base, capture_output=True, text=True, timeout=30)
                self.assertEqual(proc.returncode, 2)
                self.assertNotIn(CANARY, proc.stdout + proc.stderr)

    def test_quality_graph_contains_sharing_and_mandatory_checks(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        self.assertEqual(quality.COMPONENTS['sharing']['depends'], ['review', 'privacy'])
        self.assertIn('sharing', quality.COMPONENTS['entrypoints']['depends'])
        self.assertIn('test_sharing.SharingTests.test_private_artifacts_never_exported', quality.REQUIRED_TESTS)
        self.assertIn('sharing', quality.catalog()['items'][46]['components'])

    def test_export_is_deterministic_for_same_verified_source(self):
        self.make()
        other = self.root / 'other-export'
        sharing.create_shared(self.source, other)
        self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()},
                         {p.name: p.read_bytes() for p in other.iterdir()})


if __name__ == '__main__':
    unittest.main()
