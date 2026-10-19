"""Separate allocation probe; never mixed into timing windows or used to trim."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import tracemalloc
from benchmark import ROOT, R3, policy_from, r4_verify, r5_verify, sha


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args(); assert not a.out.exists()
    index = json.loads((R3 / "fixtures/synthetic-index.json").read_text())
    cases = [((R3 / "fixtures" / r["packet"]).read_bytes(), policy_from(r["policy"])) for r in index]
    rows = []
    for rep in range(3):
        for i, (raw, policy) in enumerate(cases):
            order = (("r4", r4_verify), ("r5", r5_verify))
            if (rep + i) % 2: order = tuple(reversed(order))
            for variant, verify in order:
                gc.collect(); tracemalloc.start()
                facts = verify(raw, policy, policy.anchor.timestamp)
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                rows.append({"rep": rep, "case": i, "variant": variant,
                             "current_bytes_with_returned_facts": current, "peak_python_bytes": peak,
                             "facts_sha256": hashlib.sha256(repr(facts).encode()).hexdigest()})
                del facts
    for rep in range(3):
        for i in range(16):
            selected = [r for r in rows if r["rep"] == rep and r["case"] == i]
            assert selected[0]["facts_sha256"] == selected[1]["facts_sha256"]
    a.out.write_text(json.dumps({
        "scope": "TRACEMALLOC_PYTHON_ALLOCATION_ONLY_NOT_RSS_OR_NATIVE_OR_LATENCY",
        "method": "96 independent calls, GC collected before tracing, no subtraction",
        "source_sha256": {str(f.relative_to(ROOT)): sha(f) for f in
                           (Path(__file__), ROOT / "python/proof_traversal.py", ROOT / "python/state_evidence_fast.py")},
        "rows": rows}, indent=2) + "\n")


if __name__ == "__main__": main()
