#!/usr/bin/env python3
"""Measure full D11 replay; historical metadata are serialization parameters only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def run(binary, replay, out, staged=False):
    if out.exists():
        raise ValueError("new append-only output required")
    out.mkdir(parents=True)
    manifest = json.loads((Path(__file__).parent / "overlay-manifest.json").read_bytes())
    command = [str(binary), "--d08-dir", str(replay/"d08-raw/closeout"),
               "--d09-dir", str(replay/"d09-raw/closeout"),
               "--authority-lock", str(replay/"legacy-replay-lock.json"),
               "--output-dir", str(out/"original-metadata-output"),
               "--code-commit", "83395dc182cb7fd31293887f4de86fcd022b4b6d",
               "--code-tree", "1ab7d599776babd5aeb3478d44c3c692fb9ad5d8"]
    envelope = {"schema": "nqc-d11-conditional-memory-replay-v2", "actual_producer_base_commit": manifest["base_commit"],
                "actual_producer_base_tree": manifest["base_tree"], "actual_producer_overlay_sha256": manifest["patch_sha256"],
                "historical_metadata_parameters_are_not_actual_producer_identity": True,
                "original_certification_transferred": False, "new_producer_certified": False,
                "terminal_census_closed": False, "command": command, "binary_sha256": sha(binary),
                "authority_lock_sha256": sha(replay/"legacy-replay-lock.json"),
                "started_at": datetime.now(timezone.utc).isoformat()}
    commands = [(command, dict(os.environ))]
    if staged:
        verifier = binary.parent/"nqc-rmc011-bounded-replay"
        verify_args = [str(verifier), str(out/"original-metadata-output"), str(replay/"d08-raw/closeout"),
                       str(replay/"d09-raw/closeout"), str(replay/"legacy-replay-lock.json"),
                       command[-3], command[-1]]
        commands = [(command, dict(os.environ, NQC_RESEARCH_EXPORT_ONLY="1")),
                    (verify_args + [str(out/"closeout-first.json")], dict(os.environ)),
                    (verify_args + [str(out/"closeout-second.json")], dict(os.environ))]
        envelope.update(bounded_verifier_binary_sha256=sha(verifier), staged=True,
                        commands=[c for c, _ in commands], export_environment={"NQC_RESEARCH_EXPORT_ONLY": "1"})
    (out/"RESEARCH_ONLY.json").write_text(json.dumps(envelope, indent=2) + "\n")
    started = time.monotonic()
    stages = []
    with (out/"process.log").open("wb") as log:
        for index, (cmd, environment) in enumerate(commands):
            stage_started = time.monotonic()
            process = subprocess.Popen(cmd, env=environment, stdout=log, stderr=subprocess.STDOUT)
            while True:
                try:
                    code = process.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    print(json.dumps({"elapsed_seconds": round(time.monotonic()-started, 1), "stage": index,
                                      "status": "RUNNING"}), flush=True)
            stages.append({"index": index, "exit_code": code, "elapsed_seconds": time.monotonic()-stage_started})
            if code:
                break
    if staged and code == 0:
        first, second = (out/"closeout-first.json").read_bytes(), (out/"closeout-second.json").read_bytes()
        if first != second:
            code = 1
            (out/"closeout-mismatch.txt").write_text("Independent process closeouts differ. No final closeout admitted.\n")
        else:
            with (out/"original-metadata-output/capital-real-source-closeout.json").open("xb") as stream:
                stream.write(first)
    measurement = {"exit_code": code, "elapsed_seconds": time.monotonic()-started,
                   "max_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                   "memory_measurement_source": "getrusage(RUSAGE_CHILDREN); maximum child RSS; sequential stages",
                   "stages": stages,
                   "binary_sha256": envelope["binary_sha256"]}
    (out/"measurement.json").write_text(json.dumps(measurement, indent=2) + "\n")
    print(json.dumps(measurement), flush=True)
    return code

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "replay", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.binary.resolve(), args.replay.resolve(), args.out.resolve(), args.staged))
