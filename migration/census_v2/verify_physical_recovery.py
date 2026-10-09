#!/usr/bin/env python3
"""Recover scoped facts from original job logs; never substitute for ZIP/fork replay."""
import argparse
import gzip
import hashlib
from pathlib import Path
import re

from verify_winner_recovery import PINS, archive, canonical, need, parse, sha, transport

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE/"evidence/physical-logs"
PINS_SHA = "27a7bde4624b12527d8a24241fcccd45d7bce5d7f3e5ceb900988ac037f8edb7"
ORIGINS_SHA = "1ee600f0fdf1a2eb93bed1a5c760d27dbd74ea6e7a2e47ec1b7c798c54d6a9a8"
RUNS = (37737680174, 37740704145, 37741109591, 37742063251)
TIMESTAMP = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z) (.*)\Z")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SUITE = re.compile(r"Ran ([1-9][0-9]*) tests? for (test/[^ :]+):([A-Za-z0-9_]+)\Z")
PASS = re.compile(r"\[PASS\] (test[A-Za-z0-9_]+)\(\) \(gas: ([0-9]+)\)\Z")
END = re.compile(r"Suite result: ok\. ([0-9]+) passed; ([0-9]+) failed; ([0-9]+) skipped; .+\Z")
METRIC = re.compile(r"  (NQC_[A-Z0-9_]+): (0|[1-9][0-9]*)\Z")
EXPECTED_TESTS = {
    RUNS[0]: {
        "testAllowanceAndTransferFromConserveExactUnits", "testCannotTransferUnownedWeth",
        "testDepositMintsExactUnitsWithoutExtraFee", "testExcessAllowanceCannotBeSpentAndNoStateChange",
        "testPinnedMainnetRuntimeAndMetadata", "testRecipientRevertingHookIsNotInvoked",
        "testTransferPreservesExactSenderRecipientDeltas", "testWithdrawBurnsExactWethAndReturnsExactEther",
        "testZeroTransferAndApprovalDoNotRebaseBalances",
    },
    RUNS[1]: {"testPreviousHealthFactorAndWinnerTimestampOnly"},
    RUNS[2]: {"testImpossibleProfitClaimRevertsAndCannotSpendExistingBalances",
              "testZeroOwnWethFeeWithoutExternalSponsorHasPositiveForkSurplus"},
    RUNS[3]: {"testImpossibleProfitClaimRevertsAndCannotSpendExistingBalances",
              "testZeroOwnWethFeeWithoutExternalSponsorHasPositiveForkSurplus"},
}
SOURCE_TEST_FILES = {
    RUNS[0]: "NqcRmc011WethPhysicalCompatibilityFork.t.sol",
    RUNS[1]: "NqcRmc015WethTimeOnlyHF.t.sol",
    RUNS[2]: "NqcRmc016RankOneSelfFinancingFork.t.sol",
    RUNS[3]: "NqcRmc016RankOneSelfFinancingFork.t.sol",
}


def output_records(raw):
    """Ignore displayed shell scripts/env, including untimestamped continuations.

    A grep/echo of PASS inside the runner's command display is not a test result.
    We preserve source line numbers and runner timestamps for accepted output.
    """
    need(len(raw) <= 500_000, "oversized decoded job log")
    records, groups = [], []
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        match = TIMESTAMP.fullmatch(line)
        if match is None:
            need(any(groups), "untimestamped output outside displayed command")
            continue
        timestamp, body = match.groups()
        if body.startswith("##[group]"):
            groups.append(body.removeprefix("##[group]").startswith("Run "))
            continue
        if body == "##[endgroup]":
            need(groups, "unbalanced log group")
            groups.pop()
            continue
        if any(groups):
            continue
        records.append({"line": line_number, "timestamp": timestamp, "text": ANSI.sub("", body)})
    need(not groups, "unterminated displayed-command group")
    return records


