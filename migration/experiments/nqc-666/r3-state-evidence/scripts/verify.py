"""Recompute delivered percentiles and check measured source/fixture identities."""
import array
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark import stats


def main():
    evidence = ROOT / "evidence"
    m = json.loads((evidence / "benchmark/benchmark.json").read_text())
    grouped = {}
    with zipfile.ZipFile(evidence / "benchmark/raw.zip") as archive:
        assert len(archive.namelist()) == len(m["runs"]) * 2
        for r in m["runs"]:
            raw = archive.read(r["label"] + ".bin")
            assert hashlib.sha256(raw).hexdigest() == r["sample_sha256"]
            def values(raw):
                a = array.array("Q")
                a.frombytes(raw)
                if sys.byteorder != "little": a.byteswap()
                return a
            v = values(raw)
            assert stats(v) == r["stats_ns"]
            assert stats(values(archive.read(r["label"] + "-clock.bin"))) == r["clock_control_ns"]
            grouped.setdefault(f'{r["mode"]}|shared{int(r["shared"])}', []).extend(v)
    assert {k: stats(v) for k, v in grouped.items()} == json.loads((evidence / "benchmark/summary.json").read_text())
    for key, digest in m["source_sha256"].items():
        assert hashlib.sha256((ROOT / key).read_bytes()).hexdigest() == digest, key
    for key, digest in m["parent_source_sha256"].items():
        assert hashlib.sha256((ROOT.parent / key).read_bytes()).hexdigest() == digest, key
    for mode in ("verify", "ingress_scenario"):
        assert len({r["observable_sha256"] for r in m["runs"] if r["mode"] == mode}) == 1
    provenance = json.loads((ROOT / "PROVENANCE.json").read_text())
    for entry in provenance["upstream"]:
        assert hashlib.sha256((ROOT / "reference/upstream" / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
    assert hashlib.sha256((ROOT / "fixtures/historical-header-26210229.json").read_bytes()).hexdigest() == provenance["historical_header"]["sha256"]
    print(json.dumps({"verified": True, "runs": len(m["runs"]), "windows": sum(len(v) for v in grouped.values()),
                      "source_and_parent_match_measurement": True, "observable_outputs_equal": True}))


if __name__ == "__main__":
    main()
