"""Retention decisions over real private archives; no purge or expiry inference."""
import copy
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import bundle_recovery as recovery, portable_copy as portable, preserved_index as index, preserved_retention as retention, quality, safe_io


class PreservedRetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name); template = cls.base / 'template'; template.mkdir()
        archives = template / 'archives'; archives.mkdir(); records = []
        cls.digest = quality.sha(safe_io.canonical(quality.source_snapshot()))
        for name, complete, aliases in [('clean', True, ['a-clean', 'b-clean', 'z-clean']),
                                        ('incomplete', False, ['c-incomplete', 'd-incomplete'])]:
            source = cls.base / (name + '-source')
            if complete: safe_io.write_new_bundle(source, {'data.bin': b'private-retention-payload'})
            else:
                source.mkdir(); (source / 'data.bin').write_bytes(b'private-retention-payload')
            saved = cls.base / (name + '-saved'); input_anchor = recovery.inspect(source)['input_anchor']
            preserved = recovery.preserve(source, saved, source_digest=cls.digest, input_anchor=input_anchor)
            archive = cls.base / (name + '.zip')
            result = portable.export(saved, archive, source_digest=cls.digest, input_anchor=input_anchor,
                                     recovery_anchor=preserved['recovery_anchor'], include_private_bytes=True)
            for alias in aliases:
                shutil.copyfile(archive, archives / (alias + '.zip'))
                records.append({'id': alias, 'file': alias + '.zip', **{key: result[key] for key in index.PINS}})
        records.sort(key=lambda row: row['id'])
        manifest = cls.base / 'manifest.json'; manifest.write_bytes(safe_io.canonical(
            {'schema_version': 1, 'profile': index.MANIFEST_PROFILE, 'archives': records}))
        cls.manifest_anchor = quality.sha(manifest.read_bytes())
        result = index.build(manifest, archives, template / 'index', source_digest=cls.digest, manifest_anchor=cls.manifest_anchor)
        cls.index_anchor = result['index_anchor']; cls.template = template

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root = Path(temp.name)
        shutil.copytree(self.template / 'archives', self.root / 'archives'); shutil.copytree(self.template / 'index', self.root / 'index')
        self.archives = self.root / 'archives'; self.bundle = self.root / 'index'; self.out = self.root / 'retention'
        self.policy_file = self.root / 'private-policy.json'
        self.policy = {'schema_version': 1, 'profile': retention.POLICY_PROFILE, 'minimum_copies_per_archive': 1,
                       'retain_ids': [], 'maximum_retained_bytes': index.MAX_TOTAL_BYTES,
                       'allow_review_of_incomplete_duplicates': False}
        self.save_policy()

    def save_policy(self):
        self.policy_file.write_bytes(safe_io.canonical(self.policy)); self.policy_anchor = quality.sha(self.policy_file.read_bytes())

    def context(self):
        return {'source_digest': self.digest, 'manifest_anchor': self.manifest_anchor,
                'index_anchor': self.index_anchor, 'policy_anchor': self.policy_anchor}

    def create(self, **changes):
        return retention.create(**{'bundle': self.bundle, 'archive_root': self.archives, 'policy': self.policy_file,
                                   'out': self.out, **self.context(), **changes})

    def verify(self, **changes):
        return retention.verify(**{'bundle': self.bundle, 'archive_root': self.archives, 'report': self.out,
                                   'report_anchor': quality.sha((self.out / 'COMPLETE.json').read_bytes()), **self.context(), **changes})

    def report(self): return json.loads((self.out / 'retention.json').read_bytes())

    def reseal(self, root):
        marker = {'schema_version': 1, 'sha256': {p.name: quality.sha(p.read_bytes()) for p in root.iterdir() if p.name != 'COMPLETE.json'}}
        (root / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))

    def mutate_report(self, change):
        report = self.report(); change(report); (self.out / 'retention.json').write_bytes(safe_io.canonical(report)); self.reseal(self.out)

    def cli(self, command, **changes):
        args = [sys.executable, '-B', '-m', 'superhunter', command]
        for key, value in {'bundle': self.bundle, 'archive_root': self.archives, **self.context(), **changes}.items():
            args.extend(['--' + key.replace('_', '-'), str(value)])
        return subprocess.run(args, cwd=quality.ROOT.parent, capture_output=True, timeout=30)

    def test_exact_duplicates_reviewed_incomplete_copies_kept(self):
        result = self.create(); self.assertEqual(result['state'], 'RETENTION_REQUIREMENTS_SATISFIED')
        self.assertEqual(result['summary']['retained_entries'], 3)
        self.assertEqual(result['summary']['reviewable_duplicate_entries'], 2)
        decisions = {r['id']: r['decision'] for r in self.report()['decisions']}
        self.assertEqual(decisions['a-clean'], 'RETAIN_MINIMUM_COPIES')
        self.assertEqual(decisions['b-clean'], 'REVIEW_EXACT_DUPLICATE')
        self.assertEqual(decisions['c-incomplete'], 'RETAIN_INCOMPLETE_CAPTURE')
        self.assertEqual(self.verify()['summary'], result['summary'])
        for name in retention.LIMITS: self.assertIs(result[name], False)

    def test_explicit_hold_has_priority_over_alias_order(self):
        self.policy['retain_ids'] = ['z-clean']; self.save_policy(); self.create()
        decisions = {r['id']: r['decision'] for r in self.report()['decisions']}
        self.assertEqual(decisions['z-clean'], 'RETAIN_EXPLICIT_ID')
        self.assertEqual(decisions['a-clean'], 'REVIEW_EXACT_DUPLICATE')

    def test_multiple_holds_are_not_reduced_to_minimum(self):
        self.policy['retain_ids'] = ['a-clean', 'b-clean', 'z-clean']; self.save_policy()
        self.assertEqual(self.create()['summary']['retained_entries'], 5)

    def test_incomplete_duplicate_review_requires_explicit_true(self):
        self.policy['allow_review_of_incomplete_duplicates'] = True; self.save_policy()
        r = self.create(); self.assertEqual(r['summary']['retained_entries'], 2)
        self.assertEqual(r['summary']['reviewable_duplicate_entries'], 3)
        self.assertEqual(r['input_counts']['incomplete_unique_archives'], 1)

    def test_two_copy_requirement_retains_two_per_archive(self):
        self.policy['minimum_copies_per_archive'] = 2; self.save_policy()
        self.assertEqual(self.create()['summary']['retained_entries'], 4)

    def test_missing_copies_are_unmet_never_fabricated(self):
        self.policy['minimum_copies_per_archive'] = 3; self.save_policy()
        result = self.create(); self.assertEqual(result['state'], 'RETENTION_REQUIREMENTS_UNMET')
        self.assertEqual(result['summary']['retained_entries'], 5)
        self.assertEqual(result['summary']['missing_copy_entries'], 1)
        self.assertEqual(self.report()['copy_shortfalls'][0]['available_entries'], 2)
        self.assertEqual(len(list(self.archives.iterdir())), 5)

    def test_budget_shortfall_preserves_required_copies(self):
        self.policy['maximum_retained_bytes'] = 1; self.save_policy(); result = self.create()
        self.assertEqual(result['state'], 'RETENTION_REQUIREMENTS_UNMET')
        self.assertEqual(result['summary']['retained_entries'], 3)
        self.assertEqual(result['summary']['budget_excess_bytes'], result['summary']['retained_listed_bytes'] - 1)
        self.assertEqual(self.verify()['state'], 'RETENTION_REQUIREMENTS_UNMET')

    def test_distinct_zip_anchors_not_merged_by_original_inventory(self):
        # Pure decision control: two declared ZIP versions of one inventory.
        rows = json.loads((self.bundle / 'index.json').read_bytes())['archives'][:2]
        rows[1] = {**rows[1], 'archive_anchor': '1' * 64}
        decisions, shortfalls, summary = retention._decisions(rows, self.policy)
        self.assertEqual(summary['distinct_archives_retained'], 2)
        self.assertEqual(summary['distinct_input_inventories_retained'], 1)
        self.assertEqual(summary['reviewable_duplicate_entries'], 0)

    def test_inputs_are_unchanged_and_no_files_deleted(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.create(); self.verify()
        self.assertTrue(all((self.root / path).read_bytes() == raw for path, raw in before.items()))
        self.assertEqual(len(list(self.archives.iterdir())), 5)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        for path in self.out.iterdir(): self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_saved_policy_remains_verifiable_without_external_file(self):
        self.create(); self.policy_file.unlink()
        self.assertEqual(self.verify()['operation'], 'RETENTION_REVIEW_VERIFIED')

    def test_all_external_pins_are_checked(self):
        self.create()
        for key in (*self.context(), 'report_anchor', 'index_source_digest', 'retention_source_digest'):
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify(**{key: '0' * 64})

    def test_changed_or_missing_archive_prevents_planning(self):
        path = self.archives / 'a-clean.zip'; raw = path.read_bytes(); path.write_bytes(raw + b'changed')
        with self.assertRaises(ValueError): self.create()
        path.unlink()
        with self.assertRaises(ValueError): self.create()
        self.assertFalse(self.out.exists())

    def test_signed_looking_resealed_index_counts_do_not_bypass_verification(self):
        p = self.bundle / 'index.json'; value = json.loads(p.read_bytes()); value['counts']['unique_archives'] = 1
        p.write_bytes(safe_io.canonical(value)); self.reseal(self.bundle)
        with self.assertRaisesRegex(ValueError, 'INDEX_CONTENT'):
            self.create(index_anchor=quality.sha((self.bundle / 'COMPLETE.json').read_bytes()))

    def test_resealed_decision_changes_are_rejected(self):
        self.create(); self.mutate_report(lambda r: r['decisions'][0].update(decision='REVIEW_EXACT_DUPLICATE'))
        with self.assertRaisesRegex(ValueError, 'RETENTION_CONTENT'): self.verify()

    def test_resealed_budget_promotion_and_deletion_claim_rejected(self):
        self.policy['maximum_retained_bytes'] = 1; self.save_policy(); self.create(); original = (self.out / 'retention.json').read_bytes()
        for mutate in (lambda r: r.update(state='RETENTION_REQUIREMENTS_SATISFIED'),
                       lambda r: r['limitations'].update(deletion_authorized=True)):
            self.mutate_report(mutate)
            with self.assertRaisesRegex(ValueError, 'RETENTION_CONTENT'): self.verify()
            (self.out / 'retention.json').write_bytes(original); self.reseal(self.out)

    def test_resealed_policy_and_review_changes_rejected(self):
        self.create(); raw = (self.out / 'policy.json').read_bytes()
        (self.out / 'policy.json').write_bytes(raw + b' '); self.reseal(self.out)
        with self.assertRaisesRegex(ValueError, 'RETENTION_POLICY_ANCHOR'): self.verify()
        (self.out / 'policy.json').write_bytes(raw); (self.out / 'REVIEW.md').write_bytes(b'purge everything'); self.reseal(self.out)
        with self.assertRaisesRegex(ValueError, 'RETENTION_CONTENT'): self.verify()

    def test_policy_schema_bounds_unknown_holds_and_duplicate_holds_rejected(self):
        ids = {row['id'] for row in json.loads((self.bundle / 'index.json').read_bytes())['archives']}
        changes = [{'minimum_copies_per_archive': value} for value in (0, 65, True, '1')]
        changes += [{'maximum_retained_bytes': value} for value in (0, index.MAX_TOTAL_BYTES + 1, True)]
        changes += [{'retain_ids': value} for value in (['unknown'], ['a-clean', 'a-clean'], ['z-clean', 'a-clean'], 'a-clean')]
        changes += [{'allow_review_of_incomplete_duplicates': value} for value in (1, None, 'true')]
        changes += [{'extra': True}, {'schema_version': True}, {'profile': 'other'}]
        for change in changes:
            raw = safe_io.canonical({**self.policy, **change})
            with self.subTest(change=change), self.assertRaises(ValueError): retention._policy(raw, quality.sha(raw), ids)

    def test_noncanonical_and_duplicate_json_policy_rejected(self):
        for raw in (self.policy_file.read_bytes() + b' ', b'{"profile":1,"profile":1}'):
            self.policy_file.write_bytes(raw)
            with self.assertRaises(ValueError): self.create(policy_anchor=quality.sha(raw))

    def test_policy_symlink_and_policy_inside_index_rejected(self):
        other = self.root / 'other-policy'; self.policy_file.rename(other); self.policy_file.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): self.create()
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_POLICY_REQUIRED'): self.create(policy=self.bundle / 'index.json')

    def test_existing_output_repository_output_and_overlap_rejected(self):
        self.out.mkdir(); (self.out / 'keep').write_bytes(b'unchanged')
        with self.assertRaises(ValueError): self.create()
        self.assertEqual((self.out / 'keep').read_bytes(), b'unchanged')
        with self.assertRaisesRegex(ValueError, 'REPOSITORY_OVERLAP'): self.create(out=quality.ROOT / 'private-review')
        with self.assertRaisesRegex(ValueError, 'OUTPUT_OVERLAP'): self.create(out=self.bundle / 'review')

    def test_extra_and_pending_output_files_rejected(self):
        self.create()
        for name in ('unexpected', safe_io.PENDING_MARKER):
            p = self.out / name; p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'BUNDLE_INVENTORY'): self.verify()
            p.unlink()

    def test_policy_changed_during_index_check_rejected(self):
        real = index.verify
        def change(*args, **kwargs):
            r = real(*args, **kwargs); self.policy_file.write_bytes(self.policy_file.read_bytes() + b' '); return r
        with patch.object(index, 'verify', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'RETENTION_POLICY_CHANGED'): self.create()
        self.assertFalse(self.out.exists())

    def test_archive_changed_after_index_check_rejected(self):
        real = index.verify
        def change(*args, **kwargs):
            r = real(*args, **kwargs); p = self.archives / 'a-clean.zip'; p.write_bytes(p.read_bytes() + b'changed'); return r
        with patch.object(index, 'verify', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'INDEX_ARCHIVES_CHANGED'): self.create()

    def test_index_changed_after_verification_rejected(self):
        real = index.verify
        def change(*args, **kwargs):
            r = real(*args, **kwargs); p = self.bundle / 'REVIEW.md'; p.write_bytes(p.read_bytes() + b'changed'); return r
        with patch.object(index, 'verify', side_effect=change):
            with self.assertRaises(ValueError): self.create()

    def test_late_write_failure_keeps_output_and_returns_no_success(self):
        real = retention.write_new_bundle
        def change(*args, **kwargs):
            real(*args, **kwargs); p = self.archives / 'a-clean.zip'; p.write_bytes(p.read_bytes() + b'changed')
        with patch.object(retention, 'write_new_bundle', side_effect=change):
            with self.assertRaises(ValueError): self.create()
        self.assertTrue(self.out.exists())
        with self.assertRaises(ValueError): self.verify()

    def test_historical_report_identity_does_not_replace_current_reader(self):
        self.create(); self.mutate_report(lambda r: r.update(retention_source_digest='1' * 64))
        with self.assertRaisesRegex(ValueError, 'RETENTION_CONTENT'): self.verify()
        result = self.verify(retention_source_digest='1' * 64)
        self.assertEqual(result['source_digest'], self.digest)
        self.assertEqual(result['retention_source_digest'], '1' * 64)
        with self.assertRaisesRegex(ValueError, 'INDEX_SOURCE'): self.verify(source_digest='1' * 64, retention_source_digest='1' * 64)

    def test_collection_budget_checked_before_full_index_verification(self):
        self.policy['maximum_retained_bytes'] = 1; self.save_policy()
        with patch.object(index, 'MAX_TOTAL_BYTES', 1), patch.object(index, 'verify', side_effect=AssertionError('verified')):
            with self.assertRaisesRegex(ValueError, 'RETENTION_TOTAL_BYTES'): self.create()
        self.assertFalse(self.out.exists())

    def test_cli_complete_and_unmet_have_distinct_results(self):
        value = json.loads((self.bundle / 'inputs.json').read_bytes())
        value['archives'] = [row for row in value['archives'] if row['id'].endswith('-clean')]
        manifest = self.root / 'only-clean.json'; manifest.write_bytes(safe_io.canonical(value))
        self.manifest_anchor = quality.sha(manifest.read_bytes()); self.bundle = self.root / 'only-clean-index'
        made = index.build(manifest, self.archives, self.bundle, source_digest=self.digest, manifest_anchor=self.manifest_anchor)
        self.index_anchor = made['index_anchor']
        r = self.cli('review-preserved-retention', policy=self.policy_file, out=self.out)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.policy['maximum_retained_bytes'] = 1; self.save_policy()
        r = self.cli('review-preserved-retention', policy=self.policy_file, out=self.root / 'unmet')
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(json.loads(r.stdout)['state'], 'RETENTION_REQUIREMENTS_UNMET')

    def test_policy_never_uses_zip_timestamps(self):
        self.create(); report = self.report()
        self.assertFalse(report['limitations']['timestamps_used_for_retention'])
        self.assertNotIn('1980', (self.out / 'retention.json').read_text())
        # No age/expiry clause is accepted even if explicitly supplied.
        self.policy['older_than'] = '1980-01-02'; self.save_policy()
        with self.assertRaisesRegex(ValueError, 'POLICY_SCHEMA'): self.create(out=self.root / 'new-review')

    def test_cli_incomplete_and_unmet_are_nonzero_and_private(self):
        r = self.cli('review-preserved-retention', policy=self.policy_file, out=self.out)
        self.assertEqual(r.returncode, 1, r.stdout); result = json.loads(r.stdout)
        r = self.cli('verify-preserved-retention', report=self.out, report_anchor=result['report_anchor'])
        self.assertEqual(r.returncode, 1, r.stdout)
        for private in (str(self.root).encode(), b'private-retention-payload', b'a-clean', b'private-policy'):
            self.assertNotIn(private, r.stdout + r.stderr)
        r = self.cli('verify-preserved-retention', report=self.out, report_anchor='0' * 64)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stdout), {'state': 'PRESERVED_RETENTION_REJECTED'})


if __name__ == '__main__': unittest.main()
