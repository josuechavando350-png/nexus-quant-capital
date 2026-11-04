"""Offline evidence bridge and fixed native lab; no RPC or automatic disclosure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .bridge import ContractError, evaluate, load_json, render_report
from .integration import export_diablo, import_nqc
from .safe_io import canonical, read_artifact, write_new_bundle


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("review-platform", "verify-platform"):
        from .platform import main as platform_main
        return platform_main(argv)
    if argv and argv[0] in ("check", "verify-check", "capabilities"):
        from .quality import main as quality_main
        return quality_main(argv)
    if argv and argv[0] in ("fuzz-lab", "verify-fuzz"):
        from .fuzz_cli import main as fuzz_main
        return fuzz_main(argv[1:], verify=argv[0] == "verify-fuzz")
    if argv and argv[0] in ("local-lab", "verify-lab"):
        from .lab_cli import main as lab_main
        return lab_main(argv[1:], verify=argv[0] == "verify-lab")
    mode = argv.pop(0) if argv and argv[0] in ("export-diablo", "import-nqc") else "legacy"
    parser = argparse.ArgumentParser(description="Offline SUPERHUNTER evidence adapters")
    if mode == "export-diablo":
        parser.add_argument("finding", type=Path)
        parser.add_argument("context", type=Path)
        parser.add_argument("forge_output", type=Path)
    elif mode == "import-nqc":
        parser.add_argument("request", type=Path)
        parser.add_argument("response", type=Path)
        parser.add_argument("admission", type=Path)
    else:
        parser.add_argument("candidate", type=Path)
        parser.add_argument("reconstruction", type=Path)
        parser.add_argument("admission", type=Path)
    if mode != "export-diablo":
        parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="NEW private output directory; never overwritten")
    args = parser.parse_args(argv)
    try:
        if mode == "export-diablo":
            request = export_diablo(load_json(args.finding), load_json(args.context),
                                   read_artifact(args.forge_output.parent, args.forge_output.name))
            write_new_bundle(args.out, {"candidate.json": canonical(request["candidate"]),
                                       "request.json": canonical(request)})
            print(json.dumps({"status": "EXPORTED_UNVERIFIED", "candidate_id": request["candidate"]["id"]}))
            return 0
        report_path = str(args.out / "review.md")
        if mode == "import-nqc":
            result = import_nqc(load_json(args.request), load_json(args.response), load_json(args.admission),
                                evidence_root=args.evidence_root, report_path=report_path)
        else:
            result = evaluate(load_json(args.candidate), load_json(args.reconstruction), load_json(args.admission),
                              evidence_root=args.evidence_root, report_path=report_path)
        files = {"decision.json": canonical(result)}
        if "diablo_feedback" in result:
            files["diablo-feedback.json"] = canonical(result["diablo_feedback"])
        if result["status"] == "REVIEW_REQUIRED":
            files["review.md"] = render_report(result["draft"]).encode()
        write_new_bundle(args.out, files)
        print(json.dumps({"status": result["status"], "execution_verified": False}))
        return 0 if result["status"] == "REVIEW_REQUIRED" else 1
    except (ContractError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        # No raw evidence, amounts, reports or keys printed to shared console logs.
        print(json.dumps({"status": "REJECTED", "error_type": type(exc).__name__, "reason": str(exc)[:300]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
