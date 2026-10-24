#!/usr/bin/env python3
"""Replay the fixed proxy probe against retained provider records, without RPC."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("proxy_capture", ROOT / "capture.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory = ROOT / "public"
    manifest = probe.load(directory / "manifest.json")
    probe.check(manifest["complete"] is True and len(manifest["observations"]) == 3 and manifest["requests"] == 72, "incomplete capture")
    probe.check(manifest["capture_sha256"] == probe.sha((ROOT / "capture.py").read_bytes()), "capture source changed")
    results = []
    for i, entry in enumerate(manifest["observations"]):
        probe.check(entry["file"] == f"proxy-{i:03d}.json", "unexpected output")
        original_path = directory / entry["file"]
        probe.check(probe.sha(original_path.read_bytes()) == entry["sha256"], "report changed")
        original = probe.load(original_path)
        relative = f"evidence/aave-state-public-attempt-20261023/history-{i:03d}/read-state.stdout"
        probe.check(original["source_report"] == relative, "foreign source report")
        source = probe.MODULE / relative
        published = subprocess.check_output(["git", "show", "f7a96bc0ba7af395453491cb001f1648b42e4864:migration/nqc-miner/" + relative], cwd=probe.MODULE)
        probe.check(source.read_bytes() == published and probe.sha(published) == original["source_report_sha256"], "source differs from audited publication")
        records = iter(original["records"])
        count = 0

        def replay(provider, method, params):
            nonlocal count
            r = next(records)
            count += 1
            req, response = r["request"], r["response"]
            probe.check(r["provider_id"] == provider and req["method"] == method and probe.same(req["params"], params), "request replay mismatch")
            probe.check(req["jsonrpc"] == response["jsonrpc"] == "2.0" and type(req["id"]) is int
                        and type(response["id"]) is int and req["id"] == response["id"] == i * 24 + count
                        and "error" not in response, "RPC identity/error")
            return {"request": req, "response": response}

        result = probe.capture_one(probe.load(source), replay)
        probe.check(next(records, None) is None and count == 24, "extra/missing calls")
        result.update(source_report=relative, source_report_sha256=probe.sha(published))
        probe.check(probe.same(result, original), "derived identity differs from retained records")
        results.append({"block": result["block"]["number"], "implementation": result["implementation"],
                        "implementation_runtime_sha256": result["implementation_runtime_sha256"],
                        "implementation_bytes": result["implementation_bytes"], "records_replayed": count})
    probe.save(args.output, {"schema": "nqc-miner-aave-proxy-audit-v1", "status": "pass", "results": results,
         "capture_sha256": probe.sha((ROOT / "capture.py").read_bytes()), "auditor_sha256": probe.sha(Path(__file__).read_bytes()),
         "source_publication": "f7a96bc0ba7af395453491cb001f1648b42e4864", "network_used": False,
         "state_authentication_verified": False, "protocol_version_verified": False,
         "implementation_source_match_verified": False, "economic_certification": False, "observer_bridge_enabled": False})
    print(json.dumps({"status": "pass", "records_replayed": sum(r["records_replayed"] for r in results), "results": results}))


if __name__ == "__main__":
    main()
