"""Benchmark a pinned Hunter, with native Solidity observations and separate scoring."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from observe import collect, HERE, sha

PRODUCT = "066cf0876cc921b89c8a2f2229b39e9e1a2b3366"
MATCH = "UNIT_BALANCES_RECONCILED"
MISMATCH = "UNIT_BALANCES_MISMATCH"
UNKNOWN = "UNIT_BALANCES_INCONCLUSIVE"


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write("\n")


def predict(reconcile, observed, vectors):
    predictions = {}
    for name, rows in observed.items():
        entries = []
        for vector, row in zip(vectors, rows, strict=True):
            left, right, a, b = vector
            opening = {"left": str(left), "right": str(right)}
            closing = {field: str(row[field]) for field in opening}
            transfers = [{"id": f"row-{i}", "from": "left", "to": "right", "amount_units": str(amount)}
                         for i, amount in enumerate((a, b)) if amount]
            result = reconcile(opening, closing, transfers)
            incomplete = reconcile(opening, closing, transfers, coverage="declared_incomplete")
            if result["status"] not in (MATCH, MISMATCH) or incomplete["status"] != UNKNOWN:
                raise ValueError("unexpected reconciliation or incomplete-journal status")
            entries.append({"status": result["status"], "residuals": result["rows"],
                            "input_sha256": result["input_sha256"], "if_incomplete": incomplete["status"]})
        predictions[name] = entries
    return predictions


def independent_report(vector):
    left, right, first, second = vector
    # Model each nonempty journal row in order. The printed subtotal belongs
    # to both columns combined; the row count excludes empty entries.
    count = 0
    total = left + right
    for quantity in (first, second):
        if quantity:
            left -= quantity
            right += quantity
            count += 1
    return {"left": left, "right": right, "rows": count, "total": total}


def score(directory, vectors):
    observed = json.loads((directory / "observations.json").read_bytes())
    frozen = json.loads((directory / "predictions.json").read_bytes())
    pairs = json.loads((HERE / "cases.json").read_bytes())
    ids = [pair[k] for pair in pairs for k in ("changed", "corrected")]
    if len(set(ids)) != len(ids) or set(ids) != set(observed) or set(ids) != set(frozen):
        raise ValueError("the answer key does not cover exactly the anonymous worksheets")
    results = []
    erroneous_vectors = detected_vectors = false_vector_alerts = 0
    for pair in pairs:
        evidence = {}
        for side in ("changed", "corrected"):
            name = pair[side]
            differences, alerts = [], []
            for i, vector in enumerate(vectors):
                expected = independent_report(vector)
                fields = [f for f in expected if observed[name][i][f] != expected[f]]
                if fields:
                    differences.append({"vector": i, "fields": fields})
                if frozen[name][i]["status"] == MISMATCH:
                    alerts.append(i)
            if bool(differences) != (side == "changed"):
                raise ValueError("published pair disagrees with the independent full-report oracle")
            wrong = {d["vector"] for d in differences}
            erroneous_vectors += len(wrong)
            detected_vectors += len(wrong.intersection(alerts))
            false_vector_alerts += len(set(alerts) - wrong)
            evidence[side] = {"worksheet": name, "changed_outputs": differences, "alerts": alerts}
        results.append({"case": pair["case"], **evidence})
    return {"pairs": len(pairs), "vectors": len(vectors), "worksheets": len(ids),
            "changed_with_alert": sum(bool(r["changed"]["alerts"]) for r in results),
            "changed_without_alert": sum(not r["changed"]["alerts"] for r in results),
            "corrected_with_alert": sum(bool(r["corrected"]["alerts"]) for r in results),
            "corrected_without_alert": sum(not r["corrected"]["alerts"] for r in results),
            "joint_pair_success": sum(any(d["vector"] in r["changed"]["alerts"] for d in r["changed"]["changed_outputs"])
                                      and not r["corrected"]["alerts"] for r in results),
            "erroneous_vectors": erroneous_vectors, "detected_vectors": detected_vectors,
            "false_vector_alerts": false_vector_alerts,
            "incomplete_abstentions": sum(p["if_incomplete"] == UNKNOWN for v in frozen.values() for p in v),
            "results": results}


def checked_reconciler(product, tools):
    commit = subprocess.check_output(["git", "-C", str(product), "rev-parse", "HEAD"]).decode().strip()
    if commit != PRODUCT or subprocess.check_output(["git", "-C", str(product), "status", "--porcelain"]):
        raise ValueError("a clean checkout of the pinned Hunter product is required")
    pins = json.loads((product / "superhunter/product_supply/contract-properties-native-build.json").read_bytes())
    for item in [*pins["direct_downloads"], *pins["archives"]]:
        if sha((tools / item["kit_file"]).read_bytes()) != item["sha256"]:
            raise ValueError("native tool differs from the product's pin")
    sys.path.insert(0, str(product))
    from superhunter.balance_reconciliation import reconcile_internal_units
    return commit, reconcile_internal_units


def run(product, tools, out):
    commit, reconcile_internal_units = checked_reconciler(product, tools)
    vectors = json.loads((HERE / "vectors.json").read_bytes())
    if any(len(v) != 4 or any(type(q) is not int or q < 0 for q in v) or v[2]+v[3]*2 > v[0] for v in vectors):
        raise ValueError("invalid benchmark vector")
    out.mkdir(parents=True, exist_ok=False)
    first = collect(tools, vectors)
    save(out / "observations.json", first)
    predictions = predict(reconcile_internal_units, first, vectors)
    save(out / "predictions.json", predictions)
    replay = collect(tools, vectors, reverse=True)
    if replay != first or predict(reconcile_internal_units, replay, vectors) != predictions:
        raise ValueError("independent process with reversed vectors gave a different report")
    summary = score(out, vectors)
    summary.update(product_commit=commit, source_sha256=sha((HERE / "Sheets.sol").read_bytes()),
                   reverse_order_replay=True)
    save(out / "score.json", summary)
    print(json.dumps({k:v for k,v in summary.items() if k != "results"}, sort_keys=True))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("product", "tools", "output"):
        p.add_argument(arg, type=Path)
    args = p.parse_args()
    run(args.product.resolve(), args.tools.resolve(), args.output.resolve())
