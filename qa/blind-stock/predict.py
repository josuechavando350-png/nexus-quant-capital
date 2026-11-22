"""Emit verdicts using the frozen detectors and anonymous observations only."""
import json
import sys
from pathlib import Path

sys.path[:0] = ["/hunter", "/controls"]
from superhunter.balance_reconciliation import reconcile_internal_units
from report_fields import presentation_errors
from study import MISMATCH, predict


def verdict(opening, moves, report):
    vector = [*opening, *moves]
    result = predict(reconcile_internal_units, {"sample": [report]}, [vector])["sample"][0]
    balance = result["status"] == MISMATCH
    return {"balance": balance, "with_fields": balance or bool(presentation_errors(vector, report))}


def main():
    cases = json.loads(Path("/data.json").read_bytes())
    result = {}
    for case, records in sorted(cases.items()):
        verdicts = []
        for item in records:
            if set(item) != {"opening", "book", "receipt", "report"}:
                raise ValueError("Unexpected observation fields")
            verdicts.append({channel: verdict(item["opening"], item[channel], item["report"])
                             for channel in ("book", "receipt")})
        result[case] = verdicts
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
