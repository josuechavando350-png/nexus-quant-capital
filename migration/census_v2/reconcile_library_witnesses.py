#!/usr/bin/env python3
"""Read recovered Library bytes offline; supplement, never expand, the winner set.

Archive integrity and agreement are checked here. Archived transport metadata
is a retained observation, not independent authentication of the provider or
decision-time information. No imported producer is executed by this consumer.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import re
import zipfile

import reconcile_winner_economics as base
from verify_winner_recovery import canonical, need, parse, sha

PACKAGE = "nqc-observed-economic-ledger-20261009/"
PIN = "f74cca61dd4984cc41fdc144926dcdd7d0260e1e6f534374006c36cc2861118d"
LIBRARY_ID = "libfile_e713c4e555548191a7a79acbb2db202d"
ARCHIVED_AT = "2026-10-09T03:23:57.575791+00:00"
ENDPOINTS = {"nodies": "https://eth-pokt.nodies.app/",
             "tenderly": "https://mainnet.gateway.tenderly.co"}
METHODS = {"eth_getBlockByNumber", "eth_getTransactionByHash", "eth_getTransactionReceipt"}


def equal(a, b):
    return canonical(a) == canonical(b)  # bools must not equal integer fields


def instant(value):
    need(type(value) is str, "timestamp is not text")
    result = datetime.fromisoformat(value)
    need(result.tzinfo is not None, "timestamp lacks timezone")
    return result


def package(path):
    need(path.is_file() and path.stat().st_size == 262911, "Library archive pin mismatch")
    raw = path.read_bytes()
    need(len(raw) == 262911 and sha(raw) == PIN, "Library archive pin mismatch")
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        need(len(infos) == 92 and len({i.filename for i in infos}) == 92,
             "package member inventory mismatch")
        for i in infos:
            p = PurePosixPath(i.filename)
            need(i.filename.startswith(PACKAGE) and not p.is_absolute()
                 and all(x not in ("", ".", "..") for x in i.filename.split("/"))
                 and "\\" not in i.filename and not i.is_dir()
                 and i.file_size <= 400000 and not i.flag_bits & 1
                 and (i.external_attr >> 16) & 0o170000 in (0, 0o100000),
                 "unsafe package member")
        data = {i.filename[len(PACKAGE):]: z.read(i) for i in infos}
    manifest = parse(data["PACKAGE-MANIFEST.json"])
    need(set(manifest["files"]) == set(data) - {"PACKAGE-MANIFEST.json"},
         "package manifest is not exhaustive")
    for name, digest in manifest["files"].items():
        need(sha(data[name]) == digest, "package member hash mismatch")
    for name, content in data.items():
        if name.startswith("output/raw-evidence/"):
            need(PurePosixPath(name).stem == sha(content), "content address mismatch")
    return data


def source(data, row):
    def read(kind, digest_key):
        key = "packaged_" + kind + "_path"
        path = row[key]
        need(re.fullmatch(r"raw-evidence/[0-9a-f]{64}\.json", path) is not None,
             "unsafe source reference")
        raw = data["output/" + path]
        need(sha(raw) == row[digest_key], "source witness hash mismatch")
        return raw, parse(raw)

    raw_bytes, envelope = read("raw", "raw_sha256")
    request_bytes, request = read("request", "request_sha256") if "request_sha256" in row else (
        data["output/" + row["packaged_request_path"]],
        parse(data["output/" + row["packaged_request_path"]]))
    need(row["packaged_request_path"] == "raw-evidence/" + sha(request_bytes) + ".json",
         "request content address mismatch")
    _, metadata = read("metadata", "metadata_sha256")
    _, accepted = read("acceptance", "accepted_marker_sha256")
    provider = row["provider"]
    need(provider in ENDPOINTS and row["method"] in METHODS, "unknown provider or method")
    request_id = request.get("id")
    need(type(request_id) is str and re.fullmatch(r"[0-9a-f]{64}", request_id)
         and row["source_id"] == provider + ":" + request_id
         and request.get("jsonrpc") == "2.0" and request["method"] == row["method"]
         and equal(request["params"], row["params"]), "request/source mismatch")
    need(type(envelope) is dict and envelope.get("jsonrpc") == "2.0"
         and envelope.get("id") == request_id and "error" not in envelope
         and type(envelope.get("result")) is dict, "RPC envelope mismatch")
    need(metadata.get("http_status") == 200 and type(metadata["http_status"]) is int
         and metadata["body_complete"] is True and metadata["truncated"] is False
         and metadata["read_error"] is None and metadata["request_id"] == request_id
         and metadata["endpoint"] == ENDPOINTS[provider]
         and metadata["response_sha256"] == row["raw_sha256"]
         and type(metadata["response_bytes"]) is int and metadata["response_bytes"] == len(raw_bytes),
         "transport witness mismatch")
    need(accepted["provider_id"] == provider and accepted["endpoint"] == ENDPOINTS[provider]
         and accepted["metadata_sha256"] == row["metadata_sha256"]
         and accepted["raw_sha256"] == row["raw_sha256"]
         and accepted["bundle_sha256"] == row["bundle_sha256"]
         and accepted["semantic_sha256"] == row["validated_semantic_sha256"],
         "archived acceptance binding mismatch")
    need(instant(metadata["started_at"]) <= instant(metadata["finished_at"])
         <= instant(accepted["accepted_at"]) <= instant(ARCHIVED_AT), "acquisition chronology mismatch")
    witness = {"source_id": row["source_id"], "provider": provider, "method": row["method"],
               "params": row["params"], "raw_sha256": row["raw_sha256"],
               "request_sha256": sha(request_bytes), "metadata_sha256": row["metadata_sha256"],
               "accepted_marker_sha256": row["accepted_marker_sha256"],
               "recorded_received_at": metadata["finished_at"],
               "recorded_accepted_at": accepted["accepted_at"],
               "historical_decision_time_observation_proven": False,
               "transport_authenticity_independently_verified": False}
    return envelope["result"], witness


def load_sources(data):
    rows = [parse(line) for line in data["output/sources.jsonl"].splitlines()]
    need(len(rows) == 18 and len({r["source_id"] for r in rows}) == 18, "source population drift")
    groups, witnesses = defaultdict(dict), []
    for row in rows:
        result, witness = source(data, row)
        key = (row["method"], canonical(row["params"]))
        need(row["provider"] not in groups[key], "duplicate source for method/parameters")
        groups[key][row["provider"]] = result
        witnesses.append(witness)
    need(len(groups) == 9 and all(set(v) == set(ENDPOINTS) for v in groups.values()),
         "incomplete paired source set")
    return groups, witnesses


def normalized_type2_receipt(raw, tx):
    # Some providers add blobGasUsed=0 alone to type-2 receipts. This is not
    # accepted for blob transactions or positive/ambiguous blob quantities.
    need(raw.get("type") == tx.get("type") == "0x2", "scope is Ethereum type-2 only")
    result = dict(raw)
    for key in ("blobGasUsed", "blobGasPrice"):
        if key in result:
            need(base.quantity(result.pop(key)) == 0, "nonzero blob fee on type-2 receipt")
    return result


def transaction_view(tx, header, receipt, expected):
    need(tx.get("type") == "0x2" and tx.get("chainId") == "0x1", "transaction type/chain mismatch")
    for key in ("hash", "blockHash", "from", "to"):
        pattern = base.HASH if key in ("hash", "blockHash") else base.ADDRESS
        need(type(tx.get(key)) is str and pattern.fullmatch(tx[key]), "transaction identity shape")
    need(tx["hash"] == expected["transaction_hash"] and tx["blockHash"] == expected["block_hash"]
         and header.get("hash") == tx["blockHash"]
         and base.quantity(tx["blockNumber"]) == base.quantity(header["number"]) == expected["block_number"]
         and base.quantity(tx["transactionIndex"]) == expected["transaction_index"]
         and tx["from"] == receipt["from"] and tx["to"] == receipt["to"], "transaction/header/receipt join mismatch")
    txs = header.get("transactions")
    need(type(txs) is list and all(type(t) is str and base.HASH.fullmatch(t) for t in txs)
         and len(txs) == len(set(txs)) and expected["transaction_index"] < len(txs)
         and txs[expected["transaction_index"]] == tx["hash"], "header transaction position mismatch")
    timestamp = base.quantity(header["timestamp"])
    if "blockTimestamp" in tx:
        need(base.quantity(tx["blockTimestamp"]) == timestamp, "provider timestamp contradicts header")
    used = base.quantity(receipt["gasUsed"])
    price = base.quantity(receipt["effectiveGasPrice"])
    base_fee = base.quantity(header["baseFeePerGas"])
    cap, tip_cap = (base.quantity(tx[k]) for k in ("maxFeePerGas", "maxPriorityFeePerGas"))
    need(base.quantity(tx["gas"]) >= used and tip_cap <= cap and cap >= base_fee
         and price == min(cap, base_fee + tip_cap) == base.quantity(tx["gasPrice"]),
         "EIP1559 fee arithmetic mismatch")
    need(type(header.get("miner")) is str and base.ADDRESS.fullmatch(header["miner"]),
         "fee recipient shape")
    need(type(tx.get("input")) is str and re.fullmatch(r"0x(?:[0-9a-f]{2})*", tx["input"]),
         "calldata shape")
    gas = used * price
    need(str(gas) == expected["total_gas_paid_wei"], "historical gas changed")
    return {"transaction_hash": tx["hash"], "block_hash": tx["blockHash"],
            "block_number": expected["block_number"], "transaction_index": expected["transaction_index"],
            "block_timestamp": timestamp, "sender": tx["from"], "top_level_target": tx["to"],
            "calldata_selector": tx["input"][:10] if len(tx["input"]) >= 10 else None,
            "top_level_value_wei": str(base.quantity(tx["value"])),
            "gas_used": str(used), "effective_gas_price_wei": str(price),
            "base_fee_burn_wei": str(used * base_fee), "priority_fee_wei": str(used * (price - base_fee)),
            "total_gas_paid_wei": str(gas), "block_fee_recipient": header["miner"],
            "gas_is_existing_ledger_breakdown_not_additional_cost": True,
            "fee_recipient_builder_identity": None, "internal_native_payments_wei": None,
            "classification": "INSUFFICIENT_EVIDENCE", "net_pnl_usd": None,
            "original_nqc_observed_at": None, "real_market_census_closed": False}


def reconcile(data, inputs):
    receipts, legs, observed, _, _, _, _ = inputs
    groups, witnesses = load_sources(data)
    ids = sorted(parse(k[1])[0] for k in groups if k[0] == "eth_getTransactionByHash")
    need(len(ids) == len(set(ids)) == 3 and set(ids) <= set(receipts), "paired cases outside winner universe")
    rows, differences, header_keys = [], [], set()
    for txid in ids:
        expected, views = receipts[txid], []
        tx_pair = groups[("eth_getTransactionByHash", canonical([txid]))]
        rec_pair = groups[("eth_getTransactionReceipt", canonical([txid]))]
        key = ("eth_getBlockByNumber", canonical([hex(expected["block_number"]), False]))
        headers = groups[key]; header_keys.add(key)
        need(equal(headers["nodies"], headers["tenderly"]), "full header provider mismatch")
        clean_txs, clean_receipts = [], []
        for provider in sorted(ENDPOINTS):
            tx, raw = tx_pair[provider], rec_pair[provider]
            clean = normalized_type2_receipt(raw, tx)
            # Compare all receipt fields and every log, not just gas/selected events.
            sem = base.semantic_receipt(clean, expected)
            need(observed.get(txid) and all(equal(sem, v) for v in observed[txid].values()),
                 "Library receipt differs from recovered BlockPI/dRPC raw evidence")
            for k, v in (("gasUsed", expected["gas_used"]), ("effectiveGasPrice", expected["effective_gas_price_wei"]),
                         ("blockNumber", str(expected["block_number"])), ("transactionIndex", str(expected["transaction_index"]))):
                need(str(base.quantity(clean[k])) == v, "receipt numerical identity drift")
            need(clean.get("transactionHash") == txid and clean.get("blockHash") == expected["block_hash"]
                 and clean.get("status") == "0x1", "receipt identity/status mismatch")
            views.append(transaction_view(tx, headers[provider], clean, expected))
            clean_txs.append({k: v for k, v in tx.items() if k != "blockTimestamp"})
            clean_receipts.append(clean)
        need(equal(clean_txs[0], clean_txs[1]) and equal(clean_receipts[0], clean_receipts[1])
             and equal(views[0], views[1]), "paired transaction or receipt semantic mismatch")
        for method, pair in (("transaction", tx_pair), ("receipt", rec_pair)):
            for field in sorted(set(pair["nodies"]) | set(pair["tenderly"])):
                if not equal(pair["nodies"].get(field), pair["tenderly"].get(field)):
                    differences.append({"transaction_hash": txid, "object": method, "field": field,
                                        "values": {p: pair[p].get(field) for p in ENDPOINTS},
                                        "treatment": "VALIDATED_HEADER_TIMESTAMP" if field == "blockTimestamp"
                                        else "EXPLICIT_ZERO_BLOB_FIELD_ON_TYPE2"})
        selected = [w for w in witnesses if w["params"] == [txid] or equal(w["params"], parse(key[1]))]
        need(len(selected) == 6, "witness association incomplete")
        need(all(instant(w["recorded_received_at"]) > datetime.fromtimestamp(views[0]["block_timestamp"], timezone.utc)
                 for w in selected), "retrospective witness chronology mismatch")
        row = views[0]
        row["source_ids"] = sorted(w["source_id"] for w in selected)
        row["receipt_matches_prior_provider_labels"] = sorted(observed[txid])
        row["liquidation_events"] = len([leg for leg in legs if leg["transaction_hash"] == txid])
        rows.append(row)
    need(header_keys == {k for k in groups if k[0] == "eth_getBlockByNumber"}, "orphan header")
    report = {"schema": "nqc-library-witness-reconciliation-v1", "scope": "THREE_EXISTING_HISTORICAL_WINNERS",
              "package_sha256": PIN, "library_file_id": LIBRARY_ID, "packaged_files_verified": len(data),
              "source_documents": len(witnesses), "paired_transactions": len(rows),
              "winner_universe_transactions": len(receipts), "new_winner_transactions": 0,
              "gas_paid_wei_in_three_existing_records": str(sum(int(r["total_gas_paid_wei"]) for r in rows)),
              "base_fee_burn_wei": str(sum(int(r["base_fee_burn_wei"]) for r in rows)),
              "priority_fee_wei": str(sum(int(r["priority_fee_wei"]) for r in rows)),
              "provider_representation_differences": differences,
              "mismatches": [], "independent_provider_infrastructure_proven": False,
              "source_producer_commit": None, "source_producer_tree": None,
              "source_identity_treatment": "LIBRARY_TRANSPORT_PIN_ONLY_NOT_GIT_PRODUCER_AUTHORITY",
              "original_acquisition_bundle_materialized": False,
              "archived_acceptance_semantic_hash_recomputed": False,
              "real_market_census_closed": False, "nqc_capture_proven": False,
              "net_pnl_usd": None, "original_decision_time_observation_proven": False,
              "non_claims": ["No original ledger builder or its archived tests rerun",
                             "No signed transaction hash, header RLP or state/inclusion proof verified",
                             "Transport records preserved; TLS/provider authenticity not independently revalidated",
                             "Original acquisition bundle and its semantic verifier are not supplied; acceptance hashes only cross-linked",
                             "Priority gas is part of existing receipt gas; never subtract it twice",
                             "msg.value is not complete native payments, builder payment or profit",
                             "No new funding permission, live acquisition or gas expenditure"]}
    files = {"paired-winner-supplement.jsonl": b"".join(canonical(r) for r in rows),
             "source-witnesses.jsonl": b"".join(canonical(w) for w in sorted(witnesses, key=lambda w: w["source_id"]))}
    report["outputs"] = {k: sha(v) for k, v in files.items()}
    return files, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("package", "archive-root", "metadata", "rpc-root", "out"):
        p.add_argument("--" + arg, type=Path, required=True)
    args = p.parse_args()
    need(not args.out.exists(), "refusing to overwrite evidence")
    files, report = reconcile(package(args.package), base.sources(args.archive_root, args.metadata, args.rpc_root))
    report["consumer_sha256"] = sha(Path(__file__).read_bytes())
    args.out.mkdir(parents=False, exist_ok=False)
    for name, raw in files.items():
        (args.out / name).write_bytes(raw)
    (args.out / "reconciliation.json").write_bytes(canonical(report))
    print(canonical(report).decode(), end="")


if __name__ == "__main__":
    main()