def suites(records, run_id):
    found, current = [], None
    for record in records:
        text = record["text"]
        start = SUITE.fullmatch(text)
        if start:
            need(current is None, "nested/incomplete test suite")
            count, path, name = start.groups()
            need(path == "test/" + SOURCE_TEST_FILES[run_id], "unexpected test source")
            current = {"start_line": record["line"], "start_time": record["timestamp"],
                       "path": path, "contract": name, "expected": int(count), "tests": {}, "metrics": {}}
            continue
        passed, measured, ended = PASS.fullmatch(text), METRIC.fullmatch(text), END.fullmatch(text)
        if passed:
            need(current is not None, "test result outside suite")
            name, gas = passed.groups()
            need(name not in current["tests"], "duplicate test result")
            current["tests"][name] = {"test_harness_gas": int(gas), "line": record["line"]}
        elif measured:
            need(current is not None, "measurement outside suite")
            name, value = measured.groups()
            need(name not in current["metrics"], "duplicate measurement")
            current["metrics"][name] = {"value": value, "line": record["line"], "timestamp": record["timestamp"]}
        elif ended:
            need(current is not None, "suite result without start")
            passed_count, failed, skipped = map(int, ended.groups())
            need(failed == skipped == 0 and passed_count == current["expected"] == len(current["tests"])
                 and set(current["tests"]) == EXPECTED_TESTS[run_id], "missing/failed/unexpected physical test")
            current.update(end_line=record["line"], end_time=record["timestamp"])
            found.append(current)
            current = None
        elif "[FAIL" in text or text.startswith("Suite result: FAILED"):
            raise ValueError("physical test failed")
    need(current is None and len(found) == (3 if run_id == RUNS[1] else 1), "incomplete/extra physical suites")
    return found


def exact_line(records, pattern):
    matches = [(r, re.fullmatch(pattern, r["text"])) for r in records]
    matches = [(r, m) for r, m in matches if m is not None]
    need(len(matches) == 1, "expected one actual output line: " + pattern)
    return matches[0]


def source_identity(directory):
    raw_pins, raw_origins = (directory/"pins.json").read_bytes(), (directory/"source-origins.json").read_bytes()
    need(sha(raw_pins) == PINS_SHA and sha(raw_origins) == ORIGINS_SHA, "source pin catalog changed")
    pins = parse(raw_pins)["pins"]
    need(tuple(p["run_id"] for p in pins) == RUNS, "wrong source runs")
    meta = parse((directory/"api-snapshot.json").read_bytes())
    need(meta["source_repository"] == "josuechavando350-png/nexus-engine"
         and meta["archive_bytes_downloaded"] is False and meta["new_rpc_calls"] is False, "source scope changed")
    by_run = {d["run"]["id"]: d for d in meta["runs"]}
    need(len(by_run) == len(meta["runs"]) == 4, "duplicate/missing metadata")
    sources = parse(raw_origins)
    for source in sources:
        need(Path(source["file"]).name == source["file"], "unsafe source name")
        data = (directory/"sources"/source["file"]).read_bytes()
        need(sha(data) == source["sha256"] and len(data) == source["bytes"]
             and hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == source["git_blob_sha1"],
             "historical source bytes changed")
        pin = next(p for p in pins if p["run_id"] == source["run_id"])
        need(source["commit"] == pin["head_sha"] and source["tree"] == pin["tree"], "source commit/tree changed")
    observations = {}
    for pin in pins:
        row = by_run[pin["run_id"]]
        run, jobs, artifacts = row["run"], row["jobs"]["jobs"], row["artifacts"]["artifacts"]
        need(run["status"] == "completed" and run["conclusion"] == pin["conclusion"] == "success"
             and run["event"] == pin["event"] == "pull_request" and run["head_sha"] == pin["head_sha"]
             and run["head_commit"]["tree_id"] == pin["tree"] and run["path"] == pin["workflow_path"]
             and run["repository"]["full_name"] == meta["source_repository"], "run provenance mismatch")
        matches = [j for j in jobs if j["id"] == pin["job_id"]]
        need(len(matches) == 1, "job missing/duplicated")
        job = matches[0]
        need(job["name"] == pin["job_name"] and job["run_id"] == pin["run_id"]
             and job["status"] == "completed" and job["conclusion"] == "success"
             and all(s["status"] == "completed" and s["conclusion"] == "success" for s in job["steps"]),
             "job or step incomplete")
        matches = [a for a in artifacts if a["id"] == pin["artifact_id"]]
        need(len(matches) == 1, "artifact metadata missing/duplicated")
        artifact = matches[0]
        need(artifact["name"] == pin["artifact_name"] and artifact["size_in_bytes"] == pin["artifact_bytes"]
             and artifact["digest"] == "sha256:" + pin["artifact_sha256"]
             and artifact["workflow_run"]["id"] == pin["run_id"]
             and artifact["workflow_run"]["head_sha"] == pin["head_sha"], "artifact metadata binding changed")
        compressed = (directory/pin["log_file"]).read_bytes()
        need(sha(compressed) == pin["gzip_sha256"], "compressed log changed")
        raw = gzip.decompress(compressed)
        need(sha(raw) == pin["decoded_log_sha256"] and len(raw) == pin["decoded_log_bytes"], "decoded log changed")
        records = output_records(raw)
        line, _ = exact_line(records, r"\[command\]/usr/bin/git log -1 --format=%H")
        i = records.index(line)
        need(i+1 < len(records) and records[i+1]["text"] == pin["head_sha"], "actual checkout differs from run head")
        exact_line(records, "forge Version: 1.7.1")
        exact_line(records, "SHA256 digest of uploaded artifact zip is " + pin["artifact_sha256"])
        exact_line(records, re.escape("Artifact " + pin["artifact_name"] + ".zip successfully finalized. Artifact ID ")
                   + str(pin["artifact_id"]))
        parsed = suites(records, pin["run_id"])
        observations[pin["run_id"]] = {"pin": pin, "suites": parsed, "records": records}
    return observations, sources, sha((directory/"api-snapshot.json").read_bytes())


