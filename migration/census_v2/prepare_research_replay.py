#!/usr/bin/env python3
"""Prepare actual pinned inputs for a NON-CERTIFYING historical Rust replay.

This does not acquire new authority. The legacy lock builder encodes affirmative
authority flags; its output may be used only inside this explicitly conditional
research replay until an independent authority accepts each prerequisite.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import verify_historical_inputs as historical


def prepare(archive_root, metadata_root, out):
    historical.require(not out.exists(), "research output directory already exists")
    report = historical.verify(archive_root, metadata_root)
    pins = historical.parse(historical.PINS.read_bytes())
    out.mkdir(parents=True)
    stages = []
    for stage in historical.KEYS:
        ref = report["stages"][stage]
        stages.append({"stage": "RMC-0" + stage[1:], "code_commit": ref["code_commit"],
                       "code_tree": ref["code_tree"], "artifact_sha256": "0x" + ref["authority_sha256"]})
        root = out / (stage + "-raw")
        root.mkdir()
        with zipfile.ZipFile(archive_root / (stage + "-original.zip")) as z:
            # Archives were fully authenticated and path-checked above. Only
            # original closeout records and declared authority are materialized.
            for info in z.infolist():
                if not (info.filename.startswith("closeout/") or info.filename == pins[stage]["authority_file"]):
                    continue
                p = root / info.filename
                p.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, p.open("xb") as dest:
                    shutil.copyfileobj(src, dest, 1024 * 1024)
                historical.equal(p.stat().st_size, info.file_size, "materialized bytes")
    candidate = {"schema_version": 1, "observation_anchor": report["observation_anchor"], "stages": stages}
    (out / "legacy-replay-lock-candidate.json").write_text(json.dumps(candidate, sort_keys=True) + "\n")
    (out / "transport-readback.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    envelope = {"schema": "nqc-conditional-historical-replay-v1",
                "purpose": "REPRODUCE_ORIGINAL_ZERO_OWN_CAPITAL_CALCULATION_ONLY",
                "legacy_authority_flags_are_replay_assumptions": True,
                "independent_prerequisite_certification_granted": False,
                "new_gas_budget_applied_retroactively": False,
                "decision_time_availability_proven": False,
                "canonical_recertification": False, "downstream_acceptance": False,
                "real_market_census_closed": False,
                "prepare_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out / "RESEARCH_ONLY.json").write_text(json.dumps(envelope, sort_keys=True, indent=2) + "\n")
    return envelope


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root", type=Path, required=True)
    p.add_argument("--metadata-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    prepare(a.archive_root, a.metadata_root, a.out)
    print("REAL_INPUTS_PREPARED_FOR_CONDITIONAL_RESEARCH_REPLAY_ONLY")
