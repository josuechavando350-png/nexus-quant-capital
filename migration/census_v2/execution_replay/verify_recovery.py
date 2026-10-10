#!/usr/bin/env python3
"""Offline audit of the retained, explicitly named provider recovery attempts."""
import argparse
import json
from pathlib import Path
import re
import tempfile
import zipfile
from rpc_witness import Witness, canonical, sha
from run_fork import FORGE_SHA, SOLC_SHA, TEST_PATH, PATCHED_TEST_SHA

ARCHIVE_SHA = "a2752e56ad4a60b22c00a7e9db2d8f116f0b0e6d2ef67b1755c92f8f210287b5"
HERE = Path(__file__).resolve().parent


def need(condition, message):
    if not condition:
        raise ValueError(message)


def verify(path):
    need(sha(Path(path).read_bytes()) == ARCHIVE_SHA, "archive digest")
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        need(len(archive.namelist()) == len(set(archive.namelist())), "duplicate member")
        need(set(archive.namelist()) == set(manifest["files"]) | {"manifest.json"}, "archive members")
        for name, pin in manifest["files"].items():
            raw = archive.read(name)
            need((len(raw), sha(raw)) == (pin["bytes"], pin["sha256"]), "member digest: " + name)
        source_manifest_raw = archive.read("inputs/sources.json")
        source_manifest = json.loads(source_manifest_raw)
        attempts = []
        for name, producer in manifest["attempt_producers"].items():
            report = json.loads(archive.read(name + "/report.json"))
            need(report["source_manifest_sha256"] == sha(source_manifest_raw), "input manifest binding")
            need(report["forge_sha256"] == FORGE_SHA and report["solc_sha256"] == SOLC_SHA, "toolchain binding")
            for field in ["capital_admission_changed", "census_closed", "independent_certification", "live_transaction_sent"]:
                need(report[field] is False, "unsupported authority: " + field)
            for source_name, digest in report["producer_sources"].items():
                need(sha(archive.read(producer + "/" + source_name)) == digest, "producer source binding")
            for source_name, pin in source_manifest["files"].items():
                need(sha(archive.read("inputs/" + source_name)) == pin["sha256"], "original source changed")
                expected = PATCHED_TEST_SHA if source_name == TEST_PATH and "compatibility_overlay" in report else pin["sha256"]
                need(sha(archive.read(name + "/source/" + source_name)) == expected, "effective source changed")
            if "build" in report:
                need(sha(archive.read(name + "/build.log")) == report["build"]["log_sha256"], "build log binding")
            metrics = {}
            for run in report["runs"]:
                log_raw = archive.read(name + "/" + run["mode"] + ".log")
                need(sha(log_raw) == run["log_sha256"], "test log binding")
                if run["exit_code"] == 0:
                    text = log_raw.decode()
                    need("2 passed; 0 failed; 0 skipped" in text, "test success summary missing")
                    pairs = re.findall(r"^  NQC_RANK1_FORK_([A-Z_]+): ([0-9]+)$", text, re.M)
                    need(len(pairs) == len(dict(pairs)) == 4, "test metrics missing or duplicated")
                    metrics[run["mode"]] = dict(pairs)
            attempts.append({"attempt": name, "provider": report["provider"], "status": report["status"],
                             "upstream_requests": report["upstream_requests"], "metrics": metrics,
                             "failure": report.get("failure")})
        by_name = {x["attempt"]: x for x in attempts}
        for name in ["blockpi-001", "nodies-001", "nodies-002", "nodies-003"]:
            need(by_name[name]["status"] == "FAILED", "failed attempt relabeled")
        passed = "SCOPED_FORK_TESTS_PASSED_NOT_ECONOMIC_ADMISSION"
        need(by_name["nodies-004"]["status"] == by_name["nodies-offline-001"]["status"] == passed, "fork not passed")
        need(by_name["nodies-004"]["upstream_requests"] == 115, "acquisition count")
        need(by_name["nodies-offline-001"]["upstream_requests"] == 0, "offline used upstream")
        expected = {"EXECUTE_CALL_GAS_UNITS": "562357", "WETH_SURPLUS_WEI": "90814117763741536",
                    "FLASH_FEE_WEI": "5342006927278914", "PRODUCTION_GAS_SPONSORED": "0"}
        need(by_name["nodies-004"]["metrics"] == {"original": expected}, "capture metrics")
        need(by_name["nodies-offline-001"]["metrics"] == {"original": expected,
             "isolated": {**expected, "EXECUTE_CALL_GAS_UNITS": "534803"}}, "replay metrics")
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "upstream.jsonl"
            source.write_bytes(archive.read("nodies-004/rpc/upstream.jsonl"))
            witness = Witness(Path(d) / "offline", replay=source, provider="nodies")
            need(len(witness.cache) == 115, "witness population")
            requests = [json.loads(x) for x in archive.read("nodies-offline-001/rpc/requests.jsonl").splitlines()]
            for row in requests:
                value = witness.call(row["method"], row["params"])
                need(row["source"] == "retained_response" and sha(canonical(value).encode()) == row["result_sha256"],
                     "offline request/result binding")
            need(witness.count == 0, "consumer opened network")
    return {"schema": "nqc-provider-recovery-readback-v1", "archive_sha256": ARCHIVE_SHA,
            "attempts": attempts, "offline_served_requests_checked": len(requests),
            "captured_state_and_header_requests": 115, "distinct_solidity_tests": 2,
            "original_and_isolated_replays_pass": True, "offline_network_requests": 0,
            "execution_profile": "ORIGINAL_CANCUN_TIME_ONLY_PREDECESSOR_STATE",
            "gas_measurement_differs_by_test_mode": True, "production_gas_quote_proven": False,
            "merkle_state_proofs_verified": False, "economic_profit_admitted": False,
            "independent_certification": False, "census_closed": False,
            "consumer_sha256": sha(Path(__file__).read_bytes())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Path(args.output).write_text(canonical(verify(args.archive)) + "\n")