def metric(suite, name):
    need(name in suite["metrics"], "missing fork metric " + name)
    return int(suite["metrics"][name]["value"])


def verify(archive_root, directory=EVIDENCE):
    observations, sources, api_hash = source_identity(directory)
    temporal = observations[RUNS[1]]["suites"]
    expected_hf = [(1000000001993818630, 999999999704293538),
                   (1000701093031081909, 1000701096098308225),
                   (1000489719586999148, 1000489713637144623)]
    cases = []
    for index, (suite, expected) in enumerate(zip(temporal, expected_hf), 1):
        before = metric(suite, "NQC_TIME_ONLY_HF_BEFORE_WAD")
        after = metric(suite, "NQC_TIME_ONLY_HF_AFTER_WAD")
        crossed = metric(suite, "NQC_TIME_ONLY_CROSSED_BELOW_ONE")
        need((before, after) == expected and crossed == int(after < 10**18), "temporal measurement mismatch")
        cases.append({"historical_rank": index, "hf_before_wad": str(before), "hf_time_only_wad": str(after),
                      "time_only_below_one": bool(crossed), "source_measurements": suite["metrics"],
                      "selection": "RETROSPECTIVE_FUTURE_WINNERS_NOT_PREDICTIVE_VALIDATION"})
    fork, gas = observations[RUNS[2]]["suites"][0], observations[RUNS[3]]["suites"][0]
    for suite in (fork, gas):
        need(metric(suite, "NQC_RANK1_FORK_WETH_SURPLUS_WEI") == 90814117763741536
             and metric(suite, "NQC_RANK1_FORK_FLASH_FEE_WEI") == 5342006927278914
             and metric(suite, "NQC_RANK1_FORK_PRODUCTION_GAS_SPONSORED") == 0, "fork quantities/nonclaims changed")
    call_gas = metric(gas, "NQC_RANK1_FORK_EXECUTE_CALL_GAS_UNITS")
    need(call_gas == 562357, "original measured call gas changed")
    _, match = exact_line(observations[RUNS[3]]["records"],
        r"RMC016_RANK1_FORK_GAS_BREAK_EVEN_SENSITIVITY_DIAGNOSTIC_NOT_NET physical_call_gas (\d+) "
        r"historical_base_fee_wei (\d+) budget_cases_positive (\d+) nexus_net_pnl_UNPROVEN")
    need(tuple(map(int, match.groups())) == (call_gas, 59451728, 5), "gas summary differs from physical output")
    compatibility, _ = exact_line(observations[RUNS[0]]["records"],
        r"RMC011_WETH_A1_SINGLE_FORK_PHYSICAL_BEHAVIOR_9_PASS_NOT_CERTIFIED runtime_code_sha256 "
        r"5566bf50796faf93c9b6f6adacd3b32c70bfe16b48ffc59db6cd144cbdc89739")
    price_pin = PINS[-1]
    price_path = archive_root/price_pin[2]
    price_ref = transport(price_pin, parse((HERE/f"evidence/winner-api/{price_pin[0]}.json").read_bytes()),
                          price_path.read_bytes())
    price_doc = parse(archive(price_path)["top-two-weth-prices.json"])
    price_sha = price_doc.pop("report_sha256")
    need(sha(canonical(price_doc)) == price_sha and price_doc["real_market_census_closed"] is False
         and price_doc["exact_intratransaction_price_proven"] is False, "recovered oracle scope changed")
    refs = [p for p in price_doc["transactions"] if p["transaction_hash"] ==
            "0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba"]
    need(len(refs) == 1 and refs[0]["preblock"]["block"] == 25938047
         and refs[0]["preblock"]["hash"] == "0x42cf44b75185587327a1aa8fc859cc5f49a639e7256547511430d6068b6f09ab"
         and refs[0]["block_end"]["block"] == 25938048
         and refs[0]["block_end"]["hash"] == "0xf143f9988199037938e4dff57aaf24301a4c26770aefc0ec64774954cbf2dbe4",
         "recovered oracle reference changed")
    price = int(refs[0]["preblock"]["oracle_usd_base_1e8"])
    need(price == 250480170000, "source/reference price mismatch")
    economic_path = HERE/"evidence/economics/replay/weth-cost-reference.jsonl"
    need(sha(economic_path.read_bytes()) == "01df779e1160cec7d3455a5979afb36ea9aae5cc9f9480254c6f09c4fa0b8483",
         "reconciled winner economic reference changed")
    winner = [parse(line) for line in economic_path.read_bytes().splitlines()
              if parse(line)["transaction_hash"] == refs[0]["transaction_hash"]]
    need(len(winner) == 1, "winner linkage missing")
    winner = winner[0]
    surplus = 90814117763741536
    need(int(winner["collateral_weth_wei"]) - int(winner["debt_weth_wei"])
         - metric(fork, "NQC_RANK1_FORK_FLASH_FEE_WEI") == surplus,
         "fork surplus inconsistent with separately recovered event quantities")
    rows = []
    for overhead, tip in ((0, 0), (50000, 10**9), (100000, 2*10**9), (200000, 5*10**9), (300000, 10*10**9)):
        units = call_gas + 21000 + overhead
        cost = units * (59451728 + tip)
        remaining = surplus - cost
        rows.append({"observed_fork_call_gas": call_gas, "assumed_intrinsic_floor_gas": 21000,
            "assumed_additional_overhead_gas": overhead, "assumed_tip_wei_per_gas": str(tip),
            "historical_basefee_reported_by_job_wei": "59451728", "modeled_gas_cost_wei": str(cost),
            "conditional_remaining_weth_par_wei": str(remaining),
            "prior_block_reference_usd_wad": str((1 if remaining >= 0 else -1)*(abs(remaining)*price//10**8)),
            "actual_transaction_gas_measured": False, "nqc_native_gas_funding_proven": False,
            "nqc_executable_value_admitted_usd_wad": "0"})
    report = {"schema": "nqc-physical-log-readback-v1", "status": "FOUR_ORIGINAL_JOB_LOGS_RECONCILED_NOT_RECERTIFIED",
        "source_repository": "josuechavando350-png/nexus-engine", "api_snapshot_sha256": api_hash,
        "source_catalog_sha256": ORIGINS_SHA, "source_files": sources,
        "original_runs": [{"pin": observations[r]["pin"], "physical_suites": observations[r]["suites"]} for r in RUNS],
        "historical_physical_test_results_observed": 16, "historical_tests_rerun_here": 0,
        "physical_artifact_zip_bytes_recovered": False, "original_input_archive_chains_reverified_here": False,
        "separate_oracle_archive_verified": price_ref, "oracle_reference": refs[0],
        "economic_reference_sha256": sha(economic_path.read_bytes()), "event_to_fork_surplus_integer_parity": True,
        "historical_underlying_rpc_bytes_recovered": False, "independent_fork_reexecution_here": False,
        "weth_compatibility": {"asset": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "chain_id": 1,
            "block_number": 26095351, "block_hash": "0x0d7a15fbb72e69696a33c65bc20902fe08e5630862ada64b065a97405c70c781",
            "physical_test_results": 9, "output_record": compatibility, "global_token_admission_changed": False},
        "time_only_cases": cases,
        "counterfactual_execution": {"previous_block": 25938047, "simulated_block": 25938048,
            "historical_reference_transaction": "0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba",
            "principal_weth_wei": "10684013854557827871", "observed_flash_fee_weth_wei": "5342006927278914",
            "fork_only_remaining_weth_before_gas_wei": str(surplus), "measured_execute_call_gas": call_gas,
            "fixture_minted_weth_for_principal_or_fee_reported": "0",
            "original_intrablock_transactions_replayed": False,
            "execution_claim_basis": "ORIGINAL_SOURCE_AND_LOGGED_TEST_RESULTS_NOT_NEW_FORK_REPLAY",
            "test_plan_hashes_are_authenticated_financing": False, "actual_transaction_receipt": None},
        "gas_sensitivities": rows, "call_gas_and_basefee_are_prior_job_reported_values": True,
        "gas_sensitivity_is_full_cost_or_capture_model": False, "original_decision_time_observation_proven": False,
        "capital_policy_id": "NQC_GAS_ONLY_MXN_2000_20261009", "own_gas_amendment_applied_retroactively": False,
        "capital_or_execution_admission_changed": False, "positive_nqc_executable_value": False,
        "real_market_census_closed": False, "independent_certification_issued": False,
        "mismatches": [], "verifier_sha256": sha(Path(__file__).read_bytes())}
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, default=EVIDENCE)
    p.add_argument("--archive-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    need(not a.output.exists(), "append-only output required")
    report = verify(a.archive_root, a.evidence)
    a.output.write_bytes(canonical(report))
    print(report["status"], "physical_results", report["historical_physical_test_results_observed"], "census_closed=false")
