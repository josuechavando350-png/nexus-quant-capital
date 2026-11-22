"""Custodian prepares observations without transferring the key to the detector."""
import hashlib
import json
from pathlib import Path
import sys
from vault.stockroom import run

ROOT = Path(__file__).resolve().parent


def check_seals():
    sealed = json.loads((ROOT / "commitments.json").read_bytes())
    for name, expected in sealed.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Committed fixture or protocol changed: " + name)


def prepare(out):
    check_seals()
    out.mkdir(parents=True, exist_ok=False)
    key = json.loads((ROOT / "vault/key.json").read_bytes())
    batches = json.loads((ROOT / "vault/receipts.json").read_bytes())
    samples = {}
    for case, entry in sorted(key.items()):
        samples[case] = [
            {"opening": batch["opening"], "receipt": batch["receipt"],
             **run(entry["variant"], batch["opening"], batch["slips"])} for batch in batches]
    for name, obj in (("observations", samples), ("reverse", {k: v[::-1] for k,v in samples.items()})):
        (out / (name + ".json")).write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
