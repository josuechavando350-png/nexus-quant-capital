"""Verify that reversing every case reproduces all decisions, then hash predictions."""
from hashlib import sha256
import json
from pathlib import Path
import sys


def seal(folder):
    raw = (folder / "predictions.json").read_bytes()
    original = json.loads(raw)
    reverse = json.loads((folder / "predictions-reverse.json").read_bytes())
    if not original or original != {case: records[::-1] for case, records in reverse.items()}:
        raise ValueError("Predictions differed after reversing the input order")
    return {"observations_sha256": sha256((folder / "observations.json").read_bytes()).hexdigest(),
            "predictions_sha256": sha256(raw).hexdigest(),
            "reverse_predictions_sha256": sha256((folder / "predictions-reverse.json").read_bytes()).hexdigest()}


if __name__ == "__main__":
    print(json.dumps(seal(Path(sys.argv[1])), indent=2, sort_keys=True))
