"""Enroll one real local artifact; writes only a new canary and a new control directory."""

import secrets
from pathlib import Path

from .canary import seed
from .codec import Rejected, canonical, identifier
from .config import ConfigStore
from .engine import Engine
from .files import create_local, read_local, sha256


def enroll(assets_root, artifact_path, asset_id, canary_path, control_root):
    identifier(asset_id)
    assets_root = Path(assets_root).absolute()
    control_root = Path(control_root).absolute()
    # All source bytes are read before creating anything. Existing control state is never overwritten.
    digest = sha256(read_local(assets_root, artifact_path))
    if artifact_path == canary_path:
        raise Rejected("canary_overlaps_artifact")
    control_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    marker = seed(assets_root, canary_path)
    policy = {"schema": "nqc-defense-policy-v2", "rate_limit": 30,
              "rate_window_seconds": 60, "token_ttl_seconds": 120,
              "evidence_max_age_seconds": 5, "max_quarantined_assets": 1,
              "assets": [{"id": asset_id, "path": artifact_path, "sha256": digest, "canaries": [marker]}]}
    store = ConfigStore(control_root / "configs")
    policy_digest = store.put(canonical(policy))
    key = secrets.token_bytes(32)
    create_local(control_root, "ledger.key", key)
    engine = Engine(assets_root, store.root, control_root / "state", policy_digest, key)
    receipt = {"schema": "nqc-defense-enrollment-v1", "asset": asset_id,
               "assets_root": str(assets_root), "artifact": artifact_path,
               "artifact_sha256": digest, "canary": canary_path, "policy_digest": policy_digest,
               "checkpoint": engine.checkpoint()}
    create_local(control_root, "enrollment.json", canonical(receipt))
    return receipt
