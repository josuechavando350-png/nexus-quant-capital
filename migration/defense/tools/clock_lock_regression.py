"""Measure token-expiry behavior across a real SQLite lock in a selected local package."""

import argparse
import concurrent.futures
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading


def run(package):
    sys.path.insert(0, str(package))
    import nqc_defense
    from nqc_defense.canary import seed
    from nqc_defense.codec import Rejected, canonical
    from nqc_defense.config import ConfigStore
    from nqc_defense.engine import Engine
    from nqc_defense.files import sha256
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assets = root / "assets"
        assets.mkdir()
        payload = (package / "nqc_defense/engine.py").read_bytes()
        (assets / "source.py").write_bytes(payload)
        marker = seed(assets, "guard")
        policy = {"schema": "nqc-defense-policy-v1", "rate_limit": 30, "rate_window_seconds": 60,
                  "token_ttl_seconds": 120, "assets": [{"id": "source", "path": "source.py",
                  "sha256": sha256(payload), "canaries": [marker]}]}
        store = ConfigStore(root / "configs")
        digest = store.put(canonical(policy))
        current = [1000]
        engine = Engine(assets, store.root, root / "state", digest, secrets.token_bytes(32), clock=lambda: current[0])
        token = engine.issue("operator", "source")
        entered, sampled = threading.Event(), threading.Event()
        def clock():
            sampled.set()
            return current[0]
        engine.clock = clock
        def worker():
            entered.set()
            return engine.process(canonical({"request_id": "lock-boundary", "asset": "source"}), token)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with engine.state.transaction():
                task = pool.submit(worker)
                if not entered.wait(2):
                    raise RuntimeError("worker did not start")
                early = sampled.wait(0.2)
                current[0] = 1120
            try:
                result = task.result(timeout=5)["decision"]
            except Rejected as exc:
                result = str(exc)
        return {"version": nqc_defense.__version__, "clock_sampled_while_write_lock_held": early,
                "clock_at_issuance": 1000, "clock_at_lock_release": 1120,
                "ttl_seconds": 120, "result": result,
                "measurement": "actual SQLite lock and file reads; controlled clock for expiry boundary"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    print(json.dumps(run(parser.parse_args().package.absolute()), indent=2, sort_keys=True))
