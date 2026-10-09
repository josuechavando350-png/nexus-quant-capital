#!/usr/bin/env python3
"""Local-only historical PFT materialization for the isolated NQC consumer.

This bridge does not transplant ancestry or certify the consumer. Trust starts at
reviewed, fixed acquisition pins; a repository name or local JSON cannot prove
GitHub origin. No network acquisition, fallback, replay, or workflow activation.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile

SOURCE_REPOSITORY = "josuechavando350-png/nexus-engine"
SOURCE_REPOSITORY_ID = 1333360261
SOURCE_COMMIT = "e259739c9f75fedcd1061d2f78d6b8852e7a3060"
SOURCE_TREE = "c9cc97b31daa96c3c427c6781333a706e988f342"
SOURCE_REF = "refs/evidence/pr668-head"
BUNDLE_SHA256 = "4568af03c4850c6aabf09b5b2897ed3d1fc856f439497f866ca92e31b7aaadac"
HISTORICAL_REFS = {'refs/evidence/d06_base': '8ebf6860e0a16964f5293df0ef40695b303b286d', 'refs/evidence/d06_original_source': 'a33a012591cd6625ddb921d995bb1bd95b4a5406', 'refs/evidence/pr668-head': 'e259739c9f75fedcd1061d2f78d6b8852e7a3060', 'refs/evidence/protocol_fork_certified': '5b4a0cb778cb4370cd54eb6fcba765dc8d7cecdf', 'refs/evidence/recertification_base': '3b23804a46bfcc730d57784fb95a349e6e6e726b', 'refs/evidence/rmc001_merge': 'cea25577edfcaf89dc8fc8bf60ee04bc01d01a3d', 'refs/evidence/rmc002_merge': '0d90ee7a7d439d2c658209c8fe176a8dda6bcbcb', 'refs/evidence/rmc003_2_authority': '519e5f6f7a4d42ff1cab67fef8306cfef9aab120', 'refs/evidence/rmc003_typed_authority': '5e032b2a601a2368334477e6ad9ee5c5b7ba219a', 'refs/evidence/rmc004_base': '765dc30fdd178a4960ade1e106669eb0b023fbeb'}
HISTORICAL_TREES = {'refs/evidence/protocol_fork_certified': 'ef3498da528f85cdb9fdd82222d64773a557f853', 'refs/evidence/rmc001_merge': 'a4425a06bb8f3ca28c1ee55e1f791871bac8c137', 'refs/evidence/rmc002_merge': '400e1b3209a3f01517e24be6f96a7e7e8406d019', 'refs/evidence/rmc004_base': 'e33fccfcf2af1ab0c121a2bb01d20cee4af97426', 'refs/evidence/rmc003_typed_authority': '5e99079028afaa05dc48dcbb9269e76469de1f05', 'refs/evidence/rmc003_2_authority': '2a0679bde85cc2eb8ca55c1c2f2e686d21319ba2', 'refs/evidence/d06_base': '001631a59bb1dc9fd6f34fa3727d96308dc7a035', 'refs/evidence/d06_original_source': 'eda36fdc07e82ccdcc9666799fa8fe21aacc7f1d', 'refs/evidence/recertification_base': 'dfe13d627fce711063079e764111b8b081363db3', 'refs/evidence/pr668-head': 'c9cc97b31daa96c3c427c6781333a706e988f342'}
MANIFEST_SHA256 = "07c126f5ccaba1d05d22e4adf964d57f59707d158ce76856ed92badec83a9b67"
VERIFIER_SHA256 = "5a590e40aa6079ca2a2dd14c69b4e1c6304e26de1afc3f484e6b02cfa5820fa9"
CONSUMER_REPOSITORY = "josuechavando350-png/nexus-quant-capital"
CONSUMER_REPOSITORY_ID = 1411047452
PFT = "5b4a0cb778cb4370cd54eb6fcba765dc8d7cecdf"
PFT_TREE = "ef3498da528f85cdb9fdd82222d64773a557f853"
RECERTIFICATION_BASE = "3b23804a46bfcc730d57784fb95a349e6e6e726b"
D06_BASE = "8ebf6860e0a16964f5293df0ef40695b303b286d"
RMC003_2 = "519e5f6f7a4d42ff1cab67fef8306cfef9aab120"
D06_SOURCE = "a33a012591cd6625ddb921d995bb1bd95b4a5406"
PFT_PATHS = tuple("ci/nqc-protocol-fork/" + p for p in (
    "recovered-source", "reimplementation", "compatibility", "locks",
    "PROTOCOL_FORK_TRUTH_CONTRACT.json", "PROTOCOL_FORK_FINAL_CLOSEOUT.json"))
CORE_PATHS = tuple("nqc-census/crates/" + p for p in (
    "nqc-census-core", "nqc-census-store", "nqc-census-chain"))
D06_PATHS = ("ci/nqc-census/rpc-providers.json", "ci/nqc-census/aave-history-providers.json",
             "ci/nqc-census/aave-discovery-scope.json", "nqc-census/rust-toolchain.toml")
HISTORICAL_PATHS = ("ci/nqc-census", "ci/nqc-protocol-fork", "nqc-census")
MIGRATION_FILES = {"HISTORICAL-ADAPTER.md", "IMPORT-PLAN.md", "VALIDATION.md",
                   "materialize_historical_source.py", "source-manifest.json",
                   "test_historical_source_adapter.py", "test_isolation.py", "verify_isolation.py",
                   "acquire_historical_source.py"}


class AdapterError(ValueError):
    """Fail closed; never reinterpret failure as historical or new authority."""


def require(condition, message):
    if not condition:
        raise AdapterError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular_bytes(path, limit=32 * 1024 * 1024):
    path = Path(path)
    require(stat.S_ISREG(path.lstat().st_mode), f"nonregular input: {path}")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "input type/size")
        data = stream.read(limit + 1)
    require(len(data) <= limit, "input exceeds size limit")
    return data


def environment(home):
    # Do not inherit Git alternate objects, replacement refs, config, credentials,
    # Python imports, proxies, SSH commands, or lazy-fetch authorization.
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
            "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "",
            "GIT_OPTIONAL_LOCKS": "0", "PYTHONDONTWRITEBYTECODE": "1"}


def run(command, *, cwd, env):
    result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0,
            f"command failed ({result.returncode}): {command[0]}: " +
            result.stderr.decode(errors="replace")[-2500:])
    return result.stdout


def git(repo, *args, env):
    return run(["git", "--no-replace-objects", "-c", "protocol.allow=never",
                "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                "-c", "core.untrackedCache=false", "-c", "core.attributesFile=/dev/null",
                "-c", "core.commitGraph=false", "-c", "core.multiPackIndex=false",
                "-C", repo, *args], cwd=repo, env=env)


def identity(repo, env):
    commit = git(repo, "rev-parse", "--verify", "HEAD^{commit}", env=env).decode().strip()
    tree = git(repo, "rev-parse", "--verify", "HEAD^{tree}", env=env).decode().strip()
    require(all(re.fullmatch("[0-9a-f]{40}", x) for x in (commit, tree)), "invalid Git identity")
    return commit, tree


def safe_repo_path(path):
    require(isinstance(path, str) and 0 < len(path) <= 512, "invalid source path")
    parts = path.split("/")
    require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) and p not in (".", "..", ".git")
                for p in parts), "unsafe source path")
    return PurePosixPath(path)


def tree_entries(repo, commit, paths, env):
    raw = git(repo, "ls-tree", "-r", "-z", commit, "--", *paths, env=env)
    entries = []
    seen = set()
    for row in raw.split(b"\0"):
        if not row:
            continue
        meta, raw_path = row.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        path = raw_path.decode()
        safe_repo_path(path)
        require(kind == "blob" and mode in ("100644", "100755"), "unsafe Git entry")
        require(path not in seen, "duplicate Git path")
        seen.add(path)
        entries.append((path, mode, oid))
    require(entries, "empty historical path selection")
    return entries


def verify_historical_authority(repo, env):
    for path in ("shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates"):
        require(not (repo / ".git" / path).exists(), "historical store has alternate or incomplete history")
    require(not git(repo, "for-each-ref", "refs/replace/", env=env).strip(), "historical replacement refs")
    for ref, commit in HISTORICAL_REFS.items():
        require(git(repo, "rev-parse", ref + "^{commit}", env=env).decode().strip() == commit,
                "historical evidence ref changed")
    git(repo, "fsck", "--full", "--strict", "--no-reflogs", env=env)
    require(identity(repo, env) == (SOURCE_COMMIT, SOURCE_TREE), "historical HEAD/tree changed")
    require(git(repo, "rev-parse", SOURCE_REF, env=env).decode().strip() == SOURCE_COMMIT,
            "historical source ref changed")
    require(git(repo, "rev-parse", PFT + "^{tree}", env=env).decode().strip() == PFT_TREE,
            "certified PFT tree changed")
    edges = ((PFT, SOURCE_COMMIT), (RECERTIFICATION_BASE, SOURCE_COMMIT),
             (D06_BASE, SOURCE_COMMIT), (D06_BASE, RMC003_2), (RMC003_2, SOURCE_COMMIT))
    for ancestor, descendant in edges:
        git(repo, "merge-base", "--is-ancestor", ancestor, descendant, env=env)
    for ancestor, paths in ((PFT, PFT_PATHS), (RMC003_2, CORE_PATHS), (D06_SOURCE, D06_PATHS)):
        git(repo, "diff", "--no-ext-diff", "--no-textconv", "--quiet", ancestor,
            SOURCE_COMMIT, "--", *paths, env=env)
    protected = PFT_PATHS + CORE_PATHS + D06_PATHS
    require(not git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--",
                    *protected, env=env).strip(), "historical protected worktree changed")
    return [{"ancestor": a, "descendant": b} for a, b in edges]


def import_historical_bundle(bundle_bytes, work, env, source_ref=SOURCE_REF):
    require(source_ref == SOURCE_REF, "substituted historical source ref")
    require(digest(bundle_bytes) == BUNDLE_SHA256, "historical bundle digest mismatch")
    bundle = work / "verified-history.bundle"
    bundle.write_bytes(bundle_bytes)
    repo = work / "historical-source"
    repo.mkdir()
    git(repo, "init", "--quiet", "--template=", env=env)
    expected = sorted(f"{commit} {ref}" for ref, commit in HISTORICAL_REFS.items())
    require(sorted(git(repo, "bundle", "list-heads", bundle, env=env).decode().splitlines()) == expected,
            "bundle ref inventory changed")
    git(repo, "bundle", "verify", bundle, env=env)
    require(sorted(git(repo, "bundle", "unbundle", bundle, env=env).decode().splitlines()) == expected,
            "unbundled ref changed")
    for ref, commit in HISTORICAL_REFS.items():
        git(repo, "update-ref", ref, commit, env=env)
    git(repo, "update-ref", "HEAD", SOURCE_COMMIT, env=env)
    git(repo, "fsck", "--full", "--strict", "--no-reflogs", env=env)
    # Explicit non-cone sparse checkout: no root/client/workflow files are written.
    git(repo, "config", "core.sparseCheckout", "true", env=env)
    (repo / ".git/info").mkdir(exist_ok=True)
    (repo / ".git/info/sparse-checkout").write_text("".join("/" + p + "/\n" for p in HISTORICAL_PATHS))
    tree_entries(repo, SOURCE_COMMIT, HISTORICAL_PATHS, env)
    git(repo, "read-tree", "-mu", "HEAD", env=env)
    edges = verify_historical_authority(repo, env)
    return repo, edges


def load_source_metadata(path):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "duplicate source metadata key")
            result[key] = value
        return result
    data = json.loads(regular_bytes(path), object_pairs_hook=pairs)
    require(set(data) == {"schema", "source_repository", "source_repository_id", "retrieved_at",
                          "repository_metadata", "commit_metadata", "git_transport_url"},
            "historical source metadata schema fields changed")
    require(data["schema"] == "nqc-public-historical-source-metadata-v1", "historical metadata schema")
    require(data["source_repository"] == SOURCE_REPOSITORY and
            type(data["source_repository_id"]) is int and data["source_repository_id"] == SOURCE_REPOSITORY_ID,
            "historical metadata repository identity changed")
    api = "https://api.github.com/repos/" + SOURCE_REPOSITORY
    require(data["git_transport_url"] == "https://github.com/" + SOURCE_REPOSITORY + ".git",
            "historical Git transport changed")
    repository = data["repository_metadata"]
    require(repository.get("full_name") == SOURCE_REPOSITORY and
            type(repository.get("id")) is int and repository["id"] == SOURCE_REPOSITORY_ID and
            repository.get("url") == api and repository.get("private") is False,
            "historical repository metadata mismatch")
    require(set(data["commit_metadata"]) == set(HISTORICAL_REFS), "historical metadata ref inventory changed")
    for ref, commit in HISTORICAL_REFS.items():
        record = data["commit_metadata"][ref]
        require(record.get("sha") == commit and record.get("tree", {}).get("sha") == HISTORICAL_TREES[ref]
                and record.get("url") == api + "/git/commits/" + commit,
                "historical metadata commit/tree mismatch")
    require(isinstance(data["retrieved_at"], str) and
            re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", data["retrieved_at"]),
            "historical metadata acquisition timestamp")
    return data


def verify_source_store(store, env):
    # The source store is read-only input. Never copy its config/hooks or checkout.
    verify_consumer_git_config(store, env)
    for rel in ("shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates"):
        require(not (store / ".git" / rel).exists(), "source store has incomplete or alternate history")
    objects = store / ".git/objects"
    require(objects.is_dir() and objects.resolve() == objects, "source object directory alias")
    total = count = 0
    for path in objects.rglob("*"):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "unsafe source object path")
        if stat.S_ISREG(info.st_mode):
            rel = path.relative_to(objects).as_posix()
            require(re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{38}", rel) or
                    re.fullmatch(r"pack/pack-[0-9a-f]{40}\.(pack|idx|rev)", rel),
                    "unreviewed or promisor source object file: " + repr(rel))
            total += info.st_size; count += 1
    require(count <= 100000 and total <= 512 * 1024 * 1024, "source object store size limit")
    for rel in ("HEAD", "packed-refs"):
        path = store / ".git" / rel
        if path.exists() or path.is_symlink():
            regular_bytes(path, limit=1024 * 1024)
    refs_dir = store / ".git/refs"
    require(not refs_dir.is_symlink(), "unsafe source ref directory")
    for path in refs_dir.rglob("*"):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "unsafe source ref path")
        if stat.S_ISREG(info.st_mode):
            regular_bytes(path, limit=65536)
    refs = git(store, "for-each-ref", "--format=%(refname) %(objectname)", env=env).decode().splitlines()
    require(sorted(refs) == sorted(ref + " " + sha for ref, sha in HISTORICAL_REFS.items()),
            "source store ref inventory changed")
    for ref, tree in HISTORICAL_TREES.items():
        require(git(store, "rev-parse", ref + "^{tree}", env=env).decode().strip() == tree,
                "source store original tree changed")
    git(store, "fsck", "--full", "--strict", "--no-reflogs", env=env)
    git(store, "rev-list", "--objects", "--missing=error", *HISTORICAL_REFS.values(), env=env)


def import_historical_store(store, metadata_path, work, env):
    store = Path(store).absolute()
    require(store.resolve(strict=True) == store, "source store path aliases")
    metadata = load_source_metadata(metadata_path)
    verify_source_store(store, env)
    repo = work / "historical-source"
    repo.mkdir()
    git(repo, "init", "--quiet", "--template=", env=env)
    shutil.copytree(store / ".git/objects", repo / ".git/objects", dirs_exist_ok=True)
    for ref, commit in HISTORICAL_REFS.items():
        git(repo, "update-ref", ref, commit, env=env)
    git(repo, "update-ref", "HEAD", SOURCE_COMMIT, env=env)
    git(repo, "config", "core.sparseCheckout", "true", env=env)
    (repo / ".git/info").mkdir(exist_ok=True)
    (repo / ".git/info/sparse-checkout").write_text("".join("/" + p + "/\n" for p in HISTORICAL_PATHS))
    tree_entries(repo, SOURCE_COMMIT, HISTORICAL_PATHS, env)
    git(repo, "read-tree", "-mu", "HEAD", env=env)
    edges = verify_historical_authority(repo, env)
    return repo, edges, metadata


def verify_consumer_git_config(repo, env):
    """Reject executable/redirection config before any consumer Git operation."""
    gitdir = repo / ".git"
    require(gitdir.is_dir() and not gitdir.is_symlink(), "consumer needs its own Git directory")
    # Git may dereference object/ref/index files even during identity lookup.
    # Reject FIFOs/devices/symlinks before any repository Git operation.
    for rel in ("objects", "refs", "info"):
        path = gitdir / rel
        require(not path.is_symlink(), "unsafe Git metadata directory alias")
    count = total = 0
    for rel in ("objects", "refs"):
        for path in (gitdir / rel).rglob("*"):
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "unsafe Git object/ref path")
            if stat.S_ISREG(info.st_mode):
                count += 1; total += info.st_size
    require(count <= 100000 and total <= 512 * 1024 * 1024, "Git metadata size limit")
    for rel in ("HEAD", "packed-refs", "index"):
        path = gitdir / rel
        if path.exists() or path.is_symlink():
            regular_bytes(path, limit=64 * 1024 * 1024)
    for rel in ("commondir", "config.worktree", "info/attributes"):
        require(not (gitdir / rel).exists() and not (gitdir / rel).is_symlink(),
                "consumer Git metadata can redirect or execute filters")
    config = regular_bytes(gitdir / "config", limit=1024 * 1024)
    # `git config` runs outside the consumer and cannot discover its repository.
    # --no-includes exposes include keys for rejection without following them.
    with tempfile.TemporaryDirectory(prefix="nqc-git-config-", dir=env["HOME"]) as name:
        scratch = Path(name)
        path = scratch / "config"
        path.write_bytes(config)
        records = run(["git", "config", "--file", path, "--no-includes", "--null", "--list"],
                      cwd=scratch, env=env).split(b"\0")
    core = {"core.repositoryformatversion": {"0"}, "core.filemode": {"true", "false"},
            "core.bare": {"false"}, "core.logallrefupdates": {"true", "false"},
            "core.sparsecheckout": {"true", "false"}, "gc.auto": {"0"}}
    for raw in records:
        if not raw:
            continue
        key, separator, value = raw.decode().partition("\n")
        require(separator, "unsupported valueless consumer Git configuration")
        if key in core:
            require(value in core[key], "unsupported consumer core Git configuration")
        else:
            require(key in {"user.name", "user.email"} or
                    re.fullmatch(r"remote\.[A-Za-z0-9._-]+\.(url|fetch)", key) or
                    re.fullmatch(r"branch\.[A-Za-z0-9._/-]+\.(remote|merge)", key),
                    "unsafe or unreviewed consumer Git configuration: " + key)
    require(regular_bytes(gitdir / "config", limit=1024 * 1024) == config,
            "consumer Git configuration changed during preflight")


def verify_consumer(repo, expected_commit, expected_tree, historical, env):
    verify_consumer_git_config(repo, env)
    require(all(isinstance(x, str) and re.fullmatch("[0-9a-f]{40}", x)
                for x in (expected_commit, expected_tree)), "expected consumer identity must be exact")
    require(identity(repo, env) == (expected_commit, expected_tree), "consumer HEAD/tree mismatch")
    require(Path(git(repo, "rev-parse", "--show-toplevel", env=env).decode().strip()) == repo,
            "consumer Git worktree redirected")
    require(expected_commit not in (SOURCE_COMMIT, D06_SOURCE, PFT), "consumer/source identity conflated")
    require((repo / ".git").is_dir() and not (repo / ".git").is_symlink(), "consumer needs its own Git directory")
    for path in ("shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates"):
        require(not (repo / ".git" / path).exists(), "consumer has alternate or incomplete history")
    require(not git(repo, "for-each-ref", "refs/replace/", env=env).strip(), "consumer replacement refs")
    ancestors = set(git(repo, "rev-list", "HEAD", env=env).decode().splitlines())
    original_ancestors = set(git(historical, "rev-list", *HISTORICAL_REFS.values(),
                                 env=env).decode().splitlines())
    require(not ancestors.intersection(original_ancestors), "consumer carries original ancestry")
    git(repo, "fsck", "--full", "--strict", "--no-reflogs", env=env)
    flags = git(repo, "ls-files", "-v", env=env).decode().splitlines()
    require(all(row.startswith("H ") for row in flags), "consumer index hides worktree paths")
    require(not git(repo, "status", "--porcelain=v1", "--untracked-files=all", env=env).strip(),
            "consumer checkout is not clean")
    manifest = repo / "migration/source-manifest.json"
    verifier = repo / "migration/verify_isolation.py"
    require(digest(regular_bytes(manifest)) == MANIFEST_SHA256, "source manifest changed")
    require(digest(regular_bytes(verifier)) == VERIFIER_SHA256, "isolation verifier changed")
    adapter = "migration/materialize_historical_source.py"
    committed_adapter = git(repo, "show", expected_commit + ":" + adapter, env=env)
    require(committed_adapter == regular_bytes(Path(__file__)) == regular_bytes(repo / adapter),
            "adapter implementation is not bound to consumer commit")
    # The reviewed verifier validates all 637 imported mappings and all original
    # refs against the separate source store, including mode and content hashes.
    composition = repo / "migration/verify_standalone_composition.py"
    require(regular_bytes(composition) == git(repo, "show", expected_commit +
            ":migration/verify_standalone_composition.py", env=env), "composition verifier not bound to consumer")
    result = json.loads(run([sys.executable, "-I", "-B", composition, "--root", repo,
                            "--source-git", historical, "--expected-commit", expected_commit,
                            "--expected-tree", expected_tree], cwd=repo, env=env))
    require(result["status"] == "STANDALONE_COMPOSITION_PASS" and
            result["canonical_recertification"] is False, "consumer source binding failed")
    # Independently compare frozen WHOLE core/store/chain and PFT paths. Do not
    # narrow this to D06-touched files, selected crates, or a partial core module.
    frozen = PFT_PATHS + CORE_PATHS + D06_PATHS
    require(tree_entries(repo, expected_commit, frozen, env) ==
            tree_entries(historical, SOURCE_COMMIT, frozen, env), "consumer frozen paths changed")
    return result


ISOLATED_MATERIALIZER = r'''
import importlib.util, json, pathlib, subprocess, sys
source, output, proof, parent = map(str, sys.argv[1:])
p = pathlib.Path(source) / 'ci/nqc-census/run_rmc006_recertification.py'
spec = importlib.util.spec_from_file_location('historical_network_proof', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
network = m.network_proof(parent)
pathlib.Path(proof).write_text(json.dumps(network, sort_keys=True, indent=2) + '\n')
subprocess.run([sys.executable, '-I', '-B', str(pathlib.Path(source) / 'ci/nqc-census/materialize_effective_source.py'), '--output', output], check=True)
'''


def publish_no_replace(stage, output):
    """Linux atomic publish without replacing even a concurrent empty directory."""
    libc = ctypes.CDLL(None, use_errno=True)
    require(hasattr(libc, "renameat2"), "atomic no-replace publication unavailable")
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(stage), -100, os.fsencode(output), 1) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(output))


def materialize(consumer, bundle, output, expected_commit, expected_tree,
                source_repository=SOURCE_REPOSITORY, source_repository_id=SOURCE_REPOSITORY_ID,
                source_ref=SOURCE_REF, source_store=None, source_metadata=None):
    require((source_repository, type(source_repository_id), source_repository_id) ==
            (SOURCE_REPOSITORY, int, SOURCE_REPOSITORY_ID), "historical repository identity changed")
    require((bundle is None) != (source_store is None), "choose exactly one historical input mode")
    require((source_store is None) == (source_metadata is None), "source store requires source metadata")
    consumer, output = map(lambda p: Path(p).absolute(), (consumer, output))
    require(not consumer.is_symlink() and consumer.resolve() == consumer, "consumer path aliases")
    require(not output.exists() and not output.is_symlink(), "output already exists")
    require(output.parent.is_dir() and output.parent.resolve() == output.parent, "output parent aliases")
    require(not output.is_relative_to(consumer) and not consumer.is_relative_to(output), "output overlaps consumer")
    if bundle is not None:
        bundle = Path(bundle).absolute()
        require(bundle.resolve(strict=True) == bundle, "historical bundle path aliases")
        require(not bundle.is_relative_to(consumer), "historical full bundle must stay outside consumer")
        bundle_bytes = regular_bytes(bundle)
    else:
        require(not Path(source_store).resolve().is_relative_to(consumer), "source store overlaps consumer")
    with tempfile.TemporaryDirectory(prefix="nqc-historical-source-", dir=output.parent) as tmp:
        work = Path(tmp)
        env = environment(work)
        require(source_ref == SOURCE_REF, "substituted historical source ref")
        source_acquisition = None
        if bundle is not None:
            historical, edges = import_historical_bundle(bundle_bytes, work, env, source_ref)
        else:
            historical, edges, source_acquisition = import_historical_store(
                source_store, source_metadata, work, env)
        binding = verify_consumer(consumer, expected_commit, expected_tree, historical, env)
        stage = work / "result"
        stage.mkdir()
        parent_net = os.readlink("/proc/self/ns/net")
        materializer_log = run(["unshare", "--user", "--map-root-user", "--net",
                               sys.executable, "-I", "-B", "-c", ISOLATED_MATERIALIZER,
                               historical, stage / "effective-source", stage / "network-isolation.json",
                               parent_net], cwd=historical, env=env)
        (stage / "materializer.log").write_bytes(materializer_log)
        original = regular_bytes(stage / "effective-source/MATERIALIZATION.json")
        receipt = json.loads(original)
        require(receipt["materializer_head"] == SOURCE_COMMIT and
                receipt["protocol_fork_certified_commit"] == PFT and
                receipt["protocol_fork_certified_tree"] == PFT_TREE, "historical receipt relabelled")
        require(receipt["invariants"]["production_authority"] is False, "historical production claim")
        # Check again after the subprocess; receipts never bless a changed checkout.
        verify_consumer(consumer, expected_commit, expected_tree, historical, env)
        verify_historical_authority(historical, env)
        seed_pin = json.loads(regular_bytes(historical / "ci/nqc-census/rmc006-recertification-source.json"))
        report = {
            "schema": "nqc-standalone-historical-materialization-v1",
            "status": "HISTORICAL_SOURCE_MATERIALIZED_CONSUMER_BOUND",
            "historical_source": {"repository": SOURCE_REPOSITORY, "repository_id": SOURCE_REPOSITORY_ID,
                "commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "ref": SOURCE_REF,
                "input_mode": "REVIEWED_LOCAL_BUNDLE" if bundle is not None else "PINNED_PUBLIC_SOURCE_STORE",
                "bundle_sha256": BUNDLE_SHA256 if bundle is not None else None,
                "source_metadata_sha256": digest(regular_bytes(source_metadata)) if source_metadata else None,
                "origin_basis": ("REVIEWED_ACQUISITION_PIN_NOT_FRESH_REMOTE_AUTHENTICATION" if bundle is not None else
                    "FIXED_OFFICIAL_ENDPOINT_METADATA_AND_PINNED_OBJECTS; CALLER_AUTHENTICATES_METADATA_ORIGIN"),
                "ancestry_checks": edges, "protected_paths_unchanged": list(PFT_PATHS + CORE_PATHS + D06_PATHS)},
            "consumer": {"repository": CONSUMER_REPOSITORY, "repository_id": CONSUMER_REPOSITORY_ID,
                "commit": expected_commit, "tree": expected_tree,
                "binding_basis": "LOCAL_CHECKOUT_AND_REVIEWED_MIGRATION_MANIFEST",
                "isolation_verification": binding, "source_manifest_sha256": MANIFEST_SHA256,
                "adapter_sha256": digest(regular_bytes(Path(__file__)))},
            "historical_materialization_receipt": {"path": "effective-source/MATERIALIZATION.json",
                "sha256": digest(original), "preserved_unchanged": True},
            "original_seed_identity": {k: seed_pin[k] for k in ("repository", "run", "workflow", "artifact")},
            "network_isolation": json.loads(regular_bytes(stage / "network-isolation.json")),
            "truth_boundaries": {"canonical_recertification": False, "new_producer_run": None,
                "certification_transferred": False, "new_consumer_is_original_descendant": False,
                "historical_seed_package_authenticated_by_this_adapter": False,
                "historical_seed_replayed_by_this_adapter": False,
                "live_network_fallback": False, "production_authority": False}}
        (stage / "HISTORICAL-ADAPTER.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        require(not output.exists() and not output.is_symlink(), "output appeared during verification")
        publish_no_replace(stage, output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--historical-bundle", type=Path)
    inputs.add_argument("--source-object-store", type=Path)
    parser.add_argument("--historical-source-metadata", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-consumer-commit", required=True)
    parser.add_argument("--expected-consumer-tree", required=True)
    args = parser.parse_args()
    try:
        result = materialize(args.consumer, args.historical_bundle, args.output,
                             args.expected_consumer_commit, args.expected_consumer_tree,
                             source_store=args.source_object_store,
                             source_metadata=args.historical_source_metadata)
    except (AdapterError, OSError, KeyError, ValueError) as error:
        print("HISTORICAL_ADAPTER_FAILED: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "consumer": result["consumer"]["commit"],
                      "canonical_recertification": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
