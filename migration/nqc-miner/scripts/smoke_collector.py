#!/usr/bin/env python3
"""Finite collector smoke test: two windows, process restart, one further window.

Preserves failures and exact file hashes. Does not start a persistent service.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from bind_run_config import BindError, bind, load_json_strict, validate_about, write_new_atomic
from capture_run import digest, safe_path, step


def classify(config, checks, first, final, polls, same_binary, previous_unchanged, config_hash):
    required = {"about-before", "validate", "follow-initial", "verify-initial",
                "follow-resumed", "verify-final", "about-after"}
    if required != {c["name"] for c in checks if c["exit_code"] == 0}:
        return "incomplete_or_rejected"
    scope = config["scopes"][0]
    width = scope["to_block"] - scope["from_block"] + 1
    for count, report in ((2, first), (3, final)):
        if not (report.get("schema") == "nqc-miner-collector-status-v1"
                and report.get("run_id") == config["run_id"]
                and report.get("plan_sha256") == config_hash
                and report.get("completed_windows") == count
                and report.get("incomplete_window") is False
                and report.get("next_from_block") == scope["from_block"] + count * width
                and report.get("integrity_verified") is True
                and report.get("data_class") == "historical"
                and all(report.get(k) is False for k in
                        ("observer_bridge_enabled", "signing_enabled", "economic_certification", "chain_authenticity_verified"))):
            return "incomplete_or_rejected"
    expected = [{"status": "completed", "window_index": i,
                 "from_block": scope["from_block"] + i * width,
                 "to_block": scope["to_block"] + i * width} for i in range(3)]
    if polls != expected or not same_binary or not previous_unchanged:
        return "incomplete_or_rejected"
    return "complete_bounded_restart_smoke"


def capture(binary, template, output, timeout, transport_context):
    binary, template, output = map(safe_path, (binary, template, output))
    if not 1 <= timeout <= 3600:
        raise BindError("timeout must be 1..3600 seconds")
    candidate = load_json_strict(template)
    if len(candidate.get("scopes", [])) != 1 or candidate.get("data_class") != "historical":
        raise BindError("smoke test requires exactly one historical scope")
    output.mkdir(mode=0o700, exist_ok=False)
    checks, first, final, polls, prior = [], {}, {}, [], {}
    config, config_hash, rejection = None, None, None
    before = digest(binary)
    started = datetime.now(timezone.utc).isoformat()
    try:
        checks.append(step(output, "about-before", [str(binary), "about"], 30))
        about = load_json_strict(output / "about-before.stdout")
        validate_about(about)
        config = bind(candidate, about)
        write_new_atomic(output / "config.json", config)
        args = ["--config", str(output / "config.json"), "--state", str(output / "state")]
        checks.append(step(output, "validate", [str(binary), "validate-config", *args[:2]], 30))
        config_hash = load_json_strict(output / "validate.stdout")["config_sha256"]
        checks.append(step(output, "follow-initial", [str(binary), "follow", *args,
                            "--max-polls", "2", "--poll-seconds", "1"], timeout))
        checks.append(step(output, "verify-initial", [str(binary), "verify-collector", *args], 60))
        first = load_json_strict(output / "verify-initial.stdout")
        prior = {str(p.relative_to(output)): digest(p)
                 for directory in sorted((output / "state").glob("window-*"))
                 for p in sorted(directory.rglob("*")) if p.is_file()}
        if any(check["exit_code"] for check in checks):
            raise BindError("initial collector attempt failed; evidence retained")
        checks.append(step(output, "follow-resumed", [str(binary), "follow", *args,
                            "--max-polls", "1", "--poll-seconds", "1"], timeout))
        checks.append(step(output, "verify-final", [str(binary), "verify-collector", *args], 60))
        final = load_json_strict(output / "verify-final.stdout")
        for name in ("follow-initial", "follow-resumed"):
            polls.extend(json.loads(line)["outcome"] for line in
                         (output / (name + ".stdout")).read_text().splitlines())
    except (BindError, OSError, ValueError, KeyError, TypeError) as exc:
        rejection = type(exc).__name__
    checks.append(step(output, "about-after", [str(binary), "about"], 30))
    try:
        after = digest(binary)
        same = (before == after and checks[0]["exit_code"] == 0 and checks[-1]["exit_code"] == 0
                and (output / "about-before.stdout").read_bytes() == (output / "about-after.stdout").read_bytes())
        unchanged = bool(prior) and all(digest(output / name) == value for name, value in prior.items())
    except OSError:
        after, same, unchanged = None, False, False
    status = (classify(config, checks, first, final, polls, same, unchanged, config_hash)
              if config is not None and rejection is None else "incomplete_or_rejected")
    summary = {"schema": "nqc-miner-collector-smoke-v1", "status": status,
               "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
               "transport_context": transport_context, "checks": checks, "rejection": rejection,
               "binary_before_sha256": before, "binary_after_sha256": after, "binary_unchanged": same,
               "prior_windows_unchanged": unchanged, "prior_window_files": prior,
               "template_sha256": digest(template), "capture_script_sha256": digest(Path(__file__)),
               "completed_windows": final.get("completed_windows", 0),
               "canonical_events": final.get("canonical_events_in_completed_windows", 0),
               "files": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()},
               "observer_bridge_enabled": False, "spending_authorized": False,
               "persistent_service_started": False, "economic_certification": False}
    write_new_atomic(output / "capture.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--transport-context", choices=["public_rpc", "synthetic_fixture"], required=True)
    args = parser.parse_args()
    summary = capture(args.binary, args.template, args.output, args.timeout_seconds, args.transport_context)
    print(json.dumps({k: summary[k] for k in ("status", "completed_windows", "canonical_events", "prior_windows_unchanged")}))
    return 0 if summary["status"] == "complete_bounded_restart_smoke" else 1


if __name__ == "__main__":
    raise SystemExit(main())
