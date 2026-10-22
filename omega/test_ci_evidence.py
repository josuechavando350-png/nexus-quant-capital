"""Real retained capture plus adversarial mutations; mutations are not evidence."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch

from ci_evidence import (ARCHIVE_PATH, PIN_PATH, PRODUCER, ROOT, MAX_ARCHIVE,
    MAX_MEMBER, JOBS, load_pin, unpack, verify_capture, verify_metadata, verify_log,
    verify_replay_steps, parse_log)
from integrity import canonical, digest
from pft_source_binding import FALSE_AUTHORITY


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = load_pin()
        cls.archive = ARCHIVE_PATH.read_bytes()
        cls.members = unpack(cls.archive, cls.pin["members"])
        cls.jobs = verify_metadata(cls.members, cls.pin)

    def changed_metadata(self, name, mutate):
        members = dict(self.members)
        value = json.loads(members[name + ".json"])
        mutate(value)
        members[name + ".json"] = canonical(value)
        return members

    def reject_metadata(self, name, mutate):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            verify_metadata(self.changed_metadata(name, mutate), self.pin)

    def mutate_evidence(self, stage, name, mutate, rehash=True):
        rows = self.members[stage + ".log"].decode().splitlines(keepends=True)
        for i, line in enumerate(rows):
            if ' OMEGA_H2_EVIDENCE ' not in line:
                continue
            prefix, payload = line.split('OMEGA_H2_EVIDENCE ', 1)
            record = json.loads(payload)
            if record['name'] != name:
                continue
            mutate(record['value'])
            if rehash:
                record['sha256'] = digest(canonical(record['value']))
            rows[i] = prefix + 'OMEGA_H2_EVIDENCE ' + json.dumps(record) + '\n'
            return ''.join(rows).encode()
        raise AssertionError('missing fixture evidence')

    def reject_evidence(self, stage, name, mutate, rehash=True):
        raw = self.mutate_evidence(stage, name, mutate, rehash)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            verify_log(raw, self.jobs[stage], stage)

    def repack(self, mutate):
        entries = []
        with zipfile.ZipFile(io.BytesIO(self.archive)) as z:
            for info in z.infolist():
                entries.append([copy.copy(info), z.read(info)])
        mutate(entries)
        out = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(out, 'w') as z:
                for info, data in entries:
                    z.writestr(info, data)
        return out.getvalue()

    def test_real_capture_verifies_without_minting_authority(self):
        report = verify_capture()
        self.assertEqual(report['status'], 'PINNED_CI_CAPTURE_VERIFIED')
        self.assertEqual(report['producer_commit'], PRODUCER)
        self.assertEqual([report['stages'][s]['commitments_verified'] for s in JOBS], [29, 25])
        self.assertEqual(report['stages']['replay']['replay_steps'], 16)
        self.assertFalse(report['artifact_authenticated'])
        self.assertIsNone(report['artifact_id'])
        for key in FALSE_AUTHORITY:
            self.assertIs(report[key], False)
        for key in ('new_execution_performed', 'new_acquisition_performed', 'source_seed_reauthenticated'):
            self.assertIs(report[key], False)
        expected = digest(canonical({k:v for k,v in report.items() if k != 'report_commitment_sha256'}))
        self.assertEqual(report['report_commitment_sha256'], expected)

    def test_consumer_refuses_to_borrow_run_for_new_head(self):
        with self.assertRaisesRegex(ValueError, 'wrong_expected_producer'):
            verify_capture(expected_producer='a' * 40)

    def test_altered_archive_rejected_before_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'capture.zip'
            path.write_bytes(self.archive[:-1] + bytes([self.archive[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, 'archive_digest'):
                verify_capture(archive=path)

    def test_changed_pin_cannot_authorize_changed_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pin.json'
            path.write_bytes(canonical({**self.pin, 'archive_sha256': '0' * 64}))
            with self.assertRaisesRegex(ValueError, 'capture_pin_changed'):
                verify_capture(pin_path=path)

    def test_symlink_archive_or_pin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for filename, target, argument in [('archive', ARCHIVE_PATH, 'archive'), ('pin', PIN_PATH, 'pin_path')]:
                link = Path(tmp) / filename
                link.symlink_to(target)
                with self.assertRaisesRegex(ValueError, 'symlink_input'):
                    verify_capture(**{argument: link})

    def test_missing_git_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                verify_capture(repo=Path(tmp))

    def test_zip_duplicate_missing_and_unknown_members_rejected(self):
        mutations = [lambda e: e.append(e[0]), lambda e: e.pop(),
                     lambda e: setattr(e[0][0], 'filename', 'unknown.json')]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'archive_inventory'):
                unpack(self.repack(mutation), self.pin['members'])

    def test_zip_traversal_and_absolute_paths_rejected(self):
        for name in ('../run.json', '/run.json', 'a/../../run.json', 'a\\run.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                unpack(self.repack(lambda e: setattr(e[0][0], 'filename', name)), self.pin['members'])

    def test_zip_symlink_and_special_modes_rejected(self):
        for mode in (0o120777, 0o060600, 0o040755):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                unpack(self.repack(lambda e: setattr(e[0][0], 'external_attr', mode << 16)), self.pin['members'])

    def test_zip_member_hash_rejects_tampered_content(self):
        with self.assertRaisesRegex(ValueError, 'member_digest'):
            unpack(self.repack(lambda e: e[0].__setitem__(1, b'{}')), self.pin['members'])

    def test_zip_size_limits_precede_processing(self):
        with self.assertRaisesRegex(ValueError, 'archive_size_limit'):
            unpack(b'0' * (MAX_ARCHIVE + 1), self.pin['members'])
        raw = self.repack(lambda e: e[0].__setitem__(1, b'0' * (MAX_MEMBER + 1)))
        with self.assertRaisesRegex(ValueError, 'member_size_or_compression'):
            unpack(raw, self.pin['members'])

    def test_wrong_repository_branch_run_and_attempt_rejected(self):
        for key, value in [('head_sha', 'a' * 40), ('head_branch', 'main'), ('id', 1),
                           ('run_attempt', 2), ('run_attempt', True), ('workflow_id', 1),
                           ('event', 'pull_request'), ('path', '.github/workflows/other.yml')]:
            with self.subTest(key=key):
                self.reject_metadata('run', lambda r: r.__setitem__(key, value))
        self.reject_metadata('run', lambda r: r['repository'].__setitem__('id', 1))
        self.reject_metadata('run', lambda r: r['head_repository'].__setitem__('full_name', 'other/repo'))
        self.reject_metadata('run', lambda r: r['repository'].__setitem__('private', True))

    def test_failed_cancelled_or_incomplete_run_rejected(self):
        for value in ('failure', 'cancelled', 'skipped', None):
            self.reject_metadata('run', lambda r: r.__setitem__('conclusion', value))
        self.reject_metadata('run', lambda r: r.__setitem__('status', 'in_progress'))

    def test_tree_and_commit_identity_must_agree(self):
        self.reject_metadata('commit', lambda r: r.__setitem__('sha', 'a' * 40))
        self.reject_metadata('commit', lambda r: r['tree'].__setitem__('sha', 'b' * 40))
        self.reject_metadata('run', lambda r: r['head_commit'].__setitem__('tree_id', 'b' * 40))

    def test_artifact_absence_is_explicit_not_synthetic_authentication(self):
        self.reject_metadata('artifacts', lambda r: r.__setitem__('total_count', True))
        self.reject_metadata('artifacts', lambda r: r.__setitem__('total_count', 1))
        self.reject_metadata('artifacts', lambda r: r.__setitem__('artifacts', [{'id': 1}]))

    def test_metadata_duplicate_json_keys_rejected(self):
        members = {**self.members, 'artifacts.json': b'{"total_count":0,"total_count":0,"artifacts":[]}'}
        with self.assertRaisesRegex(ValueError, 'duplicate_json_key'):
            verify_metadata(members, self.pin)

    def test_missing_duplicate_or_paginated_jobs_rejected(self):
        self.reject_metadata('jobs', lambda r: r.__setitem__('total_count', 3))
        self.reject_metadata('jobs', lambda r: r['jobs'].pop())
        self.reject_metadata('jobs', lambda r: r['jobs'].__setitem__(1, r['jobs'][0]))

    def test_wrong_job_producer_and_runner_rejected(self):
        for key, value in [('head_sha', 'a' * 40), ('run_id', 1), ('run_attempt', 2),
                           ('head_branch', 'miner'), ('labels', ['self-hosted']),
                           ('runner_group_name', 'other'), ('conclusion', 'failure')]:
            with self.subTest(key=key):
                self.reject_metadata('jobs', lambda r: r['jobs'][0].__setitem__(key, value))

    def test_missing_or_skipped_physical_step_rejected(self):
        self.reject_metadata('jobs', lambda r: r['jobs'][0]['steps'].pop(2))
        self.reject_metadata('jobs', lambda r: r['jobs'][0]['steps'][2].__setitem__('conclusion', 'skipped'))

    def test_inverted_job_and_run_windows_rejected(self):
        self.reject_metadata('jobs', lambda r: r['jobs'][0].__setitem__('completed_at', '2026-10-01T00:00:00Z'))
        self.reject_metadata('run', lambda r: r.__setitem__('updated_at', '2026-10-01T00:00:00Z'))
        self.reject_metadata('run', lambda r: r.__setitem__('updated_at', '2099-01-01T00:00:00Z'))

    def test_changed_workflow_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError, 'workflow_bytes'):
            verify_metadata({**self.members, 'workflow.yml': self.members['workflow.yml'] + b'# drift'}, self.pin)

    def test_evidence_hash_tampering_rejected(self):
        self.reject_evidence('forks', 'producer', lambda v: v.__setitem__('commit', 'a' * 40), rehash=False)

    def test_rehashed_producer_substitution_rejected(self):
        for key, value in [('commit', 'a' * 40), ('tree', 'b' * 40), ('run_id', 1),
                           ('artifact_id', 1), ('repository_id', 1)]:
            self.reject_evidence('forks', 'producer', lambda v: v.__setitem__(key, value))

    def test_missing_or_duplicate_evidence_rejected(self):
        raw = self.members['replay.log']
        line = next(l for l in raw.splitlines(keepends=True) if b'OMEGA_H2_EVIDENCE ' in l)
        for changed in (raw.replace(line, b'', 1), raw + line):
            with self.assertRaisesRegex(ValueError, 'evidence_inventory'):
                verify_log(changed, self.jobs['replay'], 'replay')

    def test_failure_timeout_and_unknown_markers_rejected(self):
        for marker in ('OMEGA_H2_FAILED {}', 'OMEGA_H2_UNKNOWN {}'):
            raw = self.members['replay.log'] + ('2026-10-22T22:00:00Z ' + marker + '\n').encode()
            with self.assertRaisesRegex(ValueError, 'runner_marker'):
                verify_log(raw, self.jobs['replay'], 'replay')

    def test_nonzero_and_boolean_command_exit_rejected(self):
        for code in (1, None, False):
            self.reject_evidence('replay', 'command', lambda v: v.__setitem__('exit_code', code))

    def test_economic_authority_in_any_record_rejected(self):
        for key in FALSE_AUTHORITY:
            self.reject_evidence('replay', 'disconnected-replay', lambda v: v.__setitem__(key, True))
        self.reject_evidence('forks', 'stage-complete', lambda v: v.__setitem__('certified_components', 1))

    def test_source_and_destination_isolation_must_hold(self):
        self.reject_evidence('forks', 'isolation-after', lambda v: v.__setitem__('active_omega_workflows', 2))
        self.reject_evidence('forks', 'isolation-before', lambda v: v['legacy_result'].__setitem__('original_objects_checked', False))

    def test_replay_missing_or_false_parity_cannot_pass(self):
        for key in ('source_unchanged', 'current_replay_byte_identical', 'history_replay_byte_identical', 'closeout_byte_identical'):
            self.reject_evidence('replay', 'disconnected-replay', lambda v: v.__setitem__(key, False))

    def test_original_acquisition_time_cannot_be_refreshed(self):
        self.reject_evidence('replay', 'disconnected-replay', lambda v: v.__setitem__('original_observation_at', '2026-10-22T22:00:00Z'))

    def test_replay_source_identity_and_root_rejected(self):
        for key, value in [('source_artifact_id', 1), ('source_commit', 'a'*40), ('source_run_id', 1),
                           ('result_store_root', '0'*64), ('source_store_root', '1'*64)]:
            self.reject_evidence('replay', 'disconnected-replay', lambda v: v.__setitem__(key, value))

    def test_replay_verification_must_fit_job_window(self):
        self.reject_evidence('replay', 'disconnected-replay', lambda v: v.__setitem__('verification_completed_at', '2026-10-23T00:00:00Z'))

    def test_network_namespace_and_routes_rejected(self):
        for key, value in [('network_namespace', 'net:[4026531833]'), ('routable_network', True), ('interfaces', ['lo','eth0'])]:
            self.reject_evidence('replay', 'network-isolation', lambda v: v.__setitem__(key, value))

    def test_replay_step_pair_mismatch_missing_and_nonfinite_rejected(self):
        steps = parse_log(self.members['replay.log'], self.jobs['replay'])[1]
        for mutation in (lambda s: s.pop(), lambda s: s[1].__setitem__('argv', ['other']),
                         lambda s: s[1].__setitem__('state', 'STARTED'),
                         lambda s: s[1].__setitem__('elapsed_seconds', float('nan')),
                         lambda s: s[1].__setitem__('elapsed_seconds', True)):
            changed = copy.deepcopy(steps); mutation(changed)
            with self.assertRaises(ValueError):
                verify_replay_steps(changed)

    def test_fork_provider_dissent_and_unknown_cost_rejected(self):
        self.reject_evidence('forks', 'blastapi-public', lambda v: v['positive'].__setitem__('realized_profit', 1))
        self.reject_evidence('forks', 'blastapi-public', lambda v: v['positive'].__setitem__('flash_premium', None))

    def test_terminal_digest_cannot_refer_to_different_result(self):
        self.reject_evidence('replay', 'stage-complete', lambda v: v.__setitem__('result_sha256', '0'*64))

    def test_rust_counts_and_ignored_tests_rejected(self):
        raw = self.members['replay.log']
        for changed in (raw.replace(b'0 ignored;', b'1 ignored;', 1),
                        raw.replace(b'22 passed;', b'21 passed;', 1)):
            with self.assertRaises(ValueError):
                verify_log(changed, self.jobs['replay'], 'replay')

    def test_report_is_deterministic_and_cli_never_overwrites(self):
        self.assertEqual(verify_capture(), verify_capture())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'; path.write_bytes(b'keep existing')
            env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
            result = subprocess.run([sys.executable, str(ROOT/'omega/ci_evidence.py'), '--report', str(path)],
                                    capture_output=True, env=env)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(path.read_bytes(), b'keep existing')
            self.assertIn(b'CI_CAPTURE_REJECTED', result.stdout)


if __name__ == '__main__':
    unittest.main()
