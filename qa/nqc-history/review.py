"""Inspect one anonymous checkout with the pinned product's existing checks."""
import json
from pathlib import Path
import subprocess
import sys


def get_manifest(checkout):
    # Load only the first-party QA definitions of these pinned historical trees.
    script = """
import json
import sys
sys.path.insert(0, sys.argv[1])
from superhunter import quality
try:
    paths = list(quality.source_snapshot())
except ValueError as exc:
    if str(exc) != "source inventory limit exceeded":
        raise
    print(json.dumps([quality.COMPONENTS, None, str(exc)]))
else:
    print(json.dumps([quality.COMPONENTS, paths, None]))
"""
    raw = subprocess.check_output(
        [sys.executable, "-I", "-B", "-c", script, str(checkout)], cwd=checkout, timeout=120
    )
    return json.loads(raw)


def review(product, checkout):
    sys.path.insert(0, str(product))
    from superhunter import quality, repository_boundary

    components, paths, capture_error = get_manifest(checkout)
    package = checkout / "superhunter"
    if paths is None:
        paths = [p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()]
    findings = quality.validate_components(dict.fromkeys(sorted(paths)), components)
    try:
        boundary = repository_boundary.review(checkout)
    except repository_boundary.BoundaryError as exc:
        boundary = {"status": "REPOSITORY_BOUNDARY_BLOCKED", "reason": str(exc)}
    return {
        "boundary": boundary,
        "inventory": {
            "capture_error": capture_error,
            "method": "tracked_paths" if capture_error else "historical_source_snapshot",
            "path_count": len(paths),
            "findings": findings,
        },
    }


if __name__ == "__main__":
    print(json.dumps(review(Path(sys.argv[1]), Path.cwd()), sort_keys=True))
