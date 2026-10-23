#!/usr/bin/env python3
"""Retain one bounded public read attempt; not a report/source certification tool."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

MODULE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE / "scripts"))
from bind_run_config import bind, load_json_strict, validate_about, write_new_atomic
from capture_run import digest, safe_path, step


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "template", "plan", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.timeout_seconds <= 600:
        parser.error("timeout must be 1..600 seconds")
    binary, template, plan, output = map(safe_path, (args.binary, args.template, args.plan, args.output))
    candidate, planned = load_json_strict(template), load_json_strict(plan)
    output.mkdir(mode=0o700, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    before = digest(binary)
    inputs = {"template": digest(template), "plan": digest(plan)}
    checks = [step(output, "about-before", [str(binary), "about"], 30)]
    if checks[-1]["exit_code"] != 0:
        raise RuntimeError("about failed; partial output retained")
    about = load_json_strict(output / "about-before.stdout")
    validate_about(about)
    config = bind(candidate, about)
    write_new_atomic(output / "config.json", config)
    write_new_atomic(output / "plan.json", planned)
    checks.append(step(output, "validate-plan", [str(binary), "validate-aave-plan", "--config",
                       str(output / "config.json"), "--plan", str(output / "plan.json")], 30))
    if checks[-1]["exit_code"] == 0:
        checks.append(step(output, "read-state", [str(binary), "read-aave-state", "--config",
                           str(output / "config.json"), "--plan", str(output / "plan.json")], args.timeout_seconds))
    checks.append(step(output, "about-after", [str(binary), "about"], 30))
    same = before == digest(binary) and inputs == {"template": digest(template), "plan": digest(plan)}
    same = same and (output / "about-before.stdout").read_bytes() == (output / "about-after.stdout").read_bytes()
    returned = same and len(checks) == 4 and all(c["exit_code"] == 0 for c in checks)
    summary = {
        "schema": "nqc-miner-aave-read-attempt-v1", "producer": "nqc-miner", "namespace": "nqc_miner_v1",
        "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "returned_report_requires_offline_audit" if returned else "incomplete_or_rejected",
        "binary_sha256": before, "binary_and_inputs_unchanged": same, "input_sha256": inputs,
        "checks": checks, "report_returned": returned, "source_and_report_audit_completed": False,
        "transport_context": "public_rpc", "new_certified_measurements": 0,
        "observer_bridge_enabled": False, "economic_certification": False, "activation_allowed": False,
        "files": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    write_new_atomic(output / "execution.json", summary)
    print(json.dumps({"status": summary["status"], "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
