"""Verify the separately registered paired follow-up without altering matrix evidence."""
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
    ev = ROOT / "evidence/paired"
    m = json.loads((ev / "result.json").read_text()); values = {}
    def unpack(raw):
        v = array.array("Q"); v.frombytes(raw)
        if sys.byteorder != "little": v.byteswap()
        return v
    with zipfile.ZipFile(ev / "raw.zip") as z:
        assert len(z.namelist()) == 5
        for name in ("r3_native", "r4_native"):
            raw = z.read(name + ".bin"); values[name] = unpack(raw)
            assert hashlib.sha256(raw).hexdigest() == m["sample_sha256"][name]
            assert stats(values[name]) == m["stats_ns"][name]
            status = z.read(name + "-status.bin")
            assert len(status) == m["pairs"] and all(x in (0, 1) for x in status)
            drops = [d for d in m["drops"] if d["variant"] == name]
            assert sum(status) == len(drops)
            for d in drops:
                assert status[d["pair"]] == 1 and values[name][d["pair"]] == d["elapsed_ns"]
        assert stats(unpack(z.read("clock.bin"))) == m["clock_ns"]
    delta = [b - a for a, b in zip(values["r3_native"], values["r4_native"])]
    assert stats(delta) == m["paired_delta_r4_minus_r3_ns"]
    assert sum(d < 0 for d in delta) == m["r4_faster_pairs"]
    if not m["drops"]: assert len(set(m["output_sha256"].values())) == 1
    for f, digest in m["source_sha256"].items():
        assert hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == digest
    print(json.dumps({"verified": True, "pairs": m["pairs"], "windows": m["pairs"] * 2,
                      "drops_retained": len(m["drops"]), "source_matches": True}))


if __name__ == "__main__": main()
