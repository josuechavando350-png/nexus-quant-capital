"""Exercise the inventory through its CLI and recheck three documented regressions."""
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
BASE = "05002c36c12a1b572b5d425b7b0714189c448109"


def invoke(repo, database, *options):
    return json.loads(subprocess.check_output(
        [sys.executable, "-B", "-m", "superhunter", "inventory", "--repo", str(repo),
         "--state", str(database), *options], cwd=PRODUCT))


def regression(case, tree):
    sys.path.insert(0, str(tree))
    if case == "informes":
        from superhunter.tools import verify_review_115 as r
        field = (141, "ossf/scorecard", "executable", "license_file_evidence")
        old = "604bd28d528ee809c8e6d38adab86ec6f67b652c"
        new = "f1eea76f24ff0cf0b5af4a870b5d6e117c46d248"
        data = {"nqc_commit": new, "score": 7}
        before = {(*field, r.sha(r.canonical({**data, "nqc_commit": old})))}
        after = {(*field, r.sha(r.canonical(data)))}
        with patch.object(r, "html_operations", return_value=before), patch.object(r, "operation_keys", return_value=after):
            args = ([], data) if "scorecard" in inspect.signature(r.check_previous_acceptance).parameters else ([],)
            try:
                r.check_previous_acceptance(*args)
            except r.EvidenceError as exc:
                if str(exc) != "previous accepted operations or their evidence changed":
                    raise
                return ["rejected legitimate revision change"]
        return []
    if case == "limpieza":
        from superhunter import product_dependency_attributions as reader
        observed = []
        native = subprocess.run

        def observe(*args, **kwargs):
            work = kwargs["cwd"]
            config = Path(kwargs["env"].get("XDG_CONFIG_HOME", work / ".config"))
            mode = config / "go/telemetry/mode"
            observed.append(mode.is_file() and mode.read_bytes() == b"off\n")
            return native(*args, **kwargs)

        with patch.object(reader.subprocess, "run", side_effect=observe):
            result = reader.parse_mod(b"module example.org/main\nrequire example.org/dep v1.0.0\n",
                                      Path(os.environ["NQC_STATE_GO"]))
        assert result == ("example.org/main", {"example.org/dep": ("direct", "v1.0.0")})
        assert len(observed) == 1
        return [] if observed[0] else ["Go started without private telemetry mode off"]
    if case != "inventario":
        raise ValueError(case)
    component_data = subprocess.check_output([sys.executable, "-B", "-c",
        "import json; from superhunter.quality import COMPONENTS; print(json.dumps(COMPONENTS))"], cwd=tree)
    sys.path[0] = str(PRODUCT)
    from superhunter import quality
    return quality.validate_components(quality.source_snapshot(tree / "superhunter"), json.loads(component_data))


def archive(rev, path):
    with tempfile.TemporaryFile() as file:
        subprocess.run(["git", "-C", str(PRODUCT), "archive", rev], stdout=file, check=True)
        file.seek(0)
        with tarfile.open(fileobj=file) as tar:
            tar.extractall(path, filter="data")


def main(out):
    sys.path.insert(0, str(PRODUCT))
    from superhunter import quality
    out.mkdir(exist_ok=False, parents=True)
    scores = {}
    for rev, n in [(BASE, 742), ("HEAD", 743)]:
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            dest = work / "checkout"
            subprocess.run(["git", "init", "-q", str(dest)], check=True)
            objects = subprocess.check_output(["git", "-C", str(PRODUCT), "rev-parse",
                                              "--path-format=absolute", "--git-path", "objects"])
            (dest / ".git/objects/info/alternates").write_bytes(objects)
            target = subprocess.check_output(["git", "-C", str(PRODUCT), "rev-parse", rev]).decode().strip()
            subprocess.run(["git", "-C", str(dest), "checkout", "-q", "--detach", target], check=True)
            db = work / "progress.db"
            partial = invoke(dest, db, "--batch-size", "127", "--max-batches", "2")
            assert partial == invoke(dest, db, "--status")
            assert len(partial["reviewed"]) == partial["reviewed_count"] == 254
            assert not (set(partial["reviewed"]) & set(partial["pending"]))
            assert partial["status"] == "partial" and len(partial["pending"]) == n - 254
            # Kill this child after it has inserted two rows of an uncommitted batch.
            child = """
import os, signal, sys
from pathlib import Path
from superhunter import inventory_checkpoint as inventory
original = inventory.verified_digest
calls = 0
def interrupt(*args):
    global calls
    calls += 1
    if calls == 3:
        os.kill(os.getpid(), signal.SIGKILL)
    return original(*args)
inventory.verified_digest = interrupt
inventory.inspect(Path(sys.argv[1]), Path(sys.argv[2]), 127, None)
"""
            killed = subprocess.run([sys.executable, "-B", "-c", child, str(dest), str(db)], cwd=PRODUCT)
            assert killed.returncode == -signal.SIGKILL
            assert partial == invoke(dest, db, "--status")
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(invoke, dest, db) for _ in range(2)]
                full, concurrent = [f.result() for f in futures]
            assert concurrent == full
            snap = quality.source_snapshot(dest / "superhunter")
            assert full["reviewed"] == sorted(snap)
            assert full["pending"] == [] and full["status"] == "complete"
            assert full["total"] == n == full["reviewed_count"]
            assert full["snapshot_sha256"] == quality.sha(quality.canonical(snap))
            assert full == invoke(dest, work / "fresh.db")
            if rev == "HEAD":
                assert not quality.validate_components(snap)
            # Cache and workspace edits must never certify an altered snapshot.
            source = dest / "superhunter" / full["reviewed"][0]
            original = source.read_bytes()
            source.write_bytes(original + b" ")
            try:
                invoke(dest, db)
            except subprocess.CalledProcessError as exc:
                assert exc.returncode == 2
            else:
                raise AssertionError("changed file accepted")
            source.write_bytes(original)
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE files SET digest='invalid' WHERE path=?", (full["reviewed"][0],))
            try:
                invoke(dest, db)
            except subprocess.CalledProcessError as exc:
                assert exc.returncode == 2
            else:
                raise AssertionError("damaged checkpoint accepted")
            scores[rev] = {"total": n, "resumed_from": 254, "sha256": full["snapshot_sha256"]}
            (out / (rev + "-inventory.json")).write_text(json.dumps(full, sort_keys=True) + "\n")

    cases = json.loads((HERE.parent / "nqc-history/cases.json").read_text())
    expected = {"inventario": ["unmapped runtime source: product_report_quality_sources.py"],
                "informes": ["rejected legitimate revision change"],
                "limpieza": ["Go started without private telemetry mode off"]}
    for c in cases:
        answers = {}
        for side in ("before", "after"):
            with tempfile.TemporaryDirectory() as temp:
                archive(c[side], temp)
                raw = subprocess.check_output([sys.executable, "-I", "-B", __file__, str(PRODUCT),
                                               "case", c["case"], temp])
                answers[side] = json.loads(raw)
        assert answers == {"before": expected[c["case"]], "after": []}, answers
        scores[c["case"]] = answers
    (out / "checks.json").write_text(json.dumps(scores, indent=2) + "\n")
    print(json.dumps(scores))


if __name__ == "__main__":
    PRODUCT = Path(sys.argv[1]).resolve()
    if sys.argv[2] == "case":
        print(json.dumps(regression(sys.argv[3], Path(sys.argv[4]))))
    else:
        main(Path(sys.argv[2]).resolve())
