"""Check raw measurements, outcomes, differential corpus and measured sources."""
import array
import gzip
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark import stats


def main():
    ev = ROOT / "evidence"
    m = json.loads((ev / "benchmark/benchmark.json").read_text())
    groups = {}
    def unpack(raw):
        v = array.array("Q"); v.frombytes(raw)
        if sys.byteorder != "little": v.byteswap()
        return v
    with zipfile.ZipFile(ev / "benchmark/raw.zip") as z:
        assert len(z.namelist()) == len(m["runs"]) * 3
        for r in m["runs"]:
            raw = z.read(r["label"] + ".bin"); status = z.read(r["label"] + "-status.bin")
            assert hashlib.sha256(raw).hexdigest() == r["sample_sha256"]
            assert hashlib.sha256(status).hexdigest() == r["status_sha256"]
            v = unpack(raw)
            assert stats(v) == r["stats_ns"]
            assert stats(unpack(z.read(r["label"] + "-clock.bin"))) == r["clock_ns"]
            assert len(status) == len(v) and all(x in (0, 1) for x in status)
            assert sum(status) == r["rejected"] == len(r["drops"])
            for drop in r["drops"]:
                assert status[drop["index"]] == 1 and v[drop["index"]] == drop["elapsed_ns"]
            groups.setdefault(r["mode"] + "|" + r["variant"], []).extend(v)
    assert {k: stats(v) for k, v in groups.items()} == json.loads((ev / "benchmark/summary.json").read_text())
    for base, key in ((ROOT, "source_sha256"), (ROOT.parent, "parent_source_sha256")):
        for path, expected in m[key].items():
            assert hashlib.sha256((base / path).read_bytes()).hexdigest() == expected, path
    for mode in ("math", "hot_scenario", "full_ingress"):
        # Without drops, all variants/repetitions must also have identical whole-run outputs.
        accepted = [r for r in m["runs"] if r["mode"] == mode and r["rejected"] == 0]
        assert len({r["accepted_output_sha256"] for r in accepted}) <= 1
    d = json.loads((ev / "differential/result.json").read_text())
    for name in ("inputs", "outputs"):
        assert hashlib.sha256(gzip.decompress((ev / "differential" / (name + ".txt.gz")).read_bytes())).hexdigest() == d[name + "_sha256"]
    print(json.dumps({"verified": True, "windows": sum(len(v) for v in groups.values()),
                      "runs": len(m["runs"]), "drops_retained": sum(r["rejected"] for r in m["runs"]),
                      "native_parity_cases": d["cases"], "source_and_parent_match": True}))


if __name__ == "__main__": main()
