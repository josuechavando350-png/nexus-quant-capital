#!/usr/bin/env python3
"""Reproduce two unchanged historical risk calculations in a fresh directory."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import verify_historical_inputs as historical
from verify_winner_recovery import canonical, need, parse, sha

PIN = "8cb1f3ad20d2d827e9345a079333427cbc4cc93ca49dee51537f67c0b5d7e1b0"
SOURCES = {"risk_screen.py": "d8b8cf4f8f35fcdd1f8f9da297b12c4015b11a3d41aa3dba15faadd60f5b1519",
           "independent_crosscheck.py": "e5933bf209c0d1a7d184366f466b2e2bb3a4b6aac1401e34ff30907d6049f5e6"}
INPUT_NAMES = {"d08": "rmc008-closeout-11237887761.zip", "d09": "rmc009-closeout-11159396055.zip"}


def package(path):
    need(path.is_file() and path.stat().st_size == 2213374 and sha(path.read_bytes()) == PIN,
         "risk package transport pin mismatch")
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        need(len(infos) == 42 and len({i.filename for i in infos}) == 42, "risk package inventory")
        for i in infos:
            historical.safe(i.filename)
            need(not i.is_dir() and not i.flag_bits & 1 and i.file_size <= 15000000
                 and (i.external_attr >> 16) & 0o170000 in (0, 0o100000), "unsafe risk package")
        data = {i.filename: z.read(i) for i in infos}
    inventory = parse(data["evidence-manifest.json"])["files"]
    need(len(inventory) == 41 and {r["path"] for r in inventory} == set(data) - {"evidence-manifest.json"},
         "nonexhaustive risk manifest")
    for row in inventory:
        raw = data[row["path"]]
        need(type(row["bytes"]) is int and len(raw) == row["bytes"] and sha(raw) == row["sha256"],
             "risk member hash mismatch")
    for name, digest in SOURCES.items():
        need(sha(data["code/" + name]) == digest, "risk source pin mismatch")
    return data


def replay(package_path, archive_root, metadata, out):
    need(not out.exists(), "refusing to overwrite risk evidence")
    data = package(package_path)
    pins = historical.parse(historical.PINS.read_bytes())
    upstream = {}
    for stage in INPUT_NAMES:
        snapshots = {kind: (metadata / stage / (kind + ".json")).read_bytes()
                     for kind in ("run", "artifact", "commit")}
        art, tree, _ = historical.transport(pins[stage], snapshots, pins["repository"])
        archive_path = archive_root / (stage + "-original.zip")
        with archive_path.open("rb") as stream:
            digest, size = historical.digest(stream)
        need("sha256:" + digest == pins[stage]["artifact_digest"] and size == art["size_in_bytes"],
             "risk upstream transport mismatch")
        upstream[stage] = {"run_id": pins[stage]["run_id"], "artifact_id": pins[stage]["artifact_id"],
                           "sha256": digest, "commit": pins[stage]["head_sha"], "tree": tree,
                           "api_snapshots": {k: sha(v) for k, v in snapshots.items()}}
    out.mkdir(parents=False, exist_ok=False)
    source_dir, inputs = out / "source", out / "inputs"
    source_dir.mkdir(); inputs.mkdir()
    for name in SOURCES:
        (source_dir / name).write_bytes(data["code/" + name])
    for stage, name in INPUT_NAMES.items():
        shutil.copyfile(archive_root / (stage + "-original.zip"), inputs / name)
    for name in sorted(n for n in data if n.startswith("inputs/")):
        (inputs / Path(name).name).write_bytes(data[name])
    commands = [
        [sys.executable, "-I", "-S", "-B", str(source_dir / "risk_screen.py"),
         "--input-dir", str(inputs), "--output-dir", str(out / "result")],
        [sys.executable, "-I", "-S", "-B", str(source_dir / "independent_crosscheck.py"),
         "--input-dir", str(inputs), "--primary-dir", str(out / "result"), "--output", str(out / "crosscheck.json")],
    ]
    logs = []
    for index, command in enumerate(commands, 1):
        log = out / f"{index}.log"
        with log.open("xb") as handle:
            result = subprocess.run(command, cwd=out, stdout=handle, stderr=subprocess.STDOUT, timeout=120)
        logs.append({"argv": command, "exit_code": result.returncode, "log": log.name,
                     "log_sha256": sha(log.read_bytes())})
        need(result.returncode == 0, "risk replay failed; inspect retained log")
    matches = {}
    for original in sorted(n for n in data if n.startswith("results/")):
        name = Path(original).name
        raw = (out / "result" / name).read_bytes()
        need(raw == data[original], "risk output byte mismatch: " + name)
        matches[name] = {"sha256": sha(raw), "bytes": len(raw)}
    need((out / "crosscheck.json").read_bytes() == data["evidence/independent-crosscheck-with-positions.json"],
         "independent risk output byte mismatch")
    need(all(sha((source_dir / name).read_bytes()) == digest for name, digest in SOURCES.items()),
         "risk source mutated during replay")
    report = {"schema": "nqc-library-risk-replay-v1", "package_sha256": PIN,
              "library_file_id": "libfile_bab59c9b5260819180ba8b7703dd673e",
              "consumer_sha256": sha(Path(__file__).read_bytes()), "sources": SOURCES, "upstream": upstream,
              "commands": logs, "original_outputs_byte_identical": matches,
              "crosscheck_sha256": sha((out / "crosscheck.json").read_bytes()),
              "independent_calculation_paths": 2, "independent_certification_issued": False,
              "original_package_57_tests_rerun": False, "source_producer_commit": None,
              "source_producer_tree": None, "source_provenance": "PINNED_LIBRARY_PACKAGE_NOT_GIT_AUTHORITY",
              "real_market_census_closed": False, "profitability_proven": False,
              "scope": "HISTORICAL_AAVE_V3_CORE_RISK_GETTERS_AND_400_POSITION_VALUATIONS",
              "non_claims": ["No current-state reconstruction or monthly extrapolation",
                             "Collateral is not liquidation bonus, cash proceeds or profit",
                             "Separate calculations do not constitute independent institutional certification",
                             "Historical target flags preserved, superseded by ARCHITECTURE.md for new work"]}
    (out / "replay.json").write_bytes(canonical(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("package", "archive-root", "metadata", "out"):
        parser.add_argument("--" + field, type=lambda p: Path(p).absolute(), required=True)
    args = parser.parse_args()
    print(canonical(replay(args.package, args.archive_root, args.metadata, args.out)).decode(), end="")
