"""Exercise real local protection on a temporary copy of NQC's source manifest."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.codec import Rejected
from nqc_defense.files import sha256
from nqc_defense.managed_integrity import ManagedIntegrity
from nqc_defense.integration import verify_nqc


def run(repo):
    isolation = verify_nqc(repo)
    source = repo / "migration/source-manifest.json"
    original = source.read_bytes()
    with tempfile.TemporaryDirectory() as temporary:
        managed = ManagedIntegrity.create(source, Path(temporary) / "managed")
        assert not managed.inspect()["contained"]
        assert managed.read_json()["content_sha256"] == sha256(original)
        (managed.root / "assets/artifact.json").write_bytes(b'{"controlled_acceptance_mutation":true}')
        incident = managed.inspect()
        assert incident["contained"] and incident["incident"]["status"] == "open"
        try:
            managed.read_json()
        except Rejected as exc:
            assert str(exc) == "asset_quarantined"
        else:
            raise AssertionError("changed content was admitted")
        first_archive = managed.archive_evidence()
        assert first_archive["stored_pages_verified"]
        reopened = ManagedIntegrity(managed.root, managed.digest)
        assert reopened.status()["incident"] == incident["incident"]
        recovery = reopened.recover()
        assert recovery["read_after_recovery_verified"] and not recovery["contained"]
        assert recovery["incident"]["status"] == "resolved"
        assert recovery["restored_sha256"] == sha256(original)
        second_archive = reopened.archive_evidence()
        assert second_archive["stored_pages_verified"]
        assert reopened.witness.head()["checkpoint"] == reopened.engine.checkpoint()
        assert source.read_bytes() == original
        return {"verified": True, "source_sha256": sha256(original), "source_bytes": len(original),
                "source_unchanged": True, "mutation": "controlled change to temporary managed copy only",
                "incident": incident["incident"], "recovery": recovery,
                "incident_and_recovery_archives_verified": True,
                "witness_matches_engine": True, "nqc_isolation": isolation,
                "production_activated": False, "scope": "local managed JSON admission"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    print(json.dumps(run(parser.parse_args().repo.resolve()), indent=2, sort_keys=True))
