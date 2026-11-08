"""Read one local UTF-8 log and write a private redacted derivative."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .privacy import text_export, PrivateArgumentParser
from .safe_io import read_artifact, strict_json, write_new_bundle


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description="Redact a local log for human review, without modifying the original")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        files = text_export(read_artifact(args.input.parent, args.input.name))
        write_new_bundle(args.out, files)
        receipt = strict_json(files["redaction.json"])
        print(json.dumps({"status": receipt["status"], "redactions_present": receipt["redactions_present"],
                          "manual_review_required": True, "all_secrets_detected": False}))
        return 0
    except (OSError, ValueError, TypeError, RecursionError):
        # Never echo input, filenames, exception messages or potential credentials.
        print(json.dumps({"status": "REDACTION_REJECTED", "error_code": "INVALID_LOCAL_LOG_OR_OUTPUT"}))
        return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
