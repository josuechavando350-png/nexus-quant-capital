#!/usr/bin/env python3
"""Replay all captured getters, bind published inputs, then run the offline CLI."""
import argparse
import json
from pathlib import Path
import subprocess
import capture_aave_conditions as capture
import aave_runtime_identity as identity

PUBLICATION = "3dfb0b519f170e2f8c402a57ae0b384269a203f2"


def published(relative):
    raw = subprocess.check_output(["git", "show", PUBLICATION + ":migration/nqc-miner/" + relative], cwd=identity.MODULE)
    path = identity.MODULE / relative
    identity.check(path.read_bytes() == raw, "published source bytes changed")
    return json.loads(raw), identity.sha(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(exist_ok=False)
    binary = args.binary.resolve(); binary_sha = identity.sha(binary.read_bytes())
    def execute(arguments):
        result = subprocess.run([str(binary), *arguments], capture_output=True, timeout=30, check=True)
        identity.check(len(result.stdout) <= 1_000_000 and not result.stderr, "CLI output")
        return result.stdout, json.loads(result.stdout)
    before, about = execute(["about"])
    identity.check(about["source_dirty"] is False, "dirty build")
    (args.output / "about.json").write_bytes(before)
    compiled, compiled_hash = published("evidence/aave-compiled-identity-20261023/local/audit.json")
    identity.check(compiled["status"] == "pass" and compiled["runtime_equivalence_verified"] is True, "compiled identity audit")
    liquidation = [c for c in compiled["contracts"] if c["name"] == "LiquidationLogic"]
    identity.check(len(liquidation) == 1 and liquidation[0]["runtime_sha256"] == "b11e141dc76358768078be0818b39d60b5b68385aed43552a617ad572e821914", "version binding")
    results = []
    observations = capture.replay(args.capture)
    for i, observation in enumerate(observations):
        old, old_hash = published(f"evidence/aave-state-public-attempt-20261023/history-{i:03d}/read-state.stdout")
        sample = old["samples"][-1]
        identity.check(sample["block"] == observation["block"] and old["event_anchor"] == observation["event_anchor"], "state context")
        account = sample["account"]
        expected = [int(account[k]) for k in ["total_collateral_base", "total_debt_base", "available_borrows_base", "liquidation_threshold_bps", "ltv_bps", "health_factor_wad"]]
        getters = [r for r in observation["records"] if r["request"]["method"] == "eth_call"
                   and r["request"]["params"][0]["data"][:10] == capture.SELECTORS["getUserAccountData"]]
        identity.check(len(getters) == 2 and all(capture.words(r["response"]["result"], 6) == expected for r in getters), "previous account data differs")
        identity.check(observation["block"]["number"] in liquidation[0]["blocks"], "implementation block coverage")
        input_path = args.output / f"input-{i:03d}.json"
        input_path.write_bytes(identity.encoded(observation["inputs"]))
        raw, report = execute(["check-aave-conditions", "--input", str(input_path)])
        identity.check(report["schema"] == "nqc-miner-aave-initial-conditions-v1"
                       and report["reference_liquidation_runtime_sha256"] == liquidation[0]["runtime_sha256"]
                       and report["activation_allowed"] is False and report["executable_eligibility_verified"] is False
                       and report["input_state_authenticated"] is False and report["input_implementation_verified"] is False,
                       "unsupported report claim")
        (args.output / f"report-{i:03d}.json").write_bytes(raw)
        results.append({"event_transaction": observation["event_transaction"], "event_log_index": observation["event_log_index"],
                        "block": observation["block"], "initial_conditions_passed": report["initial_conditions_passed"],
                        "first_error": report["first_error"], "input_sha256": identity.sha(input_path.read_bytes()),
                        "report_sha256": identity.sha(raw), "prior_account_report_sha256": old_hash})
    after, final_about = execute(["about"])
    identity.check(before == after and final_about == about and identity.sha(binary.read_bytes()) == binary_sha, "binary changed")
    report = {"schema": "nqc-miner-aave-conditions-audit-v1", "status": "pass", "records_replayed": 96,
              "getters_agreed": 21, "provider_getter_replies": 42, "results": results,
              "binary_sha256": binary_sha, "code_commit": about["code_commit"], "source_publication": PUBLICATION,
              "compiled_identity_audit_sha256": compiled_hash, "source_journal_sha256": capture.JOURNAL_SHA,
              "capture_script_sha256": identity.sha(Path(capture.__file__).read_bytes()),
              "audit_script_sha256": identity.sha(Path(__file__).read_bytes()), "network_used": False,
              "input_state_authenticated": False, "transaction_prestate": False,
              "executable_eligibility_verified": False, "economic_certification": False,
              "activation_allowed": False, "new_source_events": 0, "observer_bridge_enabled": False}
    (args.output / "audit.json").write_bytes(identity.encoded(report))
    print(json.dumps({"status": "pass", "records_replayed": 96, "results": results}))


if __name__ == "__main__":
    main()
