"""M26: bounded local canary creation and content-change checks, not read detection."""

import secrets

from .codec import Rejected
from .files import create_local, read_local, sha256


def seed(root, relative_path):
    data = b"NQC DEFENSIVE CANARY\n" + secrets.token_hex(32).encode() + b"\n"
    create_local(root, relative_path, data)
    return {"path": relative_path, "sha256": sha256(data)}


def observe(root, asset, clock):
    """Capture hashes and errors from actual local reads, never from request fields."""
    observations, _ = observe_snapshot(root, asset, clock)
    return observations


def observe_snapshot(root, asset, clock):
    """Retain the exact immutable artifact bytes used to compute the observation hash."""
    observations = []
    artifact_bytes = None
    for kind, item, maximum in [("artifact", asset, 16 * 1024 * 1024),
                                 *(("canary", entry, 4096) for entry in asset["canaries"])]:
        digest, error = None, None
        try:
            data = read_local(root, item["path"], maximum)
            digest = sha256(data)
            if kind == "artifact":
                artifact_bytes = data
        except Rejected as exc:
            error = str(exc)
        observations.append({"kind": kind, "path": item["path"], "sha256": digest,
                             "error": error, "observed_at": clock()})
    return observations, artifact_bytes
