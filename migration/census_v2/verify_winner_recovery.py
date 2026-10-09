#!/usr/bin/env python3
"""Validate authentic winner archives and new raw RPC evidence offline.

Archived failed runs remain failed. A complete substage never promotes its
parent run. Two public operators are not proof of independent execution nodes.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import zipfile

from recover_historical_rpc import canonical, sha, need, decode_response, distinct, PROVIDERS, gather, sortkey
from rmc016_resume_verified_receipts import authenticated_drpc_checkpoint
from rmc016_two_operator_receipts import receipt_normalized
from rmc016_aave_event_legs import bind_logs, authentic_source, decode

PINS = [
    (37718661409, 11524139188, "winner-events-original.zip", "success", "abe54f1f23bd7bff8c37871200f7da7c59c45ac3", "c74f8d9d2c317a011284398643b2d4aa6de06e83", "6b4098c1acf153106ac5b67d2c5c7db5cd0295a16c782ad8c34ae75303306204"),
    (37719091371, 11524199698, "winner-receipts-partial-original.zip", "failure", "569d4aaeecb3d066389c054efed695be02e3ef40", "ba648214fb5cb1cdca1db1f42f28059054d78e63", "182b5e81b00ca04e53c9193c1496a725dc152ade9a17d3ab2dfaeb5045ac86b6"),
    (37720137160, 11525810815, "winner-receipts-resume-original.zip", "failure", "7ec0f23fb7e114c6ac6d873bdb2889f309c2ac50", "3b5f24cee08806403243885e90f662ee75784a85", "b64e15fde2112efa32564a224dbf38b2b338bda35d2aefc68c0cb78b3f6339da"),
    (37722881910, 11526344226, "winner-legs-original.zip", "success", "cd52858444532de581af27c9ba63bb2304d76497", "80e198707e48e99ceddc37e9b4b95b049ccb0ae7", "51dfc4c9c3031a7bf3bb6ce019eb3a9184a1f2327f1accedcc2c6e165af91acb"),
    (37726618359, 11527902751, "winner-weth-prices-original.zip", "success", "a569b0a6ba11c0d12de3a1ac0d16d85b896933f6", "3c84f4fa3a2a0a62accde257029714177dc38b5a", "5ae6c45b53ded26f327270758c248f7f4ec0ff1365f550e54dcf28feb4a83a03"),
]

def parse(raw):
    return json.loads(raw, object_pairs_hook=distinct)

def transport(pin, doc, raw):
    run, artifact_id, name, conclusion, commit, tree, digest = pin
    need(doc["source_repository"] == "josuechavando350-png/nexus-engine", "wrong source repository")
    r, c = doc["run"], doc["commit"]
    need(r["id"] == run and r["status"] == "completed" and r["conclusion"] == conclusion
         and r["event"] == "push" and r["head_sha"] == commit, "run provenance or conclusion mismatch")
    need(r["repository"]["full_name"] == doc["source_repository"], "run repository mismatch")
    need(c["sha"] == commit and c["commit"]["tree"]["sha"] == tree, "commit/tree mismatch")
    matches = [a for a in doc["artifacts"]["artifacts"] if a["id"] == artifact_id]
    need(len(matches) == 1, "missing or duplicate artifact metadata")
    a = matches[0]
    need(a["digest"] == "sha256:" + digest and a["size_in_bytes"] == len(raw)
         and sha(raw) == digest and a["workflow_run"]["id"] == run
         and a["workflow_run"]["head_sha"] == commit, "artifact bytes/identity mismatch")
    return {"run_id": run, "artifact_id": artifact_id, "file": name, "sha256": digest,
            "original_run_conclusion": conclusion, "original_commit": commit, "original_tree": tree,
            "failed_run_promoted": False}

def archive(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        need(len(names) == len(set(names)) and "archive.sha256" in names, "archive duplicate or missing manifest")
        need(all(Path(n).name == n and re.fullmatch(r"[A-Za-z0-9._-]+", n) for n in names), "unsafe archive path")
        need(all(i.file_size <= 2_000_000 and (i.external_attr >> 16) & 0o170000 != 0o120000 for i in z.infolist()), "archive size/symlink")
        data = {n: z.read(n) for n in names}
    seen = set()
    for line in data["archive.sha256"].decode("ascii").splitlines():
        digest, name = line.split("  ")
        need(name in data and name != "archive.sha256" and name not in seen and sha(data[name]) == digest, "inner archive mismatch")
        seen.add(name)
    need(seen == set(data) - {"archive.sha256"}, "incomplete archive manifest")
    return data

def rpc_records(directory, allow_partial=False):
    manifest = parse((directory/"manifest.json").read_bytes())
    seen = set()
    for entry in manifest:
        rel = entry["path"]
        need(type(rel) is str and not Path(rel).is_absolute() and ".." not in Path(rel).parts
             and rel not in seen and rel != "manifest.json", "unsafe/duplicate manifest path")
        path = directory/rel
        need(not path.is_symlink() and path.is_file(), "missing/symlink witness")
        raw = path.read_bytes()
        need(len(raw) == entry["size"] and sha(raw) == entry["sha256"], "witness manifest mismatch")
        seen.add(rel)
    need(seen == {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()} - {"manifest.json"}, "manifest inventory mismatch")
    rows = [parse(line) for line in (directory/"rpc/decision-time-ledger.jsonl").read_bytes().splitlines()]
    records = []
    last = None
    for i, row in enumerate(rows, 1):
        need(row["sequence"] == i, "non-contiguous request chronology")
        sent, received = datetime.fromisoformat(row["sent_at"]), datetime.fromisoformat(row["received_at"])
        need(sent.tzinfo is not None and received.tzinfo is not None and sent <= received
             and (last is None or last <= sent), "invalid acquisition chronology")
        last = received
        prefix = directory/"rpc"/f"{i:06d}"
        request = prefix.with_suffix(".request.json").read_bytes()
        response = prefix.with_suffix(".response.json").read_bytes()
        need(sha(request) == row["request_sha256"] and sha(response) == row["response_sha256"], "ledger bytes mismatch")
        request = parse(request)
        need(request["id"] == i and row["method"] == request["method"], "request binding mismatch")
        need(row["original_decision_time_observation_proven"] is False, "retroactive decision-time claim")
        if row["status"] != "RESPONSE_CAPTURED":
            need(allow_partial and row["status"] == "FAILED" and i == len(rows)
                 and type(row.get("failure")) is str, "failed request cannot certify recovery")
            records.append((row, request, None))
        else:
            need(row["http_status"] == 200, "successful response status mismatch")
            records.append((row, request, decode_response(response, i)))
    return records

def verify(archive_root, metadata, rpc_dirs, allow_partial=False):
    recovered = []
    contents = {}
    for pin in PINS:
        name = pin[2]
        path = archive_root/name
        recovered.append(transport(pin, parse((metadata/f"{pin[0]}.json").read_bytes()), path.read_bytes()))
        contents[name] = archive(path)
    event_zip = archive_root/"winner-events-original.zip"
    rows, events, tids = authenticated_drpc_checkpoint(archive_root/"winner-receipts-partial-original.zip", event_zip)
    receipt_sources, log_sources, derived_legs, acquisitions = {}, [], [], []
    partial_logs, failures = [], []
    expected = sorted([e for group in events.values() for e in group], key=sortkey)
    for directory in rpc_dirs:
        report = parse((directory/"recovery-report.json").read_bytes())
        partial = report["status"] == "BLOCKED"
        need(report["status"] in {"FULL_RECEIPT_CHECKPOINT_MATCH", "FULL_WINDOW_EVENTS_MATCH"}
             or (partial and allow_partial), "incomplete recovery input")
        provider = next(p for p in PROVIDERS if p[0] == report["provider_id"])
        records = rpc_records(directory, allow_partial=partial)
        need(len(records) == report["rpc_calls"], "request count differs")
        need(all(r[0]["url"] == provider[2] and r[0]["operator"] == provider[1]
                 and r[0]["provider_id"] == provider[0] for r in records), "source attribution mismatch")
        acquisitions.append({"directory": directory.name, "operator": provider[1], "calls": len(records),
                             "first_sent_at": records[0][0]["sent_at"], "last_received_at": records[-1][0]["received_at"],
                             "manifest_sha256": sha((directory/"manifest.json").read_bytes())})
        if partial:
            need(records[-1][0]["status"] == "FAILED", "partial source missing failure evidence")
            failures.append({"directory": directory.name, "provider_id": provider[0],
                             "method": records[-1][1]["method"], "sequence": records[-1][0]["sequence"],
                             "failure": records[-1][0]["failure"], "received_at": records[-1][0]["received_at"]})
        if report["mode"] == "receipts":
            found = {}
            for entry, request, raw in records:
                need(request["method"] == "eth_getTransactionReceipt" and len(request["params"]) == 1, "unexpected receipt request")
                if entry["status"] == "FAILED":
                    continue
                tid = request["params"][0]
                need(tid in events and tid not in found, "duplicate/extra receipt")
                observed = receipt_normalized(tid, events[tid], raw)
                need(observed == rows[tid], "raw receipt differs from original checkpoint")
                found[tid] = observed
            need((set(found) == set(tids) or partial) and provider[0] not in receipt_sources, "incomplete/duplicate operator receipts")
            need(list(found) == tids[:len(found)] and len(found) == report["verified_transaction_count"], "receipt checkpoint ordering/count mismatch")
            need((directory/"verified-receipts.jsonl").read_bytes() == b"".join(canonical(found[t]) for t in sorted(found)), "derived receipt file differs")
            receipt_sources[provider[0]] = found
        else:
            cursor = iter(records)
            def replay(url, method, params):
                row, req, result = next(cursor)
                need(row["url"] == url and req["method"] == method and req["params"] == params, "RPC replay request differs")
                if row["status"] == "FAILED":
                    raise ValueError("Recorded acquisition failure: " + row["failure"])
                return result
            discovered, observed, _, _ = gather(provider, call=replay, chunk=1024 if provider[0] == "blockpi" else 8192,
                                                call_budget=1200, min_rpc_interval=0)
            need(next(cursor, None) is None and discovered["coverage_complete"] is (not partial), "window replay coverage differs")
            raw_logs = [entry for row, req, result in records if req["method"] == "eth_getLogs"
                        and row["status"] == "RESPONSE_CAPTURED" for entry in result]
            if partial:
                shards = discovered["partial_shard_coverage"]
                position = 25880316
                for shard in shards:
                    need(shard["start"] == position, "partial scan has gap/overlap")
                    position = shard["end"] + 1
                partial_logs.append({"provider_id": provider[0], "completed_start_block": 25880316,
                                     "completed_end_block": position-1, "completed_blocks": position-25880316,
                                     "missing_blocks": 26095351-position+1, "events": len(raw_logs),
                                     "full_window_complete": False})
                decoded = sorted([decode(x) for x in raw_logs], key=lambda x:(x["block_number"],x["transaction_index"],x["log_index"]))
                old_rows = [parse(line) for line in contents["winner-legs-original.zip"]["decoded-liquidation-legs.jsonl"].splitlines()]
                original = {(r["transaction_hash"],r["log_index"]):r for r in old_rows}
                need(len({(r["transaction_hash"],r["log_index"]) for r in decoded}) == len(decoded)
                     and all(original.get((r["transaction_hash"],r["log_index"])) == r for r in decoded), "partial raw ABI leg mismatch")
            else:
                need(observed == expected and provider[0] not in log_sources, "full-window events mismatch")
                log_sources.append(provider[0])
                source, _ = authentic_source(event_zip)
                decoded = bind_logs(source, b"".join(canonical(x) for x in raw_logs))
            data = b"".join(canonical(x) for x in decoded)
            if not partial:
                need(data == contents["winner-legs-original.zip"]["decoded-liquidation-legs.jsonl"], "raw ABI leg reproduction differs")
            derived_legs.append({"provider_id": provider[0], "rows": len(decoded), "sha256": sha(data), "full_window": not partial})
    shared = set.intersection(*(set(r) for r in receipt_sources.values())) if receipt_sources else set()
    return {"schema": "nqc-winner-evidence-reconciliation-v1",
            "status": "ARCHIVES_VERIFIED_NEW_RPC_PARTIAL" if failures else "HISTORICAL_MARKET_EVIDENCE_RECONCILED",
            "scope": {"chain_id": 1, "protocol": "Aave V3 Ethereum", "start_block": 25880316, "end_block": 26095351,
                      "events": 139, "transactions": 127}, "archives": recovered, "new_acquisitions": acquisitions,
            "new_receipt_operator_ids": sorted(receipt_sources), "new_full_window_log_operator_ids": log_sources,
            "decoded_legs_exact_parity": derived_legs, "competitor_gas_paid_wei": str(sum(int(r["total_gas_paid_wei"]) for r in rows.values())),
            "new_receipt_counts": {p: len(r) for p,r in receipt_sources.items()},
            "two_operator_matching_receipt_count": len(shared) if len(receipt_sources) >= 2 else 0,
            "new_two_operator_receipt_consistency": len(receipt_sources) >= 2 and len(shared) == 127,
            "partial_log_coverage": partial_logs, "acquisition_failures": failures,
            "archived_blockscout_and_new_distinct_operator_log_consistency": any(p != "blockscout" for p in log_sources),
            "independent_underlying_execution_nodes_proven": False,
            "original_decision_time_observation_proven": False, "censored_opportunities_recovered": False,
            "failed_transaction_universe_complete": False, "all_execution_costs_proven": False,
            "nexus_capture_proven": False, "nexus_net_pnl_proven": False, "real_market_census_closed": False,
            "verifier_sha256": sha(Path(__file__).read_bytes())}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive-root", "metadata", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--rpc-dir", action="append", type=Path, default=[])
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    report = verify(args.archive_root, args.metadata, args.rpc_dir, args.allow_partial)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(report["status"])
