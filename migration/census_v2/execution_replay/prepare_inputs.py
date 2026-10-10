#!/usr/bin/env python3
"""Bind fresh fork inputs to immutable source and authenticated winner event."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import zipfile
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parents[1]
sys.path.insert(0, str(ROOT / "ci/nqc-census"))
from rmc016_aave_event_legs import decode


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    sources = V2 / "evidence/physical-logs/sources"
    items = {
        "src/NqcFlashFundingExecutor.sol": sources / "37741109591-NqcFlashFundingExecutor.sol.txt",
        "test/NqcRmc016RankOneSelfFinancingFork.t.sol": sources / "37742063251-NqcRmc016RankOneSelfFinancingFork.t.sol.txt",
        "foundry.toml": ROOT / "ci/nqc-census/weth-physical/foundry-time-only.toml",
    }
    origins = json.loads((V2 / "evidence/physical-logs/source-origins.json").read_bytes())
    manifest = {"schema": "nqc-rank1-reproduction-inputs-v1", "source_repository": "josuechavando350-png/nexus-engine",
                "source_catalog_sha256": hashlib.sha256((V2 / "evidence/physical-logs/source-origins.json").read_bytes()).hexdigest(),
                "files": {}}
    for name, path in items.items():
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        origin = next((x for x in origins if x["file"] == path.name), None)
        if origin and digest != origin["sha256"]:
            raise ValueError("source differs from pinned historical source")
        dst = root / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
        manifest["files"][name] = {"sha256": digest, "source_path": str(path.relative_to(ROOT)),
                                    "historical_origin": origin,
                                    "unchanged_import_commit_if_no_origin": None if origin else "e259739c9f75fedcd1061d2f78d6b8852e7a3060"}
    tx = "0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba"
    receipts = V2 / "additional_evidence/recovered-rmc016/tenderly-receipts-20261009.jsonl.gz"
    matches = []
    for line in gzip.decompress(receipts.read_bytes()).splitlines():
        row = json.loads(line)
        if row["method"] == "eth_getTransactionReceipt" and row["params"] == [tx]:
            matches.append((line, row))
    if len(matches) != 1:
        raise ValueError("selected receipt missing or duplicated")
    line, row = matches[0]
    logs = [log for log in row["result"]["logs"] if int(log["logIndex"], 16) == 21]
    if len(logs) != 1:
        raise ValueError("selected liquidation missing or duplicated")
    log = logs[0]
    manifest.update(borrower="0x" + log["topics"][3][-40:], source_liquidation_log=log,
                    receipt_archive_sha256=hashlib.sha256(receipts.read_bytes()).hexdigest(),
                    selected_receipt_exchange_sha256=hashlib.sha256(line).hexdigest())
    with zipfile.ZipFile(V2 / "economic_archives/inputs/11525823668.zip") as archive:
        original = [json.loads(line) for line in archive.read("decoded-liquidation-legs.jsonl").splitlines()
                    if json.loads(line)["transaction_hash"] == tx]
    if len(original) != 1 or decode(log) != original[0]:
        raise ValueError("new input does not match authenticated original liquidation")
    manifest["original_decoded_event"] = original[0]
    (root / "sources.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.out)
    print(json.dumps({"files": len(result["files"]), "original_event_exact_match": True}))
