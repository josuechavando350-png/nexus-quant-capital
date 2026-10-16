"""Read-only, necessary-condition preflight; never installs or imports JS packages.

A successful inventory is NOT a build, bundler execution or admission proof.
The search is limited to the explicit directories in the recorded command.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

PIN = "1868538f1d7678576291d2ecabb4443c797ad133"
SELECTORS = {
    "ethers": "^5.7.0",
    "@ethersproject/properties": "^5.7.0",
    "@ethersproject/providers": "^5.7.0",
    "debug": "^4.3.4",
    "async-mutex": "^0.4.0",
}
WORKSPACES = ("validation-manager", "utils", "sdk")
SOURCE_FILES = (
    "yarn.lock", "package.json", "packages/bundler/package.json",
    *(f"packages/{p}/package.json" for p in WORKSPACES),
    "packages/validation-manager/src/ValidationManager.ts",
    "packages/validation-manager/src/TracerResultParser.ts",
    "packages/bundler/src/modules/ExecutionManager.ts",
    "packages/bundler/src/modules/DepositManager.ts",
    "packages/bundler/src/modules/MempoolManager.ts",
    "packages/bundler/src/modules/ReputationManager.ts",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locked_version(lock, name, selector):
    """Only parse simple Yarn-v1 selector/version records; fail on ambiguity."""
    target = f"{name}@{selector}"
    versions = []
    for block in re.split(r"\n\s*\n", lock):
        lines = block.splitlines()
        if not lines or not lines[0].endswith(":"):
            continue
        selectors = [s.strip().strip('"') for s in lines[0][:-1].split(", ")]
        if target in selectors:
            matches = re.findall(r'^  version "([^"\n]+)"$', block, re.M)
            if len(matches) != 1:
                raise ValueError(f"missing or ambiguous locked version: {target}")
            versions.append(matches[0])
    if len(versions) != 1:
        raise ValueError(f"missing or duplicate selector: {target}")
    return versions[0]


def inspect_package(directory, name, version):
    manifest = directory / "package.json"
    if not manifest.is_file():
        return {"path": str(directory), "status": "ABSENT"}
    result = {"path": str(directory), "manifest_sha256": digest(manifest)}
    try:
        data = json.loads(manifest.read_text())
        if not isinstance(data, dict):
            raise ValueError("manifest must be an object")
        result.update(name=data.get("name"), version=data.get("version"))
        if data.get("name") != name or data.get("version") != version:
            return dict(result, status="NAME_OR_VERSION_MISMATCH")
        main = data.get("main", "index.js")
        if not isinstance(main, str) or not main:
            raise ValueError("invalid main")
        entry = (directory / main).resolve()
        if not entry.is_relative_to(directory.resolve()):
            return dict(result, status="ENTRY_OUTSIDE_PACKAGE")
        result["main"] = main
        if not entry.is_file():
            return dict(result, status="ENTRY_MISSING")
        return dict(result, status="NECESSARY_FILES_PRESENT", entry_sha256=digest(entry))
    except (ValueError, OSError, TypeError):
        return dict(result, status="UNREADABLE_MANIFEST_OR_ENTRY")


def candidates(name, node_modules, caches):
    paths = [p / name for p in node_modules]
    prefix = "npm-" + name.replace("/", "-") + "-"
    for cache in caches:
        if cache.is_dir():
            paths.extend(p / "node_modules" / name for p in sorted(cache.iterdir())
                         if p.name.startswith(prefix) and p.is_dir())
    return list(dict.fromkeys(paths))


def inventory(checkout, node_modules, caches, observed_head):
    if observed_head != PIN:
        raise ValueError("checkout is not the pinned v0.7 commit")
    lock = (checkout / "yarn.lock").read_text()
    sources = {p: digest(checkout / p) for p in SOURCE_FILES}
    packages = {}
    for name, selector in SELECTORS.items():
        version = locked_version(lock, name, selector)
        found = [inspect_package(p, name, version)
                 for p in candidates(name, node_modules, caches)]
        packages[name] = {"locked_version": version, "selector": selector,
                          "candidates": found,
                          "necessary_files_found": any(
                              c["status"] == "NECESSARY_FILES_PRESENT" for c in found)}
    workspaces = {
        name: inspect_package(checkout / "packages" / name,
                              "@account-abstraction/" + name, "0.7.0")
        for name in WORKSPACES
    }
    blocked = [name for name, p in packages.items() if not p["necessary_files_found"]]
    blocked += ["workspace:" + name for name, p in workspaces.items()
                if p["status"] != "NECESSARY_FILES_PRESENT"]
    return {
        "schema": 1, "bundler_commit": observed_head, "checkout": str(checkout),
        "node_modules_searched": [str(p) for p in node_modules],
        "yarn_caches_searched": [str(p) for p in caches],
        "source_sha256": sources, "packages": packages, "workspaces": workspaces,
        "missing_necessary_components": blocked,
        "status": "BLOCKED_PREREQUISITES" if blocked else "REQUIRES_BUILD_AND_RUNTIME_VALIDATION",
        "scope": "Necessary files only; not exhaustive transitive dependency, integrity, Node resolution or compatibility validation.",
        "bundler_executed": False, "full_admission_proven": False,
        "network_requests": 0, "installations": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--node-modules", action="append", default=[], type=Path)
    parser.add_argument("--yarn-cache", action="append", default=[], type=Path)
    args = parser.parse_args()
    head = subprocess.check_output(
        ["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True).strip()
    # Verify source bytes against the pinned commit; a clean HEAD alone is insufficient.
    for path in SOURCE_FILES:
        original = subprocess.check_output(
            ["git", "-C", str(args.checkout), "show", f"{PIN}:{path}"])
        if original != (args.checkout / path).read_bytes():
            raise ValueError(f"source differs from pinned commit: {path}")
    report = inventory(args.checkout, args.node_modules, args.yarn_cache, head)
    report["observed_utc"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, indent=2) + "\n", end="")
    return 1 if report["missing_necessary_components"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
