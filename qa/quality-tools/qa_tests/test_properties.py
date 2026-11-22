"""Exercises the published code paths without importing archived third-party code."""
from pathlib import Path
from unittest.mock import patch
import os

from hypothesis import given, settings, strategies as st
import pytest

from superhunter.tools import verify_review_115 as receipts
from superhunter import product_dependency_attributions as go_reader

if os.environ.get("NQC_MUTATION") == "1":
    from mutation_subject import check_preserved_operations
else:
    check_preserved_operations = receipts.check_preserved_operations

FIELD = (141, "ossf/scorecard", "executable", "license_file_evidence")
EXTRA = (99, "nqc/test", "reference", "receipt", "d" * 64)
settings.register_profile("nqc", max_examples=32, derandomize=True, database=None, deadline=None)
settings.load_profile("nqc")


def key(receipt):
    return (*FIELD, receipts.sha(receipts.canonical(receipt)))


@given(st.binary(min_size=20, max_size=20), st.integers(), st.text(max_size=24))
def test_scorecard_changes_only_its_revision(seed, score, label):
    old = seed.hex()
    new = bytes(b ^ 255 for b in seed).hex()
    before = {"nqc_commit": old, "score": score, "label": label}
    after = {**before, "nqc_commit": new}
    previous = {key(before), EXTRA}
    current = {key(after), EXTRA}
    check_preserved_operations(previous, current, after, old, new)
    wrong_revision = "Scorecard identifies a different audited commit"
    changed = "previous accepted operations or their evidence changed"
    altered = {**after, "score": score + 1}
    for old_keys, new_keys, receipt, reason in [
        (previous, current, before, wrong_revision),
        (previous, {key(altered), EXTRA}, altered, changed),
        (previous, {key(after)}, after, changed),
        ({EXTRA}, current, after, changed),
        (previous, {EXTRA}, after, changed),
    ]:
        with pytest.raises(receipts.EvidenceError) as caught:
            check_preserved_operations(old_keys, new_keys, receipt, old, new)
        assert str(caught.value) == reason


def test_go_success_and_failure_clean_the_private_directory():
    go = Path(os.environ["NQC_STATE_GO"])
    original = go_reader.subprocess.run
    observed = []

    def observe(*args, **kwargs):
        work = kwargs["cwd"]
        config = Path(kwargs["env"]["XDG_CONFIG_HOME"])
        assert config.is_relative_to(work)
        assert (config / "go/telemetry/mode").read_bytes() == b"off\n"
        observed.append(work)
        return original(*args, **kwargs)

    with patch.object(go_reader.subprocess, "run", side_effect=observe):
        result = go_reader.parse_mod(b"module example.org/main\nrequire example.org/dep v1.0.0\n", go)
        assert result == ("example.org/main", {"example.org/dep": ("direct", "v1.0.0")})
        with pytest.raises(go_reader.EvidenceError, match="Go reader failed"):
            go_reader.parse_mod(b"invalid directive\n", go)
    assert len(set(observed)) == 2 and all(not p.exists() for p in observed)
