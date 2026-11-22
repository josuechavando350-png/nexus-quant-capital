"""Measure Hunter and worksheet presentation checks on NQC's fixed paper ledger."""
import argparse
from collections import Counter
import json
from pathlib import Path

from observe import HERE, collect, sha
from study import MISMATCH, checked_reconciler, independent_report, predict, save


def input_matrix():
    vectors = []
    for scale in (1, 10, 1000, 1_000_000):
        for pattern in range(4):
            for i in range(8):
                first = (scale + i) if pattern & 1 else 0
                second = (scale * 2 + i) if pattern & 2 else 0
                left = first + 2 * second + scale + i
                right = scale * 3 + i
                vectors.append([left, right, first, second])
    if len({tuple(v) for v in vectors}) != len(vectors):
        raise ValueError("Repeated matrix input")
    return vectors


def presentation_errors(vector, observed):
    # The count describes nonempty journal rows. The printed subtotal describes
    # the two balances actually printed alongside it.
    errors = []
    if observed["rows"] != sum(amount > 0 for amount in vector[2:]):
        errors.append("rows")
    if observed["total"] != observed["left"] + observed["right"]:
        errors.append("total")
    return errors


def score_mode(pairs, vectors, records, check_fields):
    score = Counter(dict(alerts_on_wrong_outputs=0, wrong_outputs_missed=0,
                         alerts_on_correct_outputs=0, pairs_detected_with_clean_correction=0))
    missed = []
    for pair in pairs:
        pair_hits = corrected_alerts = 0
        for side in ("changed", "corrected"):
            wrong_count = 0
            for vector, entry in zip(vectors, records[pair[side]], strict=True):
                wrong = entry["observed"] != independent_report(vector)
                alert = entry["balance_alert"] or (check_fields and bool(entry["presentation_errors"]))
                wrong_count += wrong
                if wrong:
                    score["alerts_on_wrong_outputs" if alert else "wrong_outputs_missed"] += 1
                elif alert:
                    score["alerts_on_correct_outputs"] += 1
                if side == "changed" and wrong and alert:
                    pair_hits += 1
                if side == "corrected" and alert:
                    corrected_alerts += 1
            if bool(wrong_count) != (side == "changed"):
                raise ValueError("Worksheet label disagrees with independent report")
        score["pairs_detected_with_clean_correction"] += bool(pair_hits) and not corrected_alerts
        if not pair_hits:
            missed.append(pair["case"])
    return {**score, "pairs_without_detection": missed}


def run(product, tools, out):
    commit, reconcile_internal_units = checked_reconciler(product, tools)
    out.mkdir(exist_ok=False, parents=True)
    vectors = input_matrix()
    save(out / "inputs.json", vectors)
    records = {}
    for start in range(0, len(vectors), 8):
        group = vectors[start:start + 8]
        rows = collect(tools, group)
        base = predict(reconcile_internal_units, rows, group)
        for name, observations in rows.items():
            entries = records.setdefault(name, [])
            for v, row, balance in zip(group, observations, base[name], strict=True):
                entries.append({"observed": row, "balance_alert": balance["status"] == MISMATCH,
                                "presentation_errors": presentation_errors(v, row)})
    save(out / "predictions.json", records)

    # Load labels and independent four-field expectations only after saving predictions.
    records = json.loads((out / "predictions.json").read_bytes())
    pairs = json.loads((HERE / "cases.json").read_bytes())
    ids = [p[k] for p in pairs for k in ("changed", "corrected")]
    if set(ids) != set(records) or len(ids) != len(records):
        raise ValueError("Incomplete worksheet matrix")
    baseline = score_mode(pairs, vectors, records, check_fields=False)
    extended = score_mode(pairs, vectors, records, check_fields=True)
    result = {"product_commit": commit, "inputs": len(vectors), "worksheets": len(records),
              "worksheet_outputs": len(vectors) * len(records),
              "wrong_outputs": baseline["alerts_on_wrong_outputs"] + baseline["wrong_outputs_missed"],
              "worksheets_sha256": sha((HERE / "Sheets.sol").read_bytes()),
              "balance_only": baseline, "balance_and_presentation": extended}
    save(out / "score-fields.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("product", "tools", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    run(args.product.resolve(), args.tools.resolve(), args.output.resolve())
