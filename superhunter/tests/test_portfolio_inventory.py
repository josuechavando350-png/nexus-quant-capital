from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import portfolio_inventory as inventory
from superhunter import quality
from superhunter.safe_io import canonical


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in inventory.PORTFOLIO_FILES:
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((inventory.ROOT/name).read_bytes())
        self.path = self.root/'repo_portfolio_50.json'
        self.data = json.loads(self.path.read_text())

    def write(self):
        self.path.write_bytes(canonical(self.data))

    def test_all_fifty_candidates_and_five_mirrors_agree(self):
        result = inventory.load_portfolio(self.root)
        self.assertEqual([row['id'] for row in result['entries']], list(range(1, 51)))
        self.assertEqual(len(result['domains']), 5)
        self.assertEqual(result['status'], 'CATALOGUED_NOT_INTEGRATED')
        self.assertFalse(result['code_ingested'])

    def test_boolean_count_and_version_are_rejected(self):
        for key in ('count', 'schema_version'):
            with self.subTest(key=key):
                original = self.data[key]; self.data[key] = True; self.write()
                with self.assertRaisesRegex(ValueError, 'VERSION_COUNT'): inventory.load_portfolio(self.root)
                self.data[key] = original

    def test_missing_entry_is_rejected(self):
        self.data['entries'].pop(); self.write()
        with self.assertRaisesRegex(ValueError, 'ALL_50_REQUIRED'): inventory.load_portfolio(self.root)

    def test_duplicate_and_reordered_ids_are_rejected(self):
        self.data['entries'][1]['id'] = 1; self.write()
        with self.assertRaisesRegex(ValueError, 'ORDERED_IDENTITIES'): inventory.load_portfolio(self.root)
        self.data['entries'][1]['id'] = 2
        self.data['entries'][0], self.data['entries'][1] = self.data['entries'][1], self.data['entries'][0]
        self.write()
        with self.assertRaisesRegex(ValueError, 'ORDERED_IDENTITIES'): inventory.load_portfolio(self.root)

    def test_boolean_id_is_rejected(self):
        self.data['entries'][0]['id'] = True; self.write()
        with self.assertRaisesRegex(ValueError, 'ORDERED_IDENTITIES'): inventory.load_portfolio(self.root)

    def test_catalog_cannot_promote_itself_to_integrated(self):
        self.data['status'] = 'INTEGRATED'; self.write()
        with self.assertRaisesRegex(ValueError, 'DOCUMENTARY_STATUS'): inventory.load_portfolio(self.root)

    def test_entry_cannot_promote_itself_to_integrated(self):
        self.data['entries'][5]['status'] = 'INTEGRATED'; self.write()
        with self.assertRaisesRegex(ValueError, 'ENTRY_DOCUMENTARY_STATUS'): inventory.load_portfolio(self.root)

    def test_ingestion_flag_must_be_exact_false(self):
        for value in (True, 0, 'false'):
            with self.subTest(value=value):
                self.data['entries'][0]['code_ingested'] = value; self.write()
                with self.assertRaisesRegex(ValueError, 'ENTRY_DOCUMENTARY_STATUS'):
                    inventory.load_portfolio(self.root)

    def test_domain_paths_cannot_select_new_files(self):
        self.data['domains'][0]['path'] = '../../outside.json'; self.write()
        original = inventory.read_artifact; seen = []
        def observe(root, name):
            seen.append(name); return original(root, name)
        with patch.object(inventory, 'read_artifact', side_effect=observe):
            with self.assertRaisesRegex(ValueError, 'DOMAINS'): inventory.load_portfolio(self.root)
        self.assertEqual(set(seen), set(inventory.PORTFOLIO_FILES))

    def test_policy_changes_are_not_accepted_as_permissions(self):
        self.data['policy']['default'] = 'EXECUTE'; self.write()
        with self.assertRaisesRegex(ValueError, 'POLICY'): inventory.load_portfolio(self.root)

    def test_url_must_match_the_declared_github_repository(self):
        for url in ('https://other.example/repo', 'https://github.com/fuzzland/ityfuzz?run=yes',
                    'file:///tmp/code', 'https://github.com/another/repo'):
            with self.subTest(url=url):
                self.data['entries'][0]['url'] = url; self.write()
                with self.assertRaisesRegex(ValueError, 'REPOSITORY_REFERENCE'):
                    inventory.load_portfolio(self.root)

    def test_repository_traversal_and_extra_path_parts_rejected(self):
        for repository in ('../repo', 'owner/..', 'owner/repo/extra', 'owner repo/name'):
            with self.subTest(repository=repository):
                row = self.data['entries'][0]; row['repository'] = repository
                row['url'] = 'https://github.com/' + repository; self.write()
                with self.assertRaisesRegex(ValueError, 'REPOSITORY_REFERENCE'):
                    inventory.load_portfolio(self.root)

    def test_duplicate_repository_case_is_rejected(self):
        row = self.data['entries'][1]
        row['repository'] = self.data['entries'][0]['repository'].upper()
        row['url'] = 'https://github.com/' + row['repository']; self.write()
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_REPOSITORY'): inventory.load_portfolio(self.root)

    def test_unknown_entry_fields_and_priorities_are_rejected(self):
        self.data['entries'][0]['execute'] = True; self.write()
        with self.assertRaisesRegex(ValueError, 'ENTRY_SCHEMA'): inventory.load_portfolio(self.root)
        del self.data['entries'][0]['execute']; self.data['entries'][0]['priority'] = 'P9'; self.write()
        with self.assertRaisesRegex(ValueError, 'PRIORITY'): inventory.load_portfolio(self.root)

    def test_empty_or_oversized_descriptions_are_rejected(self):
        for text in ('', ' ', 'a'*4097):
            self.data['entries'][0]['rationale'] = text; self.write()
            with self.assertRaisesRegex(ValueError, 'ENTRY_TEXT'): inventory.load_portfolio(self.root)

    def test_mirror_must_preserve_all_fields_not_only_ids(self):
        path = self.root/inventory.DOMAINS[0][2]
        value = json.loads(path.read_text()); value['entries'][0]['acceptance_gate'] = 'changed'
        path.write_bytes(canonical(value))
        with self.assertRaisesRegex(ValueError, 'MIRROR_DISAGREEMENT'): inventory.load_portfolio(self.root)

    def test_mirror_cannot_move_an_entry_between_domains(self):
        path = self.root/inventory.DOMAINS[0][2]
        value = json.loads(path.read_text()); value['entries'][-1] = deepcopy(self.data['entries'][10])
        path.write_bytes(canonical(value))
        with self.assertRaisesRegex(ValueError, 'MIRROR_DISAGREEMENT'): inventory.load_portfolio(self.root)

    def test_duplicate_json_key_is_rejected(self):
        raw = self.path.read_text(); self.path.write_text(raw.replace('"count": 50', '"count": 50, "count": 50', 1))
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): inventory.load_portfolio(self.root)

    def test_symlinked_catalog_is_rejected(self):
        external = self.root/'original.json'; self.path.rename(external); self.path.symlink_to(external)
        with self.assertRaises((ValueError, OSError)): inventory.load_portfolio(self.root)

    def test_catalog_change_during_read_is_rejected(self):
        read = inventory.read_artifact; mutated = False
        def changed(root, name):
            nonlocal mutated
            raw = read(root, name)
            if not mutated and name == 'repo_portfolio_50.json':
                mutated = True
                data = json.loads(raw); data['title'] += ' changed'
                (root/name).write_bytes(canonical(data))
            return raw
        with patch.object(inventory, 'read_artifact', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_READ'): inventory.load_portfolio(self.root)


class RegistryBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'inventory'

    def reseal(self):
        (self.root/'COMPLETE.json').write_bytes(canonical({'schema_version': 1, 'sha256': {
            name: quality.sha((self.root/name).read_bytes()) for name in inventory.FILES}}))

    def test_four_registries_keep_ids_counts_and_statuses_separate(self):
        report = inventory.create(self.root)
        self.assertEqual(inventory.verify(self.root, report['source_digest']), report)
        rows = {row['registry_id']: row for row in report['registries']}
        self.assertEqual([row['declared_items'] for row in report['registries']], [27, 50, 25, 50])
        self.assertEqual(rows['external_repository_candidates']['declared_status_counts'], {'CATALOGUED_NOT_INTEGRATED': 50})
        self.assertEqual(rows['internal_capabilities']['declared_status_counts'], {'PARTIAL': 9, 'PLANNED': 24, 'REDESIGN_REQUIRED': 17})
        self.assertEqual(rows['integration_requirements']['declared_status_counts'], {'IMPLEMENTED_BOUNDED': 12, 'PARTIAL': 3, 'PENDING': 12})
        self.assertEqual(rows['research_initiatives']['declared_status_counts'], {'PARTIAL': 5, 'PLANNED': 20})
        self.assertTrue(all(row['implementation_verified_here'] is False for row in report['registries']))

    def test_inventory_does_not_claim_installation_or_global_progress(self):
        report = inventory.create(self.root)
        for key in ('remote_repository_existence_verified', 'external_catalog_promoted',
                    'external_code_ingested_here', 'installation_state_inferred',
                    'license_acceptance_verified', 'qa_evidence_consumed', 'native_execution_performed',
                    'registry_denominators_pooled', 'platform_complete', 'vulnerability_confirmed',
                    'later_lab_evidence_replaces_catalog_states'):
            self.assertIs(report[key], False)
        self.assertIsNone(report['global_progress'])
        self.assertEqual(report['external_domain_mirrors_checked'], 5)

    def test_all_nine_data_sources_are_bound_to_executable_snapshot(self):
        snapshot = quality.source_snapshot()
        report = inventory.create(self.root)
        self.assertEqual(len(report['catalog_sha256']), 9)
        self.assertTrue(all(snapshot[name] == digest for name,digest in report['catalog_sha256'].items()))
        self.assertTrue(set(inventory.PORTFOLIO_FILES) <= set(quality.COMPONENTS['portfolio_inventory']['files']))

    def test_missing_catalog_binding_prevents_creation(self):
        snapshot = quality.source_snapshot(); del snapshot['repo_portfolio_50.json']
        with patch.object(quality, 'source_snapshot', return_value=snapshot):
            with self.assertRaisesRegex(ValueError, 'UNBOUND_CATALOG'): inventory.create(self.root)
        self.assertFalse(self.root.exists())

    def test_resealed_integration_promotion_is_rejected(self):
        report = inventory.create(self.root)
        report['registries'][-1]['declared_status_counts'] = {'INTEGRATED': 50}
        (self.root/'inventory.json').write_bytes(canonical(report)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): inventory.verify(self.root, report['source_digest'])

    def test_resealed_global_percentage_is_rejected(self):
        report = inventory.create(self.root); report['global_progress'] = 100
        (self.root/'inventory.json').write_bytes(canonical(report)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): inventory.verify(self.root, report['source_digest'])

    def test_wrong_source_and_invalid_hash_rejected(self):
        report = inventory.create(self.root)
        with self.assertRaisesRegex(ValueError, 'INVENTORY_SOURCE'): inventory.verify(self.root, '0'*64)
        (self.root/'REVIEW.md').write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError, 'INVENTORY_HASH'): inventory.verify(self.root, report['source_digest'])

    def test_report_mutation_during_replay_is_rejected(self):
        report = inventory.create(self.root); execute = inventory._execute
        def changed(expected):
            result = execute(expected); (self.root/'COMPLETE.json').write_text('{}'); return result
        with patch.object(inventory, '_execute', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'REPORT_CHANGED'): inventory.verify(self.root, report['source_digest'])

    def test_extra_file_and_symlinked_report_rejected(self):
        report = inventory.create(self.root); extra = self.root/'extra.json'; extra.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'INVENTORY_FILES'): inventory.verify(self.root, report['source_digest'])
        extra.unlink(); path = self.root/'inventory.json'; raw = path.read_bytes(); path.unlink()
        outside = Path(self.temp.name)/'outside.json'; outside.write_bytes(raw); path.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)): inventory.verify(self.root, report['source_digest'])

    def test_existing_or_repository_output_rejected(self):
        inventory.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'): inventory.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'): inventory.create(inventory.ROOT/'unwanted-inventory')

    def test_cli_creates_and_verifies_in_separate_processes(self):
        command = [sys.executable, '-B', '-m', 'superhunter']
        made = subprocess.run(command + ['review-registry-inventory','--out',str(self.root)],
            cwd=inventory.ROOT.parent,capture_output=True,text=True,timeout=30)
        self.assertEqual((made.returncode,made.stderr),(0,'')); receipt=json.loads(made.stdout)
        checked = subprocess.run(command + ['verify-registry-inventory','--bundle',str(self.root),
            '--expected-source',receipt['source_digest']],cwd=inventory.ROOT.parent,capture_output=True,text=True,timeout=30)
        self.assertEqual((checked.returncode,checked.stderr),(0,''))
        self.assertEqual(json.loads(checked.stdout),receipt)

    def test_component_and_worker_registration(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        from superhunter.quality_worker import QA_MODULE_GROUPS
        self.assertEqual(sum('test_portfolio_inventory' in group for group in QA_MODULE_GROUPS),1)


if __name__ == '__main__':
    unittest.main()
