"""Verify pinned NQC ancestry, bounded defense changes and immutable source bytes."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys

from .codec import Rejected, decode
from .files import read_local

BASE_COMMIT = "16e352225ba8a6a931834c4edf3d86d9a2924b7d"
VERIFIER_GIT_BLOB = "3bb842872a4ca89e81bcf45839b42cc88d26f84e"


def verify_nqc(root):
    root = Path(root).absolute()
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10, check=True, env=env).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise Rejected("nqc_git_unavailable") from exc
    if commit != BASE_COMMIT:
        try:
            subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", BASE_COMMIT, commit],
                           capture_output=True, timeout=10, check=True, env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            raise Rejected("nqc_base_changed_requires_review") from exc
    try:
        changes = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "-z", BASE_COMMIT, "--"],
                                 capture_output=True, timeout=10, check=True, env=env).stdout.decode("utf-8").split("\x00")
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise Rejected("nqc_changes_unavailable") from exc
    if any(path and not (path.startswith("migration/defense/") or path == "migration/DEFENSE-INTEGRATION.md")
           for path in changes):
        raise Rejected("nqc_unreviewed_change")
    data = read_local(root, "migration/verify_isolation.py", 65536)
    blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\x00" + data).hexdigest()
    if blob != VERIFIER_GIT_BLOB:
        raise Rejected("nqc_verifier_changed")
    # The pinned verifier only reads source bytes; it does not run workflows or publish.
    try:
        result = subprocess.run([sys.executable, "-B", str(root / "migration/verify_isolation.py"),
                                 "--root", str(root)], capture_output=True, timeout=60, check=True, env=env)
        evidence = decode(result.stdout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Rejected("nqc_isolation_not_verified") from exc
    if (evidence.get("status") != "ISOLATED_SOURCE_IDENTITY_PASS" or evidence.get("active_workflows") != 0
            or evidence.get("canonical_recertification") is not False):
        raise Rejected("nqc_isolation_result")
    return {"base_commit": BASE_COMMIT, "head_commit": commit, "isolation": evidence}
