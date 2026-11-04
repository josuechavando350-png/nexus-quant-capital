"""Run: python -m superhunter candidate.json reconstruction.json admission.json --evidence-root ... --out ..."""

import argparse
import json
from pathlib import Path

from .bridge import ContractError, evaluate, load_json, render_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline SUPERHUNTER candidate/reconstruction gate")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("reconstruction", type=Path)
    parser.add_argument("admission", type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="directory for report.md and decision.json")
    args = parser.parse_args()
    report_path = str(args.out / "report.md")
    try:
        decision = evaluate(load_json(args.candidate), load_json(args.reconstruction),
                            load_json(args.admission), evidence_root=args.evidence_root,
                            report_path=report_path)
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"status": "REJECTED", "reasons": [str(exc)]}, indent=2))
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    if decision["status"] == "REPORT_READY":
        (args.out / "report.md").write_text(render_report(decision["finding"]), encoding="utf-8")
    (args.out / "decision.json").write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2))
    return 0 if decision["status"] == "REPORT_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
