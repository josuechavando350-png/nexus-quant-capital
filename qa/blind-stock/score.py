"""Compare the sealed predictions with the full warehouse specification."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from seal import seal

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def expected(batch):
    lines = []
    reserve, display = batch["opening"]
    nonempty = 0
    for (quantity, units, void), receipt in zip(batch["slips"], batch["receipt"], strict=True):
        delivered = 0 if void else quantity * units
        if delivered != receipt:
            raise ValueError("Receipt and independent order specification disagree")
        reserve -= delivered
        display += delivered
        nonempty += int(delivered != 0)
        lines.append(delivered)
    if reserve < 0:
        raise ValueError("Invalid source stock")
    return lines, {"left": reserve, "right": display, "rows": nonempty, "total": sum(batch["opening"])}


def tally(judged, channel, mode):
    totals = Counter(dict(true_positive_cases=0, false_negative_cases=0, true_negative_cases=0,
                          false_positive_cases=0, alerts_on_wrong_outputs=0, alerts_on_correct_outputs=0))
    missed = []
    for label, defective, wrong, verdicts in judged:
        alerts = {i for i, entry in enumerate(verdicts) if entry[channel][mode]}
        hits = alerts & wrong
        totals["alerts_on_wrong_outputs"] += len(hits)
        totals["alerts_on_correct_outputs"] += len(alerts - wrong)
        if defective:
            if hits:
                totals["true_positive_cases"] += 1
            else:
                totals["false_negative_cases"] += 1
                missed.append(label)
        elif alerts:
            totals["false_positive_cases"] += 1
        else:
            totals["true_negative_cases"] += 1
    return {**totals, "missed": sorted(missed)}


def score(folder):
    if seal(folder) != read(ROOT / "prediction-seal.json"):
        raise ValueError("Disclosed predictions differ from the pre-scoring commitment")
    for path, digest in read(ROOT / "commitments.json").items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError("Source differs from pre-classification commitment")
    verdicts = read(folder / "predictions.json")
    obs = read(folder / "observations.json")
    key = read(ROOT / "vault/key.json")
    batches = read(ROOT / "vault/receipts.json")
    if len(key) != 12 or sum(v["defective"] for v in key.values()) != 8 or set(key) != set(obs) or set(key) != set(verdicts):
        raise ValueError("Bad assignment or missing cases")
    if len({v["variant"] for v in key.values()}) != len(key):
        raise ValueError("Repeated variant")
    judged = []
    for case, entry in key.items():
        wrong = set()
        for i, (batch, sample, _) in enumerate(zip(batches, obs[case], verdicts[case], strict=True)):
            book, report = expected(batch)
            if sample["receipt"] != batch["receipt"] or sample["opening"] != batch["opening"]:
                raise ValueError("Observations differ from issued receipts")
            if sample["book"] != book or sample["report"] != report:
                wrong.add(i)
        if bool(wrong) != entry["defective"]:
            raise ValueError("Independent evaluation contradicts case key or defect not exercised")
        judged.append((entry["variant"], entry["defective"], wrong, verdicts[case]))
    return {"implementations": len(key), "defective": 8, "healthy": 4, "batches_per_case": len(batches),
            "outputs": len(key) * len(batches), "wrong_outputs": sum(len(wrong) for _, _, wrong, _ in judged),
            "primary": "receipt.with_fields", "modes": {channel: {
                mode: tally(judged, channel, mode) for mode in ("balance", "with_fields")}
                for channel in ("book", "receipt")}}


if __name__ == "__main__":
    print(json.dumps(score(Path(sys.argv[1])), indent=2, sort_keys=True))
