#!/usr/bin/env python3
"""Read back pinned historical D06-D10 bytes without transferring certification.

Metadata must be acquired independently through authenticated GitHub APIs.
ZIP and manifest integrity is verified in streaming reads; no archive is extracted.
The output is a transport/coherence report, never an upstream authority lock.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / "ci/nqc-census/rmc011-real-source-inputs.json"
KEYS = ("d06", "d07", "d08", "d09", "d10")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(a, b, label):
    require(type(a) is type(b) and a == b, label + ": mismatch")


def parse(data):
    def pairs(rows):
        result = {}
        for k, v in rows:
            require(k not in result, "duplicate JSON field: " + k)
            result[k] = v
        return result
    def constant(v):
        raise ValueError("invalid JSON number: " + v)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def digest(stream):
    h = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(chunk)
        size += len(chunk)
    return h.hexdigest(), size


def safe(name):
    require(type(name) is str and bool(name) and "\\" not in name and "\x00" not in name,
            "unsafe archive name")
    p = PurePosixPath(name)
    require(bool(p.parts) and not p.is_absolute() and ".." not in p.parts and str(p) == name, "unsafe archive path")
    return name


def small(z, name):
    require(z.getinfo(name).file_size <= 2 * 1024 * 1024, "metadata file too large")
    return parse(z.read(name))


def transport(pin, snapshots, repository):
    run, art, commit = (parse(snapshots[k]) for k in ("run", "artifact", "commit"))
    for k, v in {"id": pin["run_id"], "head_sha": pin["head_sha"],
                 "name": pin["workflow_name"], "status": "completed", "conclusion": "success"}.items():
        equal(run.get(k), v, "run " + k)
    equal(run["repository"]["full_name"], repository, "repository")
    equal(run["repository"]["id"], 1333360261, "repository id")
    equal(run["head_repository"]["id"], 1333360261, "head repository id")
    for k, v in {"id": pin["artifact_id"], "name": pin["artifact_name"],
                 "digest": pin["artifact_digest"], "expired": False}.items():
        equal(art.get(k), v, "artifact " + k)
    equal(art["workflow_run"]["id"], pin["run_id"], "artifact run")
    equal(art["workflow_run"]["head_sha"], pin["head_sha"], "artifact head")
    equal(art["workflow_run"]["repository_id"], 1333360261, "artifact repository id")
    equal(commit["sha"], pin["head_sha"], "commit identity")
    tree = commit["commit"]["tree"]["sha"]
    equal(run["head_commit"]["id"], pin["head_sha"], "run commit")
    equal(run["head_commit"]["tree_id"], tree, "run tree")
    # Retained bytes remain reproducible after remote retention expires.
    # Check the captured metadata's lifetime, not today's wall clock. This
    # establishes no claim that GitHub still serves the artifact today.
    created = dt.datetime.fromisoformat(art["created_at"].replace("Z", "+00:00"))
    updated = dt.datetime.fromisoformat(art["updated_at"].replace("Z", "+00:00"))
    expiry = dt.datetime.fromisoformat(art["expires_at"].replace("Z", "+00:00"))
    require(all(x.tzinfo is not None for x in (created, updated, expiry))
            and created <= updated < expiry, "invalid captured artifact lifetime")
    return art, tree, run["event"]


def archive(path, pin, art, tree):
    require(path.is_file() and not path.is_symlink(), "regular archive required")
    with path.open("rb") as stream:
        sha, size = digest(stream)
    equal("sha256:" + sha, pin["artifact_digest"], "archive digest")
    equal(size, art["size_in_bytes"], "archive size")
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        require(len(infos) <= 10000 and sum(i.file_size for i in infos) <= 2 * 1024**3,
                "archive expansion limit")
        names = set()
        inventory = {}
        for entry in infos:
            name = safe(entry.filename)
            equal(entry.orig_filename, name, "original ZIP filename")
            require(name.casefold() not in names, "duplicate ZIP entry")
            names.add(name.casefold())
            require(not entry.is_dir() and not entry.flag_bits & 1 and
                    stat.S_IFMT(entry.external_attr >> 16) in (0, stat.S_IFREG), "special ZIP entry")
            with z.open(name) as stream:
                h, n = digest(stream)
            equal(n, entry.file_size, "expanded member size")
            inventory[name] = {"sha256": h, "bytes": n}
        manifest = small(z, "closeout/evidence-manifest.json")
        # D10 contains incremental D09 output; its producer identity is in its certificate.
        authority = small(z, pin["authority_file"])
        equal(authority["code_commit"], pin["head_sha"], "authority commit")
        equal(authority["code_tree"], tree, "authority tree")
        listed = set()
        for row in manifest["artifacts"]:
            field = "name" if pin["artifact_id"] in (11143129177, 11207794300) else "path"
            name = "closeout/" + safe(row[field])
            require(name not in listed, "duplicate manifest artifact")
            listed.add(name)
            equal(inventory[name]["sha256"], row["sha256"], "manifest artifact hash")
            equal(inventory[name]["bytes"], row["bytes"], "manifest artifact size")
        docs = {n: small(z, n) for n in z.namelist()
                if n in {"closeout/aave-discovery-run.json", "closeout/v2-discovery-run.json",
                         "closeout/evidence-manifest.json", "closeout/state-summary.json",
                         "closeout/account-summary.json", "rmc010-certification.json"}}
    return {"archive_sha256": sha, "archive_bytes": size, "members": len(infos),
            "expanded_bytes": sum(i.file_size for i in infos), "manifest_artifacts_verified": len(listed),
            "authority_sha256": inventory[pin["authority_file"]]["sha256"],
            "code_commit": pin["head_sha"], "code_tree": tree}, docs


def coherence(pins, reports, docs):
    # Reuse the unchanged historical semantic consumer. Its disk reader is
    # replaced locally with a lookup of already authenticated archive members.
    spec = importlib.util.spec_from_file_location("original_coherence", ROOT / "ci/nqc-census/verify-rmc011-upstream-coherence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    anchor = docs["d08"]["closeout/evidence-manifest.json"]["observation_anchor"]
    refs = {"schema_version": 1, "stages": [
        {"stage": "RMC-0" + k[1:], "code_commit": reports[k]["code_commit"],
         "artifact_sha256": reports[k]["authority_sha256"], "observation_anchor": anchor}
        for k in KEYS]}
    lookup = {"inputs": pins, "references": refs}
    for k, files in docs.items():
        lookup.update({k + "-raw/" + n: doc for n, doc in files.items()})
    module.load_json = lambda p: lookup[str(p)]
    with contextlib.redirect_stdout(io.StringIO()):
        module.verify(Path("inputs"), Path("references"), Path("."))
    return anchor


def verify(archive_root, metadata_root):
    pins_raw = PINS.read_bytes()
    pins = parse(pins_raw)
    reports, docs = {}, {}
    for stage in KEYS:
        snapshots = {kind: (metadata_root / stage / (kind + ".json")).read_bytes()
                     for kind in ("run", "artifact", "commit")}
        art, tree, event = transport(pins[stage], snapshots, pins["repository"])
        reports[stage], docs[stage] = archive(archive_root / (stage + "-original.zip"), pins[stage], art, tree)
        reports[stage].update({"run_id": pins[stage]["run_id"], "artifact_id": pins[stage]["artifact_id"],
                              "event": event, "metadata_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in snapshots.items()}})
    anchor = coherence(pins, reports, docs)
    return {"schema": "nqc-historical-upstream-readback-v1", "status": "PINNED_BYTES_AND_ANCHOR_COHERENCE_PASS",
            "verifier_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "original_coherence_consumer_sha256": hashlib.sha256((ROOT / "ci/nqc-census/verify-rmc011-upstream-coherence.py").read_bytes()).hexdigest(),
            "verified_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "pin_file_sha256": hashlib.sha256(pins_raw).hexdigest(), "stages": reports, "observation_anchor": anchor,
            "d08_summary": docs["d08"]["closeout/state-summary.json"],
            "d09_summary": docs["d09"]["closeout/account-summary.json"],
            "metadata_origin": "CALLER_ACQUIRED_AUTHENTICATED_GITHUB_API_RESPONSES",
            "historical_semantic_producers_reexecuted": False, "upstream_authority_lock_issued": False,
            "canonical_recertification": False, "d11_terminal_closed": False, "real_market_census_closed": False,
            "decision_time_availability_proven": False,
            "non_claims": ["NO_CERTIFICATION_TRANSFER", "NO_LIVE_STATE", "NO_CAPITAL_OR_EXECUTION_AUTHORITY",
                           "NO_PROFITABILITY", "NO_INDEPENDENT_PROTOCOL_OR_ACCOUNT_RECONSTRUCTION"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root", type=Path, required=True)
    p.add_argument("--metadata-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    report = verify(a.archive_root, a.metadata_root)
    with a.output.open("x") as out:
        json.dump(report, out, sort_keys=True, indent=2)
        out.write("\n")
    print(report["status"])


if __name__ == "__main__":
    main()
