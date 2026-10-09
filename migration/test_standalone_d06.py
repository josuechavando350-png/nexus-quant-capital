"""Local proposal regressions. All network responses below are synthetic mocks."""
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
        receipt = b'{"unit_test": true}\n'
        self.write("historical-source/HISTORICAL-ADAPTER.json", {
            "schema": "nqc-standalone-historical-materialization-v1",
            "status": "HISTORICAL_SOURCE_MATERIALIZED_CONSUMER_BOUND",
            "historical_source": {"commit": index.SOURCE_COMMIT},
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


if __name__ == "__main__":
    unittest.main()
