#!/usr/bin/env python3
"""Reproduce negative checks on the independent retained-report auditor."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2]
ROOT = MODULE / "evidence/aave-state-public-attempt-20261023"
spec = importlib.util.spec_from_file_location("audit_aave_evidence", ROOT / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = ROOT / "history-001"
    report = audit.load(run / "read-state.stdout")
    config, plan = audit.load(run / "config.json"), audit.load(run / "plan.json")
    source = json.loads((MODULE / "evidence/public-capture-v2-20261022/state/events.jsonl").read_bytes().splitlines()[2])["record"]
    audit.audit_report(report, config, plan, source)
    cases = [
        ("owner", ("owner", "run_id"), "foreign"),
        ("plan", ("plan", "borrower"), "0x" + "1" * 40),
        ("plan_hash", ("plan_sha256",), "0" * 64),
        ("providers", ("providers",), ["ethereum-primary"]),
        ("sample_gap", ("samples",), report["samples"][:-1]),
        ("parent", ("samples", 1, "block", "parent_hash"), "0x" + "1" * 64),
        ("unpinned_call", ("samples", 0, "calls", 0, "params", 1), "latest"),
        ("wrong_target", ("samples", 0, "calls", 0, "params", 0, "to"), "0x" + "1" * 40),
        ("wrong_selector", ("samples", 0, "calls", 0, "params", 0, "data"), "0x00000000"),
        ("numeric_boolean", ("samples", 0, "calls", 0, "params", 1, "requireCanonical"), 1),
        ("provider_reply_disagreement", ("samples", 0, "calls", 0, "replies", 1, "result"), "0x" + "0" * 64),
        ("truncated_ABI", ("samples", 0, "calls", 4, "replies", 0, "result"), "0x"),
        ("changed_price", ("samples", 0, "prices", 0, "price_base"), "1"),
        ("changed_health", ("samples", 0, "account", "health_factor_wad"), "1"),
        ("false_episode", ("breach_episodes",), []),
        ("invented_eligibility", ("first_eligible_block",), 26248113),
        ("false_certification", ("economic_certification",), True),
        ("oracle_change_flag", ("oracle_configuration_changed",), True),
    ]
    for name, path, value in cases:
        modified = copy.deepcopy(report)
        cursor = modified
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        try:
            audit.audit_report(modified, config, plan, source)
        except (ValueError, KeyError, TypeError, StopIteration):
            continue
        raise RuntimeError("mutation accepted: " + name)
    result = {"status": "pass", "original_report_accepted": True,
              "negative_mutations_rejected": [c[0] for c in cases], "count": len(cases),
              "auditor_sha256": audit.sha((ROOT / "audit.py").read_bytes()),
              "new_live_reads": 0, "economic_certification": False}
    audit.write_new_atomic(args.output, result)
    print(json.dumps({"status": "pass", "mutations_rejected": len(cases)}))


if __name__ == "__main__":
    main()
