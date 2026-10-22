"""Adversarial unit tests; synthetic fixtures are not physical gate evidence."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from h2_actions import (BRANCH, DESTINATION, DESTINATION_ID, PARENT, TX, WORKFLOW,
                        SOURCE, PROVIDERS, clean_env, compare_forks, download, producer_context,
                        probe_providers, rpc, rpc_readonly)
from isolation import (EXTENSION_FILES, ROOT, WORKFLOW_TEMPLATE, inventory,
                       project_repository, reviewed_workflow)


def fixture_context():
    return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": DESTINATION,
        "GITHUB_REPOSITORY_ID": str(DESTINATION_ID), "GITHUB_REF": "refs/heads/" + BRANCH,
        "GITHUB_SHA": "a" * 40, "GITHUB_EVENT_NAME": "push", "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64", "OMEGA_WORKFLOW_SHA": "a" * 40,
        "OMEGA_WORKFLOW_REF": DESTINATION + "/" + WORKFLOW + "@refs/heads/" + BRANCH,
        "OMEGA_REPOSITORY_VISIBILITY": "public", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}


class ContextTests(unittest.TestCase):
    def test_valid_context_still_has_no_canonical_authority(self):
        result = producer_context(fixture_context(), "a" * 40, "b" * 40)
        self.assertFalse(result["canonical_recertification"])
        self.assertIsNone(result["artifact_id"])

    def test_wrong_or_missing_identity_fields_reject(self):
        for key in fixture_context():
            for replacement in (None, "", "false", "different"):
                with self.subTest(key=key, replacement=replacement):
                    env = fixture_context()
                    if replacement is None:
                        del env[key]
                    else:
                        env[key] = replacement
                    with self.assertRaises(ValueError):
                        producer_context(env, "a" * 40, "b" * 40)

    def test_main_miner_and_pull_request_refs_reject(self):
        for ref in ("refs/heads/main", "refs/heads/feat/nqc-miner-collector-20261022", "refs/pull/30/merge"):
            env = fixture_context()
            env["GITHUB_REF"] = ref
            with self.assertRaises(ValueError):
                producer_context(env, "a" * 40, "b" * 40)

    def test_bad_commit_and_tree_reject(self):
        for head, tree in (("a" * 39, "b" * 40), ("a" * 40, "b" * 39), ("a" * 40, "x" * 40)):
            with self.assertRaises(ValueError):
                producer_context(fixture_context(), head, tree)

    def test_run_zero_negative_decimal_or_injection_reject(self):
        for value in ("0", "-1", "1.0", "$(id)", "1\n2"):
            env = fixture_context()
            env["GITHUB_RUN_ID"] = value
            with self.assertRaises(ValueError):
                producer_context(env, "a" * 40, "b" * 40)

    def test_child_processes_do_not_inherit_job_token(self):
        with patch.dict(os.environ, {"GH_TOKEN": "fixture", "GITHUB_TOKEN": "fixture"}):
            env = clean_env()
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("GITHUB_TOKEN", env)

    def test_script_never_writes_bytecode_when_sudo_removes_environment(self):
        import shutil
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "omega"
            shutil.copytree(ROOT / "omega", target)
            env = {k: v for k, v in os.environ.items()
                   if k not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPATH"}}
            result = subprocess.run([sys.executable, str(target / "h2_actions.py"), "--help"],
                                    env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(target.rglob("__pycache__")), [])


class RpcTests(unittest.TestCase):
    def fake_response(self, body, status=b"200"):
        from subprocess import CompletedProcess
        return CompletedProcess([], 0, body + b"\n" + status, b"")

    def test_curl_preflight_accepts_json_result(self):
        with patch("h2_actions.subprocess.run", return_value=self.fake_response(b'{"id":1,"result":"0x1"}')):
            self.assertEqual(rpc(PROVIDERS[0][1], "eth_chainId", []), "0x1")

    def test_http_error_includes_provider_and_never_passes(self):
        with patch("h2_actions.subprocess.run", return_value=self.fake_response(b'Forbidden', b'403')):
            with self.assertRaisesRegex(ValueError, "HTTP 403"):
                rpc(PROVIDERS[0][1], "eth_chainId", [])

    def test_http_200_rpc_error_or_wrong_id_does_not_pass(self):
        for body in (b'{"id":1,"error":{"code":-32000}}', b'{"id":2,"result":"0x1"}'):
            with patch("h2_actions.subprocess.run", return_value=self.fake_response(body)):
                with self.assertRaises(ValueError):
                    rpc(PROVIDERS[0][1], "eth_chainId", [])

    def test_both_providers_are_checked_on_first_failure(self):
        with patch("h2_actions.rpc", side_effect=ValueError("fixture blocked")) as called, \
             patch("h2_actions.evidence") as recorded:
            with self.assertRaisesRegex(ValueError, "preflight_blocked"):
                probe_providers()
        self.assertEqual(called.call_count, 2)
        self.assertEqual([r['status'] for r in recorded.call_args.args[1]['providers']], ['BLOCKED','BLOCKED'])

    def test_unknown_upstream_is_not_contacted(self):
        with patch("h2_actions.subprocess.run") as called:
            with self.assertRaisesRegex(ValueError, "unknown_upstream"):
                rpc("https://example.org/", "eth_chainId", [])
            called.assert_not_called()

    def test_reads_allowed(self):
        rpc_readonly({"jsonrpc": "2.0", "id": 1, "method": "eth_getStorageAt", "params": []})

    def test_signing_broadcast_and_admin_rejected(self):
        for method in ("eth_sendRawTransaction", "eth_sendTransaction", "eth_sign", "personal_sign",
                       "wallet_sendCalls", "anvil_setBalance", "admin_addPeer", None, "eth_call "):
            with self.assertRaises(ValueError):
                rpc_readonly({"jsonrpc": "2.0", "method": method})

    def test_batch_with_one_write_rejected_before_forwarding(self):
        with self.assertRaises(ValueError):
            rpc_readonly([{"jsonrpc": "2.0", "method": "eth_chainId"},
                          {"jsonrpc": "2.0", "method": "eth_sendRawTransaction"}])

    def test_empty_oversized_and_malformed_batches_reject(self):
        for value in ([], [None], [1], "eth_call", {}, {"jsonrpc": "2.0", "method": []},
                      [{"jsonrpc": "2.0", "method": "eth_chainId"}] * 33):
            with self.assertRaises(ValueError):
                rpc_readonly(value)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = Path(temporary.name) / "result"

    def fake_curl(self, command, **kwargs):
        from subprocess import CompletedProcess
        self.target.write_bytes(b"fixture")
        return CompletedProcess(command, 0, b"", b"")

    def test_token_only_on_stdin_and_no_cross_origin_forward_override(self):
        with patch.dict(os.environ, {"GH_TOKEN": "fixture_token"}), \
             patch("h2_actions.subprocess.run", side_effect=self.fake_curl) as called, \
             patch("h2_actions.evidence"):
            download("https://api.github.com/repos/" + SOURCE + "/actions/artifacts/1", self.target, api=True)
        args, kwargs = called.call_args
        self.assertNotIn("fixture_token", " ".join(args[0]))
        self.assertIn(b"fixture_token", kwargs["input"])
        self.assertNotIn("GH_TOKEN", kwargs["env"])
        self.assertNotIn("--location-trusted", args[0])
        self.assertIn("--proto-redir", args[0])

    def test_api_token_cannot_be_sent_to_other_origin_or_repository(self):
        for url in ("https://example.org/x", "https://api.github.com/repos/attacker/repo/actions/artifacts/1"):
            with patch("h2_actions.subprocess.run") as called:
                with self.assertRaisesRegex(ValueError, "api_scope"):
                    download(url, self.target, api=True)
                called.assert_not_called()

    def test_opaque_bearer_token_formats_are_not_restricted_to_a_prefix(self):
        with patch.dict(os.environ, {"GH_TOKEN": "opaque.token-with_chars+/=="}), \
             patch("h2_actions.subprocess.run", side_effect=self.fake_curl) as called, \
             patch("h2_actions.evidence"):
            download("https://api.github.com/repos/" + SOURCE + "/actions/artifacts/1", self.target, api=True)
        self.assertIn(b"opaque.token-with_chars+/==", called.call_args.kwargs["input"])

    def test_missing_or_malformed_token_rejects_before_process(self):
        for value in ("", "injected\nheader=x", 'bad"quote'):
            with patch.dict(os.environ, {"GH_TOKEN": value}), patch("h2_actions.subprocess.run") as called:
                with self.assertRaises(ValueError):
                    download("https://api.github.com/repos/" + SOURCE + "/actions/artifacts/1", self.target, api=True)
                called.assert_not_called()

    def test_hash_mismatch_rejects_downloaded_bytes(self):
        with patch("h2_actions.subprocess.run", side_effect=self.fake_curl):
            with self.assertRaisesRegex(ValueError, "digest_mismatch"):
                download("https://example.org/fixture", self.target, sha256="0"*64)

    def test_existing_file_is_never_overwritten(self):
        self.target.write_text("original")
        with patch("h2_actions.subprocess.run") as called:
            with self.assertRaises(ValueError):
                download("https://example.org/fixture", self.target)
            called.assert_not_called()
        self.assertEqual(self.target.read_text(), "original")

    def test_http_rejects_before_process(self):
        with patch("h2_actions.subprocess.run") as called:
            with self.assertRaises(ValueError):
                download("http://example.org/fixture", self.target)
            called.assert_not_called()


class WorkflowBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        for name in EXTENSION_FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        self.active = self.root / WORKFLOW
        self.active.parent.mkdir(parents=True)

    def activate(self):
        self.active.write_bytes((self.root / WORKFLOW_TEMPLATE).read_bytes())
        self.active.chmod(0o644)

    def test_preparation_without_activation_allowed(self):
        self.assertFalse(reviewed_workflow(self.root))

    def test_only_exact_reviewed_activation_is_projected(self):
        self.activate()
        self.assertTrue(reviewed_workflow(self.root))
        destination = self.root.parent / "projected"
        project_repository(self.root, destination)
        self.assertFalse((destination / WORKFLOW).exists())
        self.assertTrue(self.active.exists())

    def test_extra_workflow_is_not_hidden(self):
        self.activate()
        extra = self.active.with_name("miner-or-unknown.yml")
        extra.write_text("not authorized\n")
        destination = self.root.parent / "projected"
        project_repository(self.root, destination)
        self.assertEqual((destination / extra.relative_to(self.root)).read_bytes(), extra.read_bytes())

    def test_changed_workflow_rejects(self):
        self.activate()
        self.active.write_bytes(self.active.read_bytes() + b"# drift\n")
        with self.assertRaisesRegex(ValueError, "unreviewed_active_workflow"):
            inventory(self.root)

    def test_changed_template_and_matching_workflow_still_reject(self):
        template = self.root / WORKFLOW_TEMPLATE
        template.write_bytes(template.read_bytes() + b"# both altered\n")
        self.activate()
        with self.assertRaisesRegex(ValueError, "template_digest"):
            inventory(self.root)

    def test_executable_workflow_rejects(self):
        self.activate()
        self.active.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "unreviewed_active_workflow"):
            inventory(self.root)

    def test_workflow_symlink_rejects(self):
        self.active.symlink_to(self.root / WORKFLOW_TEMPLATE)
        with self.assertRaises(ValueError):
            inventory(self.root)


class ForkConsensusTests(unittest.TestCase):
    def setUp(self):
        self.positive = {"transaction_hash": TX, "block_number": 25252136, "parent_hash": PARENT,
            "realized_profit": 10, "operator_usdc_delta": 10, "flash_premium": 1,
            "pair_amount_out": 20, "ordered_logs_digest": "0x" + "c" * 64,
            "pair_reserve0_after": 100, "pair_reserve1_after": 200,
            "executor_runtime_keccak256": "0x" + "d" * 64}
        self.negative = {"transaction_hash": TX, "atomic_rejection_pass": 1, "shortfall_before_gas": 10}

    def compare(self, positive=None, negative=None):
        p = self.positive if positive is None else positive
        n = self.negative if negative is None else negative
        return compare_forks(p, copy.deepcopy(p), n, copy.deepcopy(n))

    def test_consensus_does_not_close_protocol_or_certify(self):
        result = self.compare()
        self.assertEqual(result["protocol_fork_truth"], "NOT_CLOSED")
        for key in ("canonical_recertification", "census_closed", "signing_authorized", "broadcast_authorized"):
            self.assertFalse(result[key])

    def test_provider_disagreement_rejects(self):
        right = {**self.positive, "realized_profit": 11}
        with self.assertRaisesRegex(ValueError, "provider_dissent"):
            compare_forks(self.positive, right, self.negative, self.negative)

    def test_wrong_historical_anchor_rejects(self):
        for key, value in (("block_number", 1), ("transaction_hash", "0x" + "a"*64), ("parent_hash", "0x"+"f"*64)):
            with self.assertRaisesRegex(ValueError, "historical_anchor"):
                self.compare({**self.positive, key: value})

    def test_missing_required_metrics_rejects(self):
        for key in ("realized_profit", "flash_premium", "ordered_logs_digest", "operator_usdc_delta"):
            p = dict(self.positive)
            del p[key]
            with self.assertRaises(ValueError):
                self.compare(p)

    def test_unknown_cost_reserves_or_hash_never_become_zero(self):
        for key in ("flash_premium", "pair_amount_out", "pair_reserve0_after", "pair_reserve1_after",
                    "ordered_logs_digest", "executor_runtime_keccak256"):
            with self.assertRaises(ValueError):
                self.compare({**self.positive, key: None})

    def test_null_boolean_zero_loss_and_unreconciled_profit_reject(self):
        for value in (None, True, 0, -1, "0", 1.5, [], "nan"):
            with self.assertRaises((ValueError, TypeError)):
                self.compare({**self.positive, "realized_profit": value, "operator_usdc_delta": value})
        with self.assertRaises(ValueError):
            self.compare({**self.positive, "operator_usdc_delta": 9})

    def test_negative_case_must_be_atomic_and_have_shortfall(self):
        for key, value in (("atomic_rejection_pass", 0), ("atomic_rejection_pass", True),
                           ("shortfall_before_gas", 0), ("shortfall_before_gas", None)):
            with self.assertRaises((ValueError, TypeError)):
                self.compare(negative={**self.negative, key: value})


if __name__ == "__main__":
    unittest.main()
