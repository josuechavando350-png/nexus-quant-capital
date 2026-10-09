"""Local proposal regressions. All network responses below are synthetic mocks."""
import ast
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

import collect_original_metadata as metadata
import index_standalone_d06 as index
import acquire_historical_source as acquisition
import materialize_historical_source as adapter


class NamespaceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.historical = self.home / 'historical-source'; self.historical.mkdir()
        self.stage = self.home / 'result'; self.stage.mkdir()
        self.env = adapter.environment(self.home)
        for method, value in (('getuid', 1001), ('getgid', 1001),
                              ('getresuid', (1001,) * 3), ('getresgid', (1001,) * 3)):
            patcher = mock.patch.object(adapter.os, method, return_value=value)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = mock.patch.object(adapter, 'verify_system_executables')
        self.systems = patcher.start(); self.addCleanup(patcher.stop)
        namespace = {}
        exec(compile(adapter.PRIVILEGE_PROOF, '<reviewed proof function>', 'exec'), namespace)
        self.prove = namespace['privilege_drop_proof']
        self.status = 'Uid: 1001 1001 1001 1001\nGid: 1001 1001 1001 1001\nGroups:\n' + ''.join(
            key + ': 0000000000000000\n' for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')) + 'NoNewPrivs: 1\n'

    def command(self, mode='sudo-drop', **changes):
        values = dict(historical=self.historical, stage=self.stage,
                      parent_network='net:[1]', env=self.env, mode=mode)
        values.update(changes)
        return adapter.isolation_command(**values)

    def test_privileged_prefix_has_no_shell_or_caller_executable(self):
        command = self.command()
        prefix = ['/usr/bin/sudo', '-n', '--', '/usr/bin/unshare', '--net', '--mount',
                  '--propagation', 'private', '--', '/usr/bin/setpriv', '--reuid=1001',
                  '--regid=1001', '--clear-groups', '--bounding-set=-all', '--inh-caps=-all',
                  '--ambient-caps=-all', '--no-new-privs', '--', '/usr/bin/env', '-i']
        self.assertEqual(command[:len(prefix)], prefix)
        self.assertEqual(command[len(prefix):len(prefix) + len(self.env)],
                         [key + '=' + value for key, value in sorted(self.env.items())])
        self.assertEqual(command[len(prefix) + len(self.env):len(prefix) + len(self.env) + 4],
                         ['/usr/bin/python3', '-I', '-B', '-c'])
        self.assertNotIn('bash', command); self.assertNotIn('sh', command)
        self.systems.assert_called_once_with()

    def test_unsafe_fixed_system_binary_is_rejected_before_command(self):
        self.systems.side_effect = ValueError('unsafe system executable or parent')
        with self.assertRaisesRegex(ValueError, 'system executable'): self.command()

    def test_default_mode_preserves_unprivileged_command_without_fallback(self):
        command = self.command(mode='user')
        self.assertEqual(command[:4], ['unshare', '--user', '--map-root-user', '--net'])
        self.assertNotIn('/usr/bin/sudo', command)
        self.systems.assert_not_called()
        self.assertEqual(command[-4], 'user')

    def test_unknown_mode_root_and_mismatched_saved_ids_rejected(self):
        with self.assertRaises(ValueError): self.command(mode='auto')
        for method, value in (('getuid', 0), ('getgid', 0), ('getresuid', (1001, 0, 1001)),
                              ('getresuid', (1001, 1001, 0)), ('getresgid', (1001, 0, 1001)),
                              ('getresgid', (1001, 1001, 0))):
            with self.subTest(method=method, value=value), mock.patch.object(adapter.os, method, return_value=value):
                with self.assertRaises(ValueError): self.command()

    def test_env_injection_path_alias_and_namespace_substitution_rejected(self):
        for key, value in (('PATH', '/tmp'), ('LD_PRELOAD', '/tmp/a.so'), ('PYTHONPATH', '/tmp'),
                           ('BASH_ENV', '/tmp/inject'), ('GIT_CONFIG_GLOBAL', '/tmp/config')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.command(env=dict(self.env, **{key: value}))
        alias = self.home / 'alias'; alias.symlink_to(self.historical)
        for historical in (alias, Path('historical-source'), self.home / 'different'):
            with self.assertRaises(ValueError): self.command(historical=historical)
        for namespace in ('', 'net:[1];id', 'mnt:[1]', 'net:[1]\n'):
            with self.assertRaises(ValueError): self.command(parent_network=namespace)

    def test_privilege_proof_requires_all_four_ids_and_zero_capability_sets(self):
        proof = self.prove(self.status, 1001, 1001)
        self.assertEqual(proof['uids'], [1001] * 4)
        self.assertEqual(proof['groups'], [])
        for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prove(self.status.replace(key + ': 0000000000000000', key + ': 0000000000000001'), 1001, 1001)
        for key in ('Uid', 'Gid'):
            for position in range(4):
                ids = ['1001'] * 4; ids[position] = '0'
                changed = self.status.replace(key + ': 1001 1001 1001 1001', key + ': ' + ' '.join(ids))
                with self.subTest(key=key, position=position), self.assertRaises(ValueError):
                    self.prove(changed, 1001, 1001)

    def test_privilege_proof_rejects_groups_root_nnp_and_bad_status(self):
        for changed in (self.status.replace('Groups:', 'Groups: 0'),
                        self.status.replace('NoNewPrivs: 1', 'NoNewPrivs: 0'),
                        self.status + 'Uid: 1001 1001 1001 1001\n',
                        self.status.replace('NoNewPrivs: 1\n', ''),
                        self.status.replace('CapEff: 0000000000000000', 'CapEff: nothex')):
            with self.assertRaises((ValueError, KeyError)): self.prove(changed, 1001, 1001)
        for uid, gid in ((0, 1001), (1001, 0), (True, 1001), (1001, False)):
            with self.assertRaises(ValueError): self.prove(self.status, uid, gid)

    def test_build_worker_checks_same_proof_before_any_git_or_source_import(self):
        script = (Path(__file__).parent / 'run_standalone_d06_offline.sh').read_text()
        block = script.split("<<'PRIVILEGES'\n", 1)[1].split('\nPRIVILEGES', 1)[0]
        proof_function = next(node for node in ast.parse(block).body if isinstance(node, ast.FunctionDef))
        expected = ast.parse(adapter.PRIVILEGE_PROOF).body[0]
        self.assertEqual(ast.dump(proof_function), ast.dump(expected))
        self.assertLess(script.index('privilege_drop_proof('), script.index('git rev-parse'))
        self.assertIn("network['privilege_drop']", script)
        self.assertIn("network['mount_namespace']", script)

    def test_workflow_drops_privileges_before_bash_and_removes_root_cleanup(self):
        workflow = (Path(__file__).parents[1] / '.github/workflows/nqc-d06-standalone.yml').read_text()
        step = workflow.split('      - name: Disconnected Rust gates and', 1)[1].split('      - name:', 1)[0]
        self.assertIn('/usr/bin/sudo -n -- /usr/bin/unshare --net --mount --propagation private --', step)
        self.assertIn('/usr/bin/setpriv --reuid="$runner_uid" --regid="$runner_gid" --clear-groups', step)
        self.assertIn('--bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs --', step)
        self.assertLess(step.index('/usr/bin/setpriv'), step.index('/usr/bin/env -i'))
        self.assertLess(step.index('/usr/bin/env -i'), step.index('/bin/bash'))
        self.assertNotIn('chown', workflow); self.assertNotIn('safe.directory', workflow)
        self.assertNotIn('sudo bash', workflow)
        self.assertIn('--isolation-mode sudo-drop', workflow)


class SystemExecutableTests(unittest.TestCase):
    def test_only_root_owned_nonwritable_system_chain_is_accepted(self):
        from types import SimpleNamespace
        for owner, mode, rejected in ((0, 0o100755, False), (1001, 0o100755, True),
                                      (0, 0o100775, True), (0, 0o100777, True)):
            with self.subTest(owner=owner, mode=mode), \
                 mock.patch.object(Path, 'resolve', lambda path, **kwargs: path), \
                 mock.patch.object(Path, 'is_file', return_value=True), \
                 mock.patch.object(Path, 'lstat', return_value=SimpleNamespace(st_uid=owner, st_mode=mode)):
                if rejected:
                    with self.assertRaises(ValueError): adapter.verify_system_executables()
                else:
                    adapter.verify_system_executables()


class Response(io.BytesIO):
    def __init__(self, data=b"{}", *, status=200, url=metadata.ENDPOINTS["run"]):
        super().__init__(data)
        self.status, self.url = status, url
        self.headers = {"Date": "Thu, 08 Oct 2026 23:00:00 GMT"}

    def geturl(self):
        return self.url


class MetadataTests(unittest.TestCase):
    def test_fixed_public_api_path_inventory(self):
        self.assertEqual(len(metadata.ENDPOINTS), 4)
        self.assertEqual(metadata.ENDPOINTS["run"], metadata.API + "/actions/runs/36820687233")
        self.assertEqual(metadata.ENDPOINTS["artifact"], metadata.API + "/actions/artifacts/11143129177")
        self.assertTrue(all(url.startswith("https://api.github.com/repos/") for url in metadata.ENDPOINTS.values()))

    def test_official_url_success_preserves_response_bytes(self):
        raw = b'{"id":36820687233}\n'
        opener = mock.Mock()
        opener.open.return_value = Response(raw)
        result, _headers = metadata.read_endpoint(opener, metadata.ENDPOINTS["run"])
        self.assertEqual(result, raw)
        request = opener.open.call_args.args[0]
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(request.full_url, metadata.ENDPOINTS["run"])

    def test_reject_caller_host_path_query_or_plain_http_before_open(self):
        for url in ("https://evil.example", metadata.ENDPOINTS["run"] + "?ref=main",
                    metadata.ENDPOINTS["run"].replace("https:", "http:")):
            opener = mock.Mock()
            with self.assertRaises(ValueError):
                metadata.read_endpoint(opener, url)
            opener.open.assert_not_called()

    def test_redirect_is_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "redirect"):
            metadata.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://github.com")

    def test_denial_and_final_origin_change_are_fail_closed(self):
        for response in (Response(status=403), Response(url="https://evil.example/")):
            opener = mock.Mock(); opener.open.return_value = response
            with self.assertRaises(ValueError):
                metadata.read_endpoint(opener, metadata.ENDPOINTS["run"])

    def test_strict_json_rejects_duplicate_nonfinite_and_nonobject(self):
        for raw in (b'{"id":1,"id":2}', b'{"value":NaN}', b'[]', b'not-json'):
            with self.assertRaises(ValueError):
                metadata.strict_json(raw)

    def test_oversized_response_rejected(self):
        opener = mock.Mock(); opener.open.return_value = Response(b" " * (metadata.LIMIT + 1))
        with self.assertRaisesRegex(ValueError, "oversized"):
            metadata.read_endpoint(opener, metadata.ENDPOINTS["run"])

    def test_collection_receipt_is_explicitly_tokenless_and_noncanonical(self):
        repository = {"id": 1333360261, "full_name": "josuechavando350-png/nexus-engine", "private": False, "url": metadata.API}
        fixtures = {label: {key: "fixture" for key in fields} for label, fields in metadata.FIELDS.items()}
        fixtures["repository"] = repository
        for label, groups in metadata.NESTED_FIELDS.items():
            for key, fields in groups.items():
                fixtures[label][key] = {field: "fixture" for field in fields}
        responses = [(json.dumps(fixtures[label]).encode(), {}) for label in metadata.ENDPOINTS]
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(metadata, "read_endpoint", side_effect=responses):
            output = Path(temp) / "metadata"
            metadata.collect(output)
            receipt = json.loads((output / "metadata-acquisition.json").read_text())
            self.assertFalse(receipt["account_authenticated"])
            self.assertFalse(receipt["token_used"])
            self.assertFalse(receipt["canonical_recertification"])
            self.assertEqual(len(receipt["files"]), 4)
            with self.assertRaises(FileExistsError):
                metadata.collect(output)

    def test_changed_repository_cannot_emit_success_receipt(self):
        for changed in ({"id": True}, {"id": 1333360261, "full_name": "x", "private": False},
                        {"id": 1333360261, "full_name": "josuechavando350-png/nexus-engine", "private": True}):
            with tempfile.TemporaryDirectory() as temp, mock.patch.object(metadata, "read_endpoint", return_value=(json.dumps(changed).encode(), {})):
                output = Path(temp) / "metadata"
                with self.assertRaisesRegex(ValueError, "identity"):
                    metadata.collect(output)
                self.assertFalse((output / "metadata-acquisition.json").exists())

    def test_projection_discards_unrelated_client_homepage_and_actor_data(self):
        repo = {key: "fixture" for key in metadata.FIELDS["repository"]}
        repo.update(homepage="https://client.example", owner={"email": "private@example.test"})
        projected = metadata.project_metadata("repository", repo)
        self.assertEqual(set(projected), set(metadata.FIELDS["repository"]))
        run = {key: "fixture" for key in metadata.FIELDS["run"]}
        for key, fields in metadata.NESTED_FIELDS["run"].items():
            run[key] = {field: "fixture" for field in fields}
            run[key]["homepage"] = "https://client.example"
        run["actor"] = {"email": "private@example.test"}
        projected = metadata.project_metadata("run", run)
        self.assertNotIn("client.example", json.dumps(projected))
        self.assertNotIn("actor", projected)


class ProducerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.head, self.tree = "a" * 40, "b" * 40
        self.event = {"ref": index.PRODUCER_REF, "before": "c" * 40, "after": self.head,
                      "created": False, "deleted": False, "forced": False,
                      "head_commit": {"id": self.head},
                      "repository": {"id": int(index.REPOSITORY_ID), "full_name": index.REPOSITORY}}
        self.environment = {
            "GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": index.REPOSITORY,
            "GITHUB_REF": index.PRODUCER_REF, "GITHUB_REF_TYPE": "branch",
            "GITHUB_REPOSITORY_ID": index.REPOSITORY_ID, "GITHUB_SHA": self.head,
            "GITHUB_WORKFLOW_SHA": self.head,
            "GITHUB_WORKFLOW_REF": index.REPOSITORY + "/" + index.WORKFLOW + "@" + index.PRODUCER_REF,
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
        }

    def test_exact_new_producer_is_bound_separately(self):
        value = index.producer_context(self.environment, self.head, self.tree, self.event)
        self.assertEqual(value["repository_id"], 1411047452)
        self.assertEqual(value["commit"], self.head)
        self.assertEqual(value["tree"], self.tree)
        self.assertEqual(value["event"], "push")
        self.assertEqual(value["ref"], "refs/heads/nqc/d06-standalone-certification")

    def test_wrong_repo_event_workflow_commit_or_run_fails(self):
        for key, bad in {
            "GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": "josuechavando350-png/nexus-engine",
            "GITHUB_REF": "refs/heads/main", "GITHUB_REF_TYPE": "tag",
            "GITHUB_REPOSITORY_ID": "1333360261", "GITHUB_SHA": "c" * 40,
            "GITHUB_WORKFLOW_SHA": "d" * 40, "GITHUB_WORKFLOW_REF": "other@refs/heads/main",
            "GITHUB_RUN_ID": "123; echo hi", "GITHUB_RUN_ATTEMPT": "0",
        }.items():
            changed = copy.deepcopy(self.environment); changed[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                index.producer_context(changed, self.head, self.tree, self.event)

    def test_branch_reference_must_be_exact_dedicated_branch(self):
        for ref in ("refs/tags/release", "refs/heads/", "refs/heads/main", index.PRODUCER_REF + "-other"):
            changed = dict(self.environment, GITHUB_WORKFLOW_REF=index.REPOSITORY + "/" + index.WORKFLOW + "@" + ref)
            with self.assertRaises(ValueError):
                index.producer_context(changed, self.head, self.tree, self.event)

    def test_manual_dispatch_is_not_new_producer_authority(self):
        changed = dict(self.environment, GITHUB_EVENT_NAME="workflow_dispatch")
        with self.assertRaisesRegex(ValueError, "push"):
            index.producer_context(changed, self.head, self.tree, self.event)

    def test_push_payload_is_bound_and_flags_preserved(self):
        value = index.producer_context(self.environment, self.head, self.tree, self.event)
        self.assertEqual(value["push_context"], {key: self.event[key] for key in
                         ("before", "after", "created", "deleted", "forced")})
        created = dict(self.event, before="0" * 40, created=True)
        self.assertTrue(index.producer_context(self.environment, self.head, self.tree, created)["push_context"]["created"])

    def test_followup_push_preserves_actual_reviewed_predecessor(self):
        event = dict(self.event, before="5d415c1acc89130d03119bbafb0ace93001097a6")
        value = index.producer_context(self.environment, self.head, self.tree, event)
        self.assertEqual(value["push_context"]["before"], event["before"])
        self.assertNotEqual(value["push_context"]["before"], "16e352225ba8a6a931834c4edf3d86d9a2924b7d")
        self.assertEqual(value["push_context"]["after"], self.head)

    def test_forced_deleted_wrong_head_and_wrong_branch_push_are_rejected(self):
        for key, value in (("forced", True), ("deleted", True), ("after", "d" * 40),
                           ("ref", "refs/heads/main"), ("before", "main"), ("created", True)):
            changed = dict(self.event); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                index.producer_context(self.environment, self.head, self.tree, changed)

    def test_nonexact_commit_tree_rejected(self):
        for head, tree in (("main", self.tree), (self.head, "HEAD^{tree}"), ("a" * 39, self.tree)):
            with self.assertRaises(ValueError):
                index.producer_context(self.environment, head, tree, self.event)

    def test_full_negative_matrix_count_is_pinned(self):
        self.assertEqual(len(index.NEGATIVES), 22)


class IndexTests(ProducerIdentityTests):
    """Synthetic proof fixtures exercise only the new index, never original authentication."""
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"; self.repo.mkdir()
        self.root = Path(self.temp.name) / "evidence"; self.root.mkdir()
        event_path = Path(self.temp.name) / "event.json"
        event_path.write_text(json.dumps(self.event))
        self.environment["GITHUB_EVENT_PATH"] = str(event_path)
        self.archive = b"SYNTHETIC INDEX UNIT TEST ONLY"
        def git(command, **_kwargs):
            if command[-1] == "HEAD": return self.head
            if command[-1] == "HEAD^{tree}": return self.tree
            if "status" in command: return ""
            raise AssertionError(command)
        for patcher in (mock.patch.object(index.subprocess, "check_output", side_effect=git),
                        mock.patch.object(index, "SOURCE_ARCHIVE_SIZE", len(self.archive)),
                        mock.patch.object(index, "SOURCE_ARCHIVE_SHA256", hashlib.sha256(self.archive).hexdigest())):
            patcher.start(); self.addCleanup(patcher.stop)
        now = datetime.now(timezone.utc)
        self.write("offline-verification.json", {
            "code_commit": self.head, "code_tree": self.tree,
            "source_commit": "a33a012591cd6625ddb921d995bb1bd95b4a5406",
            "source_run_id": 36820687233, "source_artifact_id": 11143129177,
            "source_unchanged": True, "current_replay_byte_identical": True,
            "history_replay_byte_identical": True, "closeout_byte_identical": True,
            "canonical_recertification": False,
            "original_observation_at": (now - timedelta(days=7)).isoformat(),
            "verification_started_at": (now - timedelta(seconds=2)).isoformat(),
            "verification_completed_at": (now - timedelta(seconds=1)).isoformat(),
        })
        self.write("network-isolation.json", {"routable_network": False, "interfaces": ["lo"],
                   "network_namespace": "net:[2]", "parent_network_namespace": "net:[1]"})
        self.write("negative-tests/results.json", {"schema": "nqc-rmc006-replay-negatives-v1",
                   "cases": [{"case": name, "rejected": True, "store_unchanged": True}
                             for name in sorted(index.NEGATIVES)]})
        self.isolation = {
            'routable_network': False, 'interfaces': ['lo'],
            'network_namespace': 'net:[2]', 'parent_network_namespace': 'net:[1]',
            'mount_namespace': 'mnt:[4]', 'parent_mount_namespace': 'mnt:[3]',
            'isolation_mode': 'sudo-drop',
            'privilege_drop': {'schema': 'nqc-privilege-drop-v1', 'caller_uid': 1001, 'caller_gid': 1001,
                'uids': [1001] * 4, 'gids': [1001] * 4, 'groups': [], 'no_new_privs': 1,
                'capabilities': {key: 0 for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')}}}
        self.write('code-gates/build-network-isolation.json', self.isolation)
        self.write('code-gates/replay-network-isolation.json', self.isolation)
        for original, adapter_name, output in (
            ('run_rmc006_recertification.py', 'run_premounted_d06_v1.py', 'runner-identity.json'),
            ('test_rmc006_recertification_replay.py', 'test_premounted_d06_replay_v1.py', 'negative-tests/runner-identity.json')):
            import premounted_d06
            for directory, name in (('ci/nqc-census', original), ('migration', adapter_name), ('migration', 'premounted_d06.py')):
                path = self.repo / directory / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((Path(__file__).parents[1] / directory / name).read_bytes())
            self.write(output, {'schema': 'nqc-prospective-d06-runner-v1', 'method': premounted_d06.METHOD,
                'original_runner_byte_identical': False, 'certification_inherited': False,
                'original_path': 'ci/nqc-census/' + original,
                'original_sha256': hashlib.sha256((self.repo / 'ci/nqc-census' / original).read_bytes()).hexdigest(),
                'adapter_path': 'migration/' + adapter_name,
                'adapter_sha256': hashlib.sha256((self.repo / 'migration' / adapter_name).read_bytes()).hexdigest(),
                'boundary_path': 'migration/premounted_d06.py',
                'boundary_sha256': hashlib.sha256((self.repo / 'migration/premounted_d06.py').read_bytes()).hexdigest(),
                'root_setup_sha256': hashlib.sha256(premounted_d06.ROOT_SETUP.encode()).hexdigest(),
                'source_mount': {'schema': 'nqc-premounted-source-v2', 'method': premounted_d06.METHOD,
                    'read_only': True, 'write_open_errno': 30, 'probe': 'source-directory-O_TMPFILE|O_EXCL',
                    'probe_creates_named_file': False, 'probe_writes_or_truncates_existing': False, 'probe_linkable': False, 'mount_flags': ['ro', 'relatime'],
                    'descendant_mounts': False, 'private_mount': True, 'premount_id': 10, 'readonly_mount_id': 11}})

        receipt = b'{"unit_test": true}\n'
        self.write("historical-source/HISTORICAL-ADAPTER.json", {
            "schema": "nqc-standalone-historical-materialization-v1",
            "status": "HISTORICAL_SOURCE_MATERIALIZED_CONSUMER_BOUND",
            "historical_source": {"commit": index.SOURCE_COMMIT},
            "network_isolation": self.isolation,
            "consumer": {"repository": index.REPOSITORY, "repository_id": int(index.REPOSITORY_ID),
                         "commit": self.head, "tree": self.tree},
            "truth_boundaries": {key: False for key in ("canonical_recertification", "certification_transferred",
                "new_consumer_is_original_descendant", "live_network_fallback", "production_authority")},
            "historical_materialization_receipt": {"sha256": hashlib.sha256(receipt).hexdigest(),
                                                   "preserved_unchanged": True},
        })
        path = self.root / "historical-source/effective-source/MATERIALIZATION.json"
        path.parent.mkdir(); path.write_bytes(receipt)
        self.write("original-seed/source-provenance-after.json", {
            "original_repository": {"full_name": "josuechavando350-png/nexus-engine", "id": 1333360261},
            "original_run": {"id": 36820687233}, "original_artifact": {"id": 11143129177},
            "canonical_recertification": False, "extracted_source_rechecked": True,
        })
        (self.root / "original-seed/source.zip").write_bytes(self.archive)

    def write(self, relative, value):
        path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def mutate(self, relative, function):
        value = json.loads((self.root / relative).read_text()); function(value); self.write(relative, value)

    def run_index(self):
        return index.make_index(self.repo, self.root, self.head, self.tree, self.environment)

    def test_retained_privilege_or_missing_network_proof_prevents_index(self):
        for section in ('historical-source/HISTORICAL-ADAPTER.json', 'code-gates/build-network-isolation.json', 'code-gates/replay-network-isolation.json'):
            original = (self.root / section).read_text()
            for mutate in (
                lambda n: n.update(isolation_mode='user'),
                lambda n: n.update(network_namespace=n['parent_network_namespace']),
                lambda n: n.update(mount_namespace=n['parent_mount_namespace']),
                lambda n: n['privilege_drop'].update(no_new_privs=0),
                lambda n: n['privilege_drop'].update(groups=[1001]),
                lambda n: n['privilege_drop']['capabilities'].update(CapEff=1),
                lambda n: n['privilege_drop']['capabilities'].update(CapBnd=True),
                lambda n: n['privilege_drop'].update(uids=[0] * 4),
            ):
                value = json.loads(original)
                mutate(value['network_isolation'] if section.startswith('historical') else value)
                self.write(section, value)
                with self.assertRaises(ValueError): self.run_index()
                self.assertFalse((self.root / 'evidence-index.json').exists())
            (self.root / section).write_text(original)

    def test_prospective_identity_or_false_readonly_proof_cannot_index(self):
        for path in ('runner-identity.json', 'negative-tests/runner-identity.json'):
            original = (self.root / path).read_text()
            for mutation in (lambda p: p.update(original_runner_byte_identical=True),
                             lambda p: p.update(certification_inherited=True),
                             lambda p: p.update(adapter_sha256='0'*64),
                             lambda p: p.update(boundary_sha256='0'*64),
                             lambda p: p.update(root_setup_sha256='0'*64),
                             lambda p: p['source_mount'].update(write_open_errno=13),
                             lambda p: p['source_mount'].update(probe_creates_named_file=True),
                             lambda p: p['source_mount'].update(probe_writes_or_truncates_existing=True),
                             lambda p: p['source_mount'].update(probe_linkable=True),
                             lambda p: p['source_mount'].update(schema='nqc-premounted-source-v1'),
                             lambda p: p['source_mount'].update(readonly_mount_id=10),
                             lambda p: p['source_mount'].update(mount_flags=['rw'])):
                value = json.loads(original); mutation(value); self.write(path, value)
                with self.assertRaises(ValueError): self.run_index()
                self.assertFalse((self.root / 'evidence-index.json').exists())
            (self.root / path).write_text(original)

    def test_build_and_materializer_caller_ids_must_match(self):
        changed = copy.deepcopy(self.isolation)
        changed['privilege_drop'].update(caller_uid=1002, uids=[1002] * 4)
        self.write('code-gates/build-network-isolation.json', changed)
        with self.assertRaisesRegex(ValueError, 'identity differs'): self.run_index()

    def test_index_preserves_noncanonical_status_and_checks_file_hashes(self):
        result = self.run_index()
        for field in ("final_github_run_verified", "immutable_artifact_metadata_verified",
                      "canonical_recertification", "certification_transfer", "downstream_acceptance",
                      "reviewed_producer_authorization_verified"):
            self.assertIs(result[field], False)
        self.assertIsNone(result["new_artifact_id"])
        for row in result["files"]:
            self.assertEqual(hashlib.sha256((self.root / row["path"]).read_bytes()).hexdigest(), row["sha256"])

    def test_index_never_overwrites_existing_index(self):
        self.run_index()
        before = (self.root / "evidence-index.json").read_bytes()
        with self.assertRaises(ValueError): self.run_index()
        self.assertEqual((self.root / "evidence-index.json").read_bytes(), before)

    def test_missing_negative_case_is_rejected_without_index(self):
        self.mutate("negative-tests/results.json", lambda value: value["cases"].pop())
        with self.assertRaisesRegex(ValueError, "matrix"): self.run_index()
        self.assertFalse((self.root / "evidence-index.json").exists())

    def test_changed_archive_is_rejected_without_index(self):
        (self.root / "original-seed/source.zip").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "archive"): self.run_index()

    def test_changed_materialization_receipt_is_rejected(self):
        (self.root / "historical-source/effective-source/MATERIALIZATION.json").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "receipt"): self.run_index()

    def test_reachable_network_claim_is_rejected(self):
        self.mutate("network-isolation.json", lambda value: value.update(routable_network=True))
        with self.assertRaisesRegex(ValueError, "disconnected"): self.run_index()

    def test_changed_new_consumer_is_rejected(self):
        self.mutate("historical-source/HISTORICAL-ADAPTER.json", lambda value: value["consumer"].update(commit=index.SOURCE_COMMIT))
        with self.assertRaisesRegex(ValueError, "consumer identity"): self.run_index()

    def test_canonical_claim_is_rejected(self):
        self.mutate("offline-verification.json", lambda value: value.update(canonical_recertification=True))
        with self.assertRaisesRegex(ValueError, "canonical"): self.run_index()

    def test_future_verification_time_is_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.mutate("offline-verification.json", lambda value: value.update(verification_completed_at=future))
        with self.assertRaisesRegex(ValueError, "chronology"): self.run_index()

    def test_extra_symlink_is_rejected(self):
        (self.root / "unexpected-link").symlink_to(self.root / "offline-verification.json")
        with self.assertRaisesRegex(ValueError, "nonregular"): self.run_index()


class ExactProducerCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nqc-producer-checkout-test-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name); self.env = acquisition.a.environment(self.work)
        self.source = self.work / "synthetic-source"; self.source.mkdir()
        acquisition.a.git(self.source, "init", "--quiet", "--template=", env=self.env)
        (self.source / "fixture.txt").write_text("baseline\n")
        self.commit(); self.base = acquisition.a.identity(self.source, self.env)[0]
        (self.source / "fixture.txt").write_text("producer\n")
        self.commit(); self.head, self.tree = acquisition.a.identity(self.source, self.env)
        self.repository = {"id": 1411047452, "full_name": acquisition.a.CONSUMER_REPOSITORY,
                           "private": False, "url": acquisition.PRODUCER_API_URL}
        self.fetch_calls = []

    def commit(self):
        acquisition.a.git(self.source, "add", "fixture.txt", env=self.env)
        acquisition.a.git(self.source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                          "commit", "--quiet", "-m", "fixture", env=self.env)

    def acquire(self, output=None, head=None, tree=None, repository=None):
        original_run = acquisition.a.run
        def local_fixture(command, *, cwd, env):
            args = list(command)
            if acquisition.PRODUCER_GIT_URL in args:
                self.fetch_calls.append(args)
                self.assertEqual(args[args.index("--") + 1:],
                                 [acquisition.PRODUCER_GIT_URL, (head or self.head) + ":" + acquisition.PRODUCER_REF])
                self.assertEqual(env["GIT_ALLOW_PROTOCOL"], "https")
                args = [str(self.source) if arg == acquisition.PRODUCER_GIT_URL else
                        "protocol.file.allow=always" if arg == "protocol.https.allow=always" else arg
                        for arg in args]
                env = dict(env, GIT_ALLOW_PROTOCOL="file")
            return original_run(args, cwd=cwd, env=env)
        with mock.patch.object(acquisition, "read_metadata", return_value=repository or self.repository) as read, \
                mock.patch.object(acquisition, "PRODUCER_BASE", self.base), \
                mock.patch.object(acquisition.a, "run", side_effect=local_fixture):
            result = acquisition.acquire_producer(output or self.work / "consumer", head or self.head,
                                                  tree or self.tree)
            read.assert_called_once_with(acquisition.PRODUCER_API_URL, producer=True)
            return result

    def test_clean_copy_uses_exact_objects_without_checkout_metadata(self):
        acquisition.a.git(self.source, "sparse-checkout", "disable", env=self.env)
        acquisition.a.git(self.source, "config", "--local", "--unset-all", "extensions.worktreeConfig", env=self.env)
        metadata = self.source / ".git/config.worktree"
        original = metadata.read_bytes()
        with self.assertRaisesRegex(acquisition.a.AdapterError, "consumer Git metadata"):
            acquisition.a.verify_consumer_git_config(self.source, self.env)
        hooks = self.source / ".git/hooks"; hooks.mkdir(exist_ok=True)
        (hooks / "fixture-hook").write_text("do not copy\n")
        info = self.source / ".git/info"; info.mkdir(exist_ok=True)
        (info / "attributes").write_text("fixture.txt -filter\n")
        consumer = self.acquire()
        self.assertEqual(acquisition.a.identity(consumer, self.env), (self.head, self.tree))
        self.assertEqual((consumer / "fixture.txt").read_text(), "producer\n")
        for rel in ("config.worktree", "commondir", "info/attributes", "hooks/fixture-hook"):
            self.assertFalse((consumer / ".git" / rel).exists(), rel)
        self.assertEqual(metadata.read_bytes(), original)
        acquisition.a.verify_consumer_git_config(consumer, self.env)
        acquisition.a.git(consumer, "merge-base", "--is-ancestor", self.base, self.head, env=self.env)
        acquisition.a.git(consumer, "rev-list", "--objects", "--missing=error", self.head, env=self.env)
        command = self.fetch_calls[0]
        for flag in ("--no-auto-maintenance", "--no-write-commit-graph", "--no-tags",
                     "credential.helper=", "credential.interactive=false", "http.followRedirects=false"):
            self.assertIn(flag, command)
        self.assertNotIn("--depth", command)
        self.assertNotIn("--filter", command)

    def test_invalid_or_partial_identity_fails_before_metadata_or_fetch(self):
        for head, tree in (("main", self.tree), (self.head, None), (None, self.tree),
                           ("0" * 40, self.tree), (self.head, "b" * 39)):
            with self.subTest(head=head, tree=tree), mock.patch.object(acquisition, "read_metadata") as read:
                with self.assertRaisesRegex(acquisition.a.AdapterError, "exact nonzero"):
                    acquisition.acquire_producer(self.work / "bad", head, tree)
                read.assert_not_called()

    def test_changed_repository_is_rejected_before_git_fetch(self):
        with self.assertRaisesRegex(acquisition.a.AdapterError, "repository identity"):
            self.acquire(repository=dict(self.repository, id=1333360261))
        self.assertEqual(self.fetch_calls, [])
        self.assertFalse((self.work / "consumer").exists())

    def test_fetched_tree_mismatch_never_publishes_output(self):
        with self.assertRaisesRegex(acquisition.a.AdapterError, "fetched tree"):
            self.acquire(tree="b" * 40)
        self.assertFalse((self.work / "consumer").exists())

    def test_existing_output_and_parent_alias_are_rejected(self):
        output = self.work / "occupied"; output.mkdir(); (output / "sentinel").write_text("keep")
        with self.assertRaisesRegex(acquisition.a.AdapterError, "already exists"):
            self.acquire(output=output)
        self.assertEqual((output / "sentinel").read_text(), "keep")
        alias = self.work / "alias"; alias.symlink_to(self.work, target_is_directory=True)
        with self.assertRaisesRegex(acquisition.a.AdapterError, "parent aliases"):
            self.acquire(output=alias / "other")

    def test_historical_and_producer_metadata_endpoints_do_not_substitute(self):
        for url, producer in ((acquisition.API_URL, True), (acquisition.PRODUCER_API_URL, False),
                              ("https://evil.example/repo", True)):
            with self.subTest(url=url, producer=producer), mock.patch.object(acquisition.urllib.request, "build_opener") as opener:
                with self.assertRaisesRegex(acquisition.a.AdapterError, "unapproved"):
                    acquisition.read_metadata(url, producer=producer)
                opener.assert_not_called()


class HistoricalFetchCacheTests(unittest.TestCase):
    def captured_command(self, store, environment):
        with mock.patch.object(acquisition.a, "run", return_value=b"") as run:
            acquisition.fetch_source_objects(store, environment)
        command = run.call_args.args[0]
        return command, run.call_args.kwargs["env"]

    def test_fixed_fetch_disables_optional_metadata_without_weakening_transport(self):
        command, environment = self.captured_command(Path("/tmp/fixed-fixture"), {})
        self.assertIn("--no-auto-maintenance", command)
        self.assertIn("--no-write-commit-graph", command)
        self.assertIn("--no-write-fetch-head", command)
        self.assertIn("--no-recurse-submodules", command)
        self.assertIn("protocol.allow=never", command)
        self.assertIn("protocol.https.allow=always", command)
        self.assertIn("credential.helper=", command)
        self.assertIn("credential.interactive=false", command)
        self.assertIn("http.followRedirects=false", command)
        self.assertIn("http.extraHeader=", command)
        self.assertEqual(environment["GIT_ALLOW_PROTOCOL"], "https")
        self.assertEqual(command[command.index("--") + 1:], [acquisition.GIT_URL] +
                         [oid + ":" + ref for ref, oid in acquisition.a.HISTORICAL_REFS.items()])

    def test_real_local_fetch_regression_old_cache_rejected_new_flags_prevent_it(self):
        # Synthetic local Git fixture only. No network or source-authority claim.
        with tempfile.TemporaryDirectory() as name:
            work = Path(name); env = acquisition.a.environment(work)
            source = work / "fixture-source"; source.mkdir()
            acquisition.a.git(source, "init", "--quiet", "--template=", env=env)
            (source / "fixture.txt").write_text("synthetic fixture\n")
            acquisition.a.git(source, "add", "fixture.txt", env=env)
            acquisition.a.git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                              "commit", "--quiet", "-m", "fixture", env=env)
            expected = acquisition.a.git(source, "rev-parse", "HEAD", env=env).decode().strip()
            for controls in (False, True):
                store = work / ("new" if controls else "old"); store.mkdir()
                acquisition.a.git(store, "init", "--quiet", "--template=", env=env)
                command, _ = self.captured_command(store, env)
                prefix = command[:command.index("--")]
                prefix = ["protocol.file.allow=always" if arg == "protocol.https.allow=always" else arg
                          for arg in prefix]
                if not controls:
                    prefix = [arg for arg in prefix if arg not in
                              ("--no-auto-maintenance", "--no-write-commit-graph")]
                # Deliberately request the optional cache and a pack in both
                # cases. Only the new command's negative flags override it.
                prefix[1:1] = ["-c", "fetch.writeCommitGraph=true", "-c", "transfer.unpackLimit=1"]
                acquisition.a.run(prefix + ["--", source, expected + ":refs/evidence/fixture"],
                                  cwd=store, env=dict(env, GIT_ALLOW_PROTOCOL="file"))
                objects = store / ".git/objects"
                unexpected = [str(path.relative_to(objects)) for path in objects.rglob("*") if path.is_file()
                              and not (re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{38}", str(path.relative_to(objects)))
                                       or re.fullmatch(r"pack/pack-[0-9a-f]{40}\.(pack|idx|rev)",
                                                       str(path.relative_to(objects))))]
                if controls:
                    self.assertEqual(unexpected, [])
                    self.assertEqual(acquisition.a.git(store, "rev-parse", "refs/evidence/fixture",
                                     env=env).decode().strip(), expected)
                    acquisition.a.git(store, "fsck", "--full", "--strict", env=env)
                else:
                    self.assertTrue(any(path.startswith("info/commit-graphs/") for path in unexpected))
                    with self.assertRaisesRegex(acquisition.a.AdapterError,
                                                "unreviewed or promisor source object file:.*info/commit-graphs/"):
                        acquisition.a.verify_source_store(store, env)

    def test_promisor_and_unreviewed_files_remain_rejected_with_safe_path_diagnostic(self):
        for rel in ("pack/pack-" + "0" * 40 + ".promisor", "info/commit-graphs/unreviewed\nfile"):
            with self.subTest(rel=rel), tempfile.TemporaryDirectory() as name:
                root = Path(name); env = acquisition.a.environment(root)
                store = root / "store"; store.mkdir()
                acquisition.a.git(store, "init", "--quiet", "--template=", env=env)
                path = store / ".git/objects" / rel; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("untrusted metadata must not be read\n")
                with self.assertRaises(acquisition.a.AdapterError) as caught:
                    acquisition.a.verify_source_store(store, env)
                self.assertEqual(str(caught.exception),
                                 "unreviewed or promisor source object file: " + repr(rel))


class WorkflowRuntimeRootTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        paths = [root / ".github/workflows/nqc-d06-standalone.yml",
                 root / "migration/nqc-d06-standalone.yml.disabled"]
        existing = [path for path in paths if path.exists()]
        self.assertEqual(len(existing), 1)
        self.workflow = existing[0].read_text()

    def initialization_script(self):
        start = '          [[ "$GITHUB_RUN_ID" =~ ^[1-9][0-9]*$ ]]\n'
        self.assertEqual(self.workflow.count(start), 1)
        code = start + self.workflow.split(start, 1)[1].split('          mkdir "$D06_ROOT"', 1)[0]
        return "set -euo pipefail\n" + "\n".join(line[10:] for line in code.splitlines())

    def initialize(self, changes=None):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "environment"
            environment = {"PATH": os.environ["PATH"], "RUNNER_TEMP": temp + "/runner space",
                           "GITHUB_RUN_ID": "37875417870", "GITHUB_RUN_ATTEMPT": "2",
                           "GITHUB_ENV": str(output)}
            environment.update(changes or {})
            result = subprocess.run(["bash", "-c", self.initialization_script()], env=environment,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            return result.returncode, output.read_text() if output.exists() else "", environment

    def test_job_env_uses_only_documented_job_contexts(self):
        job_env = self.workflow.split("    env:\n", 1)[1].split("\n    defaults:", 1)[0]
        allowed = {"github", "needs", "strategy", "matrix", "vars", "secrets", "inputs"}
        for expression in re.findall(r"\$\{\{(.*?)\}\}", job_env):
            for context in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.", expression):
                self.assertIn(context, allowed)
        self.assertNotIn("D06_ROOT:", job_env)

    def test_pinned_toolchain_install_never_updates_rustup(self):
        marker = "      - name: Acquire pinned Rust toolchain and locked dependency cache before disconnecting\n"
        self.assertEqual(self.workflow.count(marker), 1)
        step = self.workflow.split(marker, 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("rustup toolchain install 1.98.1 --profile minimal --component clippy,rustfmt --no-self-update", step)
        self.assertNotIn("rustup update", step)
        self.assertIn('CARGO_HOME="$D06_ROOT/cargo-home"', step)
        self.assertIn('RUSTUP_HOME="$D06_ROOT/rustup-home"', step)
        self.assertIn('RUSTUP_TOOLCHAIN=1.98.1', step)
        self.assertIn('cargo fetch --manifest-path "$D06_ROOT/consumer/nqc-census/Cargo.toml" --locked', step)

    def test_runtime_root_is_persisted_exactly_for_following_steps(self):
        status, output, environment = self.initialize()
        self.assertEqual(status, 0)
        self.assertEqual(output, "D06_ROOT=" + environment["RUNNER_TEMP"] +
                         "/nqc-standalone-d06-37875417870-2\n")

    def test_missing_runtime_values_fail_without_writing_environment(self):
        for key in ("RUNNER_TEMP", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
            with self.subTest(key=key):
                status, output, _ = self.initialize({key: ""})
                self.assertNotEqual(status, 0)
                self.assertEqual(output, "")

    def test_noncanonical_run_identifiers_fail_before_environment_write(self):
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
            for value in ("0", "01", "-1", "1/other", "1\nINJECTED=value", "1; echo unsafe"):
                with self.subTest(key=key, value=value):
                    status, output, _ = self.initialize({key: value})
                    self.assertNotEqual(status, 0)
                    self.assertEqual(output, "")


class PremountedAdapterTests(unittest.TestCase):
    def setUp(self):
        import premounted_d06
        self.p = premounted_d06
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source'
        import importlib.util
        original = Path(__file__).parents[1] / 'ci/nqc-census/verify_rmc006_recertification_source.py'
        spec = importlib.util.spec_from_file_location('original_extractor_permissions', original)
        source_verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(source_verifier)
        source_verifier.extract_members({'required_empty_directories': []},
                                       {'evidence-index.json': b'unchanged evidence'}, self.source)
        self.mountinfo = f'11 1 0:1 / {self.source} ro,nosuid,nodev - tmpfs none rw\n'

    def test_both_adapters_preserve_all_original_computation(self):
        root = Path(__file__).parents[1]
        for name, original in self.p.ORIGINALS.items():
            changed = (root / 'migration' / name).read_text()
            changed = changed.replace("sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/nqc-census'))\n", '')
            changed = changed.replace('\n\n# Prospective v1 adapter: original computation is preserved; privileged mounting\n# was moved to the reviewed fd-pinned boundary. Original entry point is unchanged.\nfrom premounted_d06 import runner_identity\n', '')
            changed = changed.replace('    # Require the genuine pre-mounted read-only boundary before any computation.', '    # Read-only bind mount enforces source preservation even during error paths.')
            changed = changed.replace('    prospective_identity = runner_identity(repo, source, __file__)\n', "    run(['mount', '--bind', source, source])\n    run(['mount', '-o', 'remount,bind,ro', source])\n")
            for output in ('out', 'work'):
                changed = changed.replace("    (" + output + "/'runner-identity.json').write_text(json.dumps(prospective_identity, sort_keys=True, indent=2)+'\\n')\n", '')
            self.assertEqual(changed, (root / original).read_text())

    def test_source_directory_walk_rejects_symlink_in_any_component(self):
        namespace = {}; exec(self.p.MOUNT_SETUP, namespace)
        for target, path in ((self.source, Path(self.temp.name) / 'alias'),
                             (Path(self.temp.name), Path(self.temp.name) / 'parent-alias')):
            path.symlink_to(target, target_is_directory=True)
            looked_up = path if target == self.source else path / 'source'
            with self.assertRaises(OSError): namespace['open_directory'](str(looked_up))
        for bad in ('relative', '/', str(self.source) + '/', str(self.source) + '/../source'):
            with self.assertRaises(ValueError): namespace['open_directory'](bad)

    def test_pinned_device_inode_rejected_before_mount(self):
        namespace = {}; exec(self.p.MOUNT_SETUP, namespace)
        info = self.source.stat()
        with self.assertRaisesRegex(ValueError, 'replaced'):
            namespace['mount_readonly'](str(self.source), os.getuid(), info.st_dev, info.st_ino + 1)

    def test_nested_source_mount_is_rejected(self):
        self.p.require_no_descendant_mounts(self.source, self.mountinfo)
        with self.assertRaisesRegex(ValueError, 'descendant'):
            self.p.require_no_descendant_mounts(self.source, self.mountinfo + f'12 11 0:1 / {self.source}/child rw - tmpfs none rw\n')

    def proof(self, text=None):
        from types import SimpleNamespace
        with mock.patch.object(Path, 'read_text', return_value=text or self.mountinfo), \
             mock.patch.object(self.p.os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)), \
             mock.patch.dict(os.environ, {'NQC_SOURCE_PREMOUNT_ID': '10', 'NQC_SOURCE_READONLY_MOUNT_ID': '11'}):
            return self.p.readonly_proof(self.source)

    def test_only_real_erofs_accepts_write_rejection(self):
        import errno
        with mock.patch.object(self.p.os, 'open', side_effect=OSError(errno.EROFS, 'readonly')):
            result = self.proof()
            self.assertEqual(result['write_open_errno'], errno.EROFS)
            self.assertFalse(result['probe_creates_named_file'])
            self.assertFalse(result['probe_writes_or_truncates_existing'])
            self.assertFalse(result['probe_linkable'])
        for code in (errno.EACCES, errno.EPERM, errno.ENOENT, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL):
            with mock.patch.object(self.p.os, 'open', side_effect=OSError(code, 'different failure')):
                with self.assertRaisesRegex(ValueError, 'errno=' + str(code) + r' \(' + errno.errorcode[code] + r'\)'): self.proof()

    def test_unexpected_write_open_success_does_not_mutate_evidence(self):
        before = (self.source / 'evidence-index.json').read_bytes()
        def metadata(path):
            value = path.stat()
            return value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink
        paths = (self.source, self.source / 'evidence-index.json')
        original_metadata = [metadata(path) for path in paths]
        with self.assertRaisesRegex(ValueError, 'permits anonymous write'): self.proof()
        self.assertEqual([metadata(path) for path in paths], original_metadata)
        self.assertEqual((self.source / 'evidence-index.json').read_bytes(), before)
        self.assertEqual(list(self.source.iterdir()), [self.source / 'evidence-index.json'])

    def test_rw_shared_missing_and_wrong_mount_identity_rejected(self):
        for changed in (self.mountinfo.replace(' ro,', ' rw,'),
                        self.mountinfo.replace(' - ', ' shared:42 - '),
                        self.mountinfo.replace(str(self.source), '/another-source'),
                        self.mountinfo.replace('11 1 ', '12 1 ')):
            with self.assertRaises(ValueError): self.proof(changed)

    def test_source_probe_symlink_rejected_without_following(self):
        source = self.source
        alias = Path(self.temp.name) / 'alias'; alias.symlink_to(source, target_is_directory=True)
        self.source = alias
        with self.assertRaisesRegex(ValueError, 'alias'): self.proof()
        self.assertEqual((source / 'evidence-index.json').read_bytes(), b'unchanged evidence')

    def test_actual_extractor_permissions_under_nonzero_zero_capability_uid(self):
        import errno, stat
        self.assertGreater(os.getuid(), 0)
        fields = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
        for name in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'):
            self.assertEqual(int(fields[name].strip(), 16), 0)
        self.assertEqual(os.getgroups(), [])
        self.assertEqual(fields['NoNewPrivs'].strip(), '1')
        self.assertEqual(stat.S_IMODE(self.source.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.source / 'evidence-index.json').stat().st_mode), 0o444)
        with self.assertRaises(OSError) as caught:
            os.open(self.source / 'evidence-index.json', os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.assertEqual(caught.exception.errno, errno.EACCES)

    def test_anonymous_probe_flags_disallow_linking_creation_or_truncation_of_named_files(self):
        import errno
        with mock.patch.object(self.p.os, 'open', side_effect=OSError(errno.EROFS, 'readonly')) as opened:
            self.proof()
        args = opened.call_args.args
        self.assertEqual(args[0], self.source)
        self.assertEqual(args[1], os.O_TMPFILE | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.assertEqual(args[2], 0o600)
        self.assertFalse(args[1] & os.O_TRUNC)
        self.assertFalse(args[1] & os.O_CREAT)

    def test_workflow_exact_isolated_cli_reaches_own_guard(self):
        program = Path(__file__).with_name('premounted_d06.py')
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', str(program), '--root', str(self.source),
            '--expected-commit', 'a' * 40, '--expected-tree', 'b' * 40],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('run-specific root required', result.stdout)
        self.assertNotIn('ModuleNotFoundError', result.stdout)

    def test_privileged_setup_clears_high_inherited_fds_and_cwd(self):
        program = Path(__file__).with_name('premounted_d06.py')
        probe = Path(self.temp.name) / 'inherited-writable-fd'
        probe.write_bytes(b'unchanged evidence')
        script = r'''
import importlib.util, os, pathlib, resource, sys
spec = importlib.util.spec_from_file_location('boundary', sys.argv[1]); p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
fd = os.open(sys.argv[2], os.O_WRONLY); os.dup2(fd, 900, inheritable=True); os.close(fd)
os.chdir(pathlib.Path(sys.argv[3]))
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE); resource.setrlimit(resource.RLIMIT_NOFILE, (128, hard))
namespace = {}; exec(p.MOUNT_SETUP, namespace)
namespace['mount_readonly'] = lambda *args: (10, 11)
os.getuid = lambda: 0; os.geteuid = lambda: 0
sys.argv = ['fixed', '/tmp/nqc-standalone-d06-1-1', '1001', '1001', '1', '1', 'net:[1]', 'mnt:[1]', 'a'*40, 'b'*40]
def inspect(path, command):
    assert path == '/usr/bin/setpriv' and '--bounding-set=-all' in command and '--no-new-privs' in command
    assert os.getcwd() == '/'
    try: os.fstat(900)
    except OSError: pass
    else: raise AssertionError('inherited descriptor survived')
    print('HIGH_FD_AND_CWD_CLOSED_FIXED_SETPRIV')
os.execv = inspect
exec(p.ROOT_SETUP[len(p.MOUNT_SETUP):], namespace)
'''
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', script, str(program), str(probe), str(self.source)],
            stdin=subprocess.DEVNULL, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('HIGH_FD_AND_CWD_CLOSED_FIXED_SETPRIV', result.stdout)
        self.assertEqual(probe.read_bytes(), b'unchanged evidence')

    def test_privileged_literal_uses_only_fixed_imports_and_no_shell(self):
        imported = {alias.name for node in ast.walk(ast.parse(self.p.ROOT_SETUP)) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imported, {'ctypes', 'os', 're', 'stat', 'sys'})
        self.assertNotIn('subprocess', self.p.ROOT_SETUP)
        self.assertIn('MountAttr(1, 0, 0, 0)', self.p.ROOT_SETUP)
        self.assertIn("os.execv('/usr/bin/setpriv'", self.p.ROOT_SETUP)
        self.assertIn("os.chdir('/')", self.p.ROOT_SETUP)
        self.assertIn('os.closerange(3, 2**31 - 1)', self.p.ROOT_SETUP)

    def test_privileged_python_disables_site_hooks_and_stdlib_still_loads(self):
        import inspect
        self.assertIn("'/usr/bin/python3', '-I', '-S', '-B', '-c', ROOT_SETUP", inspect.getsource(self.p.command))
        result = subprocess.run(['/usr/bin/python3', '-I', '-S', '-B', '-c', self.p.ROOT_SETUP],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fixed privileged setup arguments required', result.stdout)
        self.assertNotIn('ModuleNotFoundError', result.stdout)

    def test_original_root_identity_is_rejected_before_privilege_request(self):
        with mock.patch.object(self.p.os, 'getuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'nonroot'): self.p.command(self.source, 'a'*40, 'b'*40)

if __name__ == "__main__":
    unittest.main()
