#!/usr/bin/env python3
"""Verify one reviewed standalone producer composition, without new authority.

The caller must supply the externally reviewed exact consumer commit/tree. The
composition manifest is bound to that commit, not an independent certificate.
The original 645-file snapshot/verifier remain unchanged; exact additions are
verified separately. Only the one pinned workflow and fixed seed ZIP are allowed.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile

spec = importlib.util.spec_from_file_location("historical_authority", Path(__file__).with_name("materialize_historical_source.py"))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
WORKFLOW = ".github/workflows/nqc-d06-standalone.yml"
INERT_WORKFLOW = "migration/nqc-d06-standalone.yml.disabled"
WORKFLOW_SHA256 = "9ed8ae584e7bfe80ce86fba2a32f97899fb2969f72802af0db3febd1c0f6ac0d"
ZIP_PATH = "migration/evidence/d06/original-evidence.zip"
ZIP_SHA256 = "1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4"
ZIP_BYTES = 6709740
CONTRACT = "migration/standalone-composition.json"
BASE_METADATA = {'.gitignore': '9c42a9ecdcce4dfd6e999337c98de0f29ae4d3d68c49737e43a39090336a5fc8', 'AGENTS.md': 'fb2f2dbdfd655eb425e28dda0491519bcd1f7747c8c3299e9b7b96c7a6789e99', 'README.md': 'c46590f3bc43239ed749688e6a302128daec2921c6f999ccf3703609df6c3a99', 'migration/IMPORT-PLAN.md': 'be2002638339181eca99cf67248663bdb155193f0bbe906b50eb5d22a1861771', 'migration/VALIDATION.md': '000ab16c6ad9465bbeee8e47f7e3708c6339b4b9a4f98aadacbae8cf02310f02', 'migration/source-manifest.json': '07c126f5ccaba1d05d22e4adf964d57f59707d158ce76856ed92badec83a9b67', 'migration/test_isolation.py': '8db02f36a70e56dd78cc4aa51c0b5ed215f58f897f247374e57172ca2504e356', 'migration/verify_isolation.py': '5a590e40aa6079ca2a2dd14c69b4e1c6304e26de1afc3f484e6b02cfa5820fa9'}
ADDITIONS = {
    "migration/HISTORICAL-ADAPTER.md", "migration/materialize_historical_source.py",
    "migration/test_historical_source_adapter.py", "migration/acquire_historical_source.py",
    "migration/verify_standalone_composition.py", "migration/test_standalone_composition.py",
    "migration/collect_original_metadata.py", "migration/index_standalone_d06.py",
    "migration/run_standalone_d06_offline.sh", "migration/test_standalone_d06.py", ZIP_PATH, WORKFLOW,
}


def verify(root, source_git, expected_commit, expected_tree, require_active=False):
    root, source_git = Path(root).absolute(), Path(source_git).absolute()
    a.require(root.resolve() == root and source_git.resolve() == source_git, "composition path aliases")
    with tempfile.TemporaryDirectory(prefix="nqc-composition-") as name:
        work = Path(name); env = a.environment(work)
        a.verify_consumer_git_config(root, env)
        a.verify_consumer_git_config(source_git, env)
        a.require(a.identity(root, env) == (expected_commit, expected_tree), "composition consumer identity changed")
        a.require(all(x.startswith("H ") for x in a.git(root, "ls-files", "-v", env=env).decode().splitlines()),
                  "composition consumer index hides worktree files")
        a.require(not a.git(root, "status", "--porcelain=v1", "--untracked-files=all", env=env).strip(),
                  "composition checkout is not clean")
        raw = a.regular_bytes(root / CONTRACT)
        a.require(raw == a.git(root, "show", expected_commit + ":" + CONTRACT, env=env),
                  "composition manifest not bound to reviewed consumer commit")
        contract = json.loads(raw)
        a.require(set(contract) == {"schema", "baseline_commit", "baseline_tree", "repository_id", "files"},
                  "composition manifest fields")
        a.require(contract["schema"] == "nqc-reviewed-standalone-composition-v1" and
                  contract["baseline_commit"] == "16e352225ba8a6a931834c4edf3d86d9a2924b7d" and
                  contract["baseline_tree"] == "d9b498f784db19aed4436b0f46ceb4e05766cb6c" and
                  type(contract["repository_id"]) is int and contract["repository_id"] == a.CONSUMER_REPOSITORY_ID,
                  "composition baseline/repository identity changed")
        a.require(set(contract["files"]) == ADDITIONS, "composition addition allowlist changed")
        for path, sha in BASE_METADATA.items():
            a.require(a.digest(a.regular_bytes(root / path)) == sha, "original migration metadata changed: " + path)
        source = json.loads(a.regular_bytes(root / "migration/source-manifest.json"))
        baseline = set(BASE_METADATA) | {item["destination_path"] for item in source["files"]}
        a.require(len(baseline) == 645, "composition baseline membership changed")
        active, inert = (root / WORKFLOW).exists(), (root / INERT_WORKFLOW).exists()
        a.require(active != inert, "exactly one active or inert reviewed workflow is required")
        a.require(not require_active or active, "active reviewed workflow is required by CI")
        actual_workflow = WORKFLOW if active else INERT_WORKFLOW
        additions = (ADDITIONS - {WORKFLOW}) | {actual_workflow}
        expected_files = baseline | additions | {CONTRACT}
        entries = a.tree_entries(root, expected_commit, (".",), env)
        a.require({path for path, _, _ in entries} == expected_files, "unexpected/missing tracked composition payload")
        modes = {path: mode for path, mode, _ in entries}
        for canonical, item in contract["files"].items():
            a.require(set(item) == {"sha256", "bytes", "mode"}, "composition addition fields")
            path = actual_workflow if canonical == WORKFLOW else canonical
            data = a.regular_bytes(root / path)
            mode = "100755" if (root / path).stat().st_mode & stat.S_IXUSR else "100644"
            a.require(mode == modes[path] == item["mode"] and len(data) == item["bytes"] and
                      a.digest(data) == item["sha256"], "composition addition content changed: " + path)
        workflow = a.regular_bytes(root / actual_workflow)
        a.require(a.digest(workflow) == WORKFLOW_SHA256, "reviewed workflow bytes changed")
        archive = a.regular_bytes(root / ZIP_PATH)
        a.require(len(archive) == ZIP_BYTES and a.digest(archive) == ZIP_SHA256, "original seed ZIP changed")
        for path in root.rglob("*"):
            rel = path.relative_to(root)
            if rel.parts[0] == ".git":
                continue
            a.require(not path.is_symlink(), "composition symlink rejected")
            if path.is_file():
                a.require(rel.as_posix() in expected_files, "unexpected/untracked composition payload")
        # The projection is exhaustive for the frozen baseline, never a selective
        # filter over NQC. New additions were independently validated above.
        projection = work / "frozen-baseline"; projection.mkdir()
        for path in sorted(baseline):
            destination = projection / path; destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / path, destination)
            destination.chmod(0o755 if modes[path] == "100755" else 0o644)
        result = json.loads(a.run([sys.executable, "-I", "-B", projection / "migration/verify_isolation.py",
                                  "--root", projection, "--source-git", source_git], cwd=projection, env=env))
        a.require(result["status"] == "ISOLATED_SOURCE_IDENTITY_PASS", "original baseline verification failed")
        return {"status": "STANDALONE_COMPOSITION_PASS", "consumer_commit": expected_commit,
                "consumer_tree": expected_tree, "baseline_files": 645, "addition_files": len(additions),
                "active_workflows": int(active), "workflow_sha256": WORKFLOW_SHA256,
                "original_verifier_sha256": a.VERIFIER_SHA256, "original_verifier_unchanged": True,
                "source_files": result["source_files"], "disabled_workflows": result["disabled_workflows"],
                "original_objects_checked": True, "canonical_recertification": False,
                "contract_authority": "BOUND_TO_EXTERNALLY_REVIEWED_CONSUMER_COMMIT_NOT_SELF_CERTIFYING"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-git", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--require-active-workflow", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(args.root, args.source_git, args.expected_commit, args.expected_tree, args.require_active_workflow)
    except (a.AdapterError, OSError, ValueError, KeyError) as error:
        print("STANDALONE_COMPOSITION_FAILED: " + str(error), file=sys.stderr); return 1
    print(json.dumps(report, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
