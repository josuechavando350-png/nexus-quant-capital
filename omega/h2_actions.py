"""Branch-scoped physical H2 audit. Evidence is printed to GitHub job logs.

Bounded runtime evidence upload is delegated to the pinned workflow action.
No caches, signing, broadcasts, subscriptions, or live acquisition.
The job token is used only for GETs to the pinned original evidence repository.
Run metadata must be independently read back before accepting these job claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

# sudo removes PYTHONDONTWRITEBYTECODE; protect the checkout before local imports.
sys.dont_write_bytecode = True

from integrity import canonical, digest, load_pinned_python, read_regular, strict_json
from isolation import verify_repository
from pft_source_binding import (DESTINATION, DESTINATION_ID, FALSE_AUTHORITY, SOURCE,
                                SOURCE_COMMIT, build_binding, git, require,
                                verify_checkout_bytes, verify_clean_head)

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "feat/omega-h2-executable-audit-20261022"
WORKFLOW = ".github/workflows/omega-h2-audit.yml"
TX = "0xc953d5da04ee4dc9f421ac5418f05add5244d9816c50420bbf7bb6cbafc1150a"
PARENT = "0x04a2465e3a87b1103521c1f54e568de209062f08742a0212da24d34eee4aac78"
PROVIDERS = (("blastapi-public", "https://eth-mainnet.public.blastapi.io", 0.35),
             ("mevblocker-rpc", "https://rpc.mevblocker.io", 1.25))
RPC_METHODS = frozenset({"eth_chainId", "eth_blockNumber", "eth_getBlockByNumber",
    "eth_getBlockByHash", "eth_getTransactionByHash", "eth_getTransactionReceipt",
    "eth_getCode", "eth_getBalance", "eth_getStorageAt", "eth_getTransactionCount",
    "eth_call", "eth_getProof", "net_version", "web3_clientVersion"})
REPLAY_PATH = "ci/nqc-census/run_rmc006_recertification.py"
REPLAY_BLOB = "a200f6d699df693f4087c6b7dc2c9027898ebba4"
PROXY_PATH = "ci/nqc-protocol-fork/parity/http_rpc_throttle_proxy.py"
PROXY_BLOB = "a4cc2d56bfc1ddce2995543c7c5271d7c734a451"
_EVIDENCE_RECORDS = None


def producer_context(env: dict, head: str, tree: str) -> dict:
    for name, expected in {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": DESTINATION,
        "GITHUB_REPOSITORY_ID": str(DESTINATION_ID),
        "GITHUB_REF": "refs/heads/" + BRANCH, "GITHUB_SHA": head,
        "GITHUB_EVENT_NAME": "push", "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64", "OMEGA_WORKFLOW_SHA": head,
        "OMEGA_WORKFLOW_REF": DESTINATION + "/" + WORKFLOW + "@refs/heads/" + BRANCH,
        "OMEGA_REPOSITORY_VISIBILITY": "public",
    }.items():
        require(env.get(name) == expected, "producer_context_mismatch: " + name)
    require(all(re.fullmatch(r"[0-9a-f]{40}", x) for x in (head, tree)), "invalid_git_identity")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch(r"[1-9][0-9]*", env.get(key, "")) is not None, "invalid_run_identity")
    return {"repository": DESTINATION, "repository_id": DESTINATION_ID,
            "commit": head, "tree": tree, "workflow_path": WORKFLOW,
            "workflow_sha": head, "run_id": int(env["GITHUB_RUN_ID"]),
            "run_attempt": int(env["GITHUB_RUN_ATTEMPT"]),
            "identity_basis": "RUNNER_CONTEXT_PENDING_INDEPENDENT_API_READBACK",
            "artifact_id": None, "canonical_recertification": False}


def rpc_readonly(payload) -> None:
    rows = payload if isinstance(payload, list) else [payload]
    require(bool(rows) and len(rows) <= 32, "rpc_batch_rejected")
    for row in rows:
        require(isinstance(row, dict) and row.get("jsonrpc") == "2.0"
                and isinstance(row.get("method"), str)
                and row["method"] in RPC_METHODS, "rpc_method_rejected")


def proxy() -> None:
    require(os.environ.get("NQC_PFT_UPSTREAM_URL") in {p[1] for p in PROVIDERS},
            "unknown_upstream")
    module = load_pinned_python(ROOT / PROXY_PATH, PROXY_BLOB, "omega_pinned_proxy")
    original_forward = module.forward

    def guarded(raw, payload):
        rpc_readonly(payload)
        return original_forward(raw, payload)

    module.forward = guarded
    with module.ThreadingHTTPServer((module.HOST, module.PORT), module.Handler) as server:
        server.serve_forever()


def namespace_probe(parent: str, source: Path) -> None:
    module = load_pinned_python(ROOT / REPLAY_PATH, REPLAY_BLOB, "omega_pinned_replay")
    proof = module.network_proof(parent)
    before = read_regular(source / "sentinel")
    subprocess.run(["mount", "--bind", str(source), str(source)], check=True)
    subprocess.run(["mount", "-o", "remount,bind,ro", str(source)], check=True)
    require(os.statvfs(source).f_flag & os.ST_RDONLY, "readonly_mount_missing")
    require(read_regular(source / "sentinel") == before, "probe_source_mutated")
    print(json.dumps({**proof, "readonly_bind_mount": True}, sort_keys=True))


def evidence(name: str, value: dict) -> None:
    raw = canonical(value)
    record = {"name": name, "sha256": digest(raw), "value": value}
    if _EVIDENCE_RECORDS is not None:
        _EVIDENCE_RECORDS.append(strict_json(canonical(record)))
    print("OMEGA_H2_EVIDENCE " + json.dumps(record, sort_keys=True), flush=True)


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra:
        env.update(extra)
    return env


def run(args, cwd: Path, timeout=1200, extra=None):
    print("OMEGA_H2_COMMAND " + json.dumps([str(x) for x in args]), flush=True)
    try:
        result = subprocess.run([str(x) for x in args], cwd=cwd, env=clean_env(extra),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        output = error.output or b""
        print(output.decode(errors="replace"), flush=True)
        evidence("command-timeout", {"argv": [str(x) for x in args],
                 "timeout_seconds": timeout, "exit_code": None,
                 "partial_output_sha256": digest(output)})
        raise
    print(result.stdout.decode(errors="replace"), flush=True)
    evidence("command", {"argv": [str(x) for x in args], "exit_code": result.returncode,
                         "output_sha256": digest(result.stdout)})
    require(result.returncode == 0, "command_failed: " + str(args[0]))
    return result.stdout


def observed_replay(source: Path, out: Path, repo: Path, parent: str):
    """Add progress messages around the pinned runner's unchanged assertions."""
    path = repo / REPLAY_PATH
    module = load_pinned_python(path, REPLAY_BLOB, "omega_observed_replay")
    original_run = module.run

    def observed(command, log=None, cwd=None, expected=0):
        started = time.monotonic()
        print("OMEGA_H2_REPLAY_STEP " + json.dumps({"state": "STARTED",
              "argv": [str(x) for x in command], "log": str(log) if log else None}), flush=True)
        result = original_run(command, log=log, cwd=cwd, expected=expected)
        print("OMEGA_H2_REPLAY_STEP " + json.dumps({"state": "VERIFIED",
              "argv": [str(x) for x in command],
              "elapsed_seconds": round(time.monotonic() - started, 3)}), flush=True)
        return result

    module.run = observed
    previous = sys.argv
    try:
        sys.argv = [str(path), "--source", str(source), "--out", str(out),
                    "--repo", str(repo), "--parent-network-namespace", parent]
        module.main()
    finally:
        sys.argv = previous


def download(url: str, target: Path, *, api=False, sha256=None, limit=64*1024*1024):
    require(not target.exists() and url.startswith("https://"), "invalid_download")
    command = ["curl", "-q", "--fail", "--silent", "--show-error", "--location",
               "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "15",
               "--max-time", "180", "--max-filesize", str(limit), "--output", str(target)]
    config = ""
    if api:
        require(url.startswith("https://api.github.com/repos/" + SOURCE + "/"), "api_scope_rejected")
        token = os.environ.get("GH_TOKEN", "")
        # Bearer credentials are opaque; support RFC 6750 b64token characters.
        # Reject CR/LF and curl-config quotes rather than assuming one token prefix.
        require(bool(re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,2}", token)), "invalid_or_missing_job_token")
        command += ["--config", "-", "--header", "Accept: application/vnd.github+json",
                    "--header", "X-GitHub-Api-Version: 2022-11-28"]
        # curl drops Authorization on cross-origin redirects. Never use location-trusted.
        config = 'header = "Authorization: Bearer ' + token + '"\n'
    result = subprocess.run(command + [url], input=config.encode(), env=clean_env(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=190)
    require(result.returncode == 0, "download_failed: " + url + " "
            + result.stderr.decode(errors="replace")[-500:])
    data = read_regular(target, limit=limit)
    require(sha256 is None or digest(data) == sha256, "download_digest_mismatch")
    evidence("download", {"url": url, "bytes": len(data), "sha256": digest(data)})


def rpc(url: str, method: str, params: list):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    rpc_readonly(payload)
    require(url in {p[1] for p in PROVIDERS}, "unknown_upstream")
    # Same ordinary curl transport verified on the user's phone. No proxy/tunnel
    # or credential fallback. Record endpoint and status on failure.
    command = ["curl", "-q", "-sS", "--proto", "=https",
        "--connect-timeout", "10", "--max-time", "30", "--max-filesize", str(2*1024*1024),
        "-H", "Content-Type: application/json", "--data", canonical(payload).decode(),
        "--write-out", "\n%{http_code}", url]
    for attempt in range(4):
        result = subprocess.run(command, env=clean_env(), capture_output=True, timeout=35)
        require(result.returncode == 0, "rpc_transport_failed: " + url + " " + method)
        data, status = result.stdout.rsplit(b"\n", 1)
        if status != b"429" or attempt == 3:
            break
        delay = 2 ** (attempt + 1)
        print("OMEGA_RPC_BACKOFF " + json.dumps({'provider':url,'method':method,
            'http_status':429,'attempt':attempt+1,'wait_seconds':delay}), flush=True)
        time.sleep(delay)
    require(status == b"200", "rpc_http_error: " + url + " " + method + " HTTP "
            + status.decode(errors="replace") + " " + data[:200].decode(errors="replace"))
    require(len(data) <= 2*1024*1024, "rpc_response_too_large")
    answer = strict_json(data)
    require(answer.get("id") == 1 and "error" not in answer and "result" in answer,
            "rpc_error")
    return answer["result"]


def probe_providers():
    reports = []
    for name, url, _ in PROVIDERS:
        try:
            require(rpc(url, "eth_chainId", []) == "0x1", "wrong_chain")
            tx = rpc(url, "eth_getTransactionByHash", [TX])
            require(isinstance(tx, dict) and tx.get("hash") == TX
                    and tx.get("blockNumber") == hex(25252136), "historical_transaction_missing")
            reports.append({"provider": name, "url": url, "status": "PASS",
                            "transaction_hash": TX, "block_number": 25252136})
        except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
            reports.append({"provider": name, "url": url, "status": "BLOCKED", "reason": str(error)})
    evidence("rpc-preflight", {"providers": reports, "canonical_recertification": False})
    require(all(r["status"] == "PASS" for r in reports), "rpc_preflight_blocked")


def compare_forks(left: dict, right: dict, nl: dict, nr: dict) -> dict:
    require(left == right and nl == nr, "provider_dissent")
    def integer(value):
        require(type(value) is int or (type(value) is str and
                re.fullmatch(r"(?:0x[0-9a-fA-F]+|[0-9]+)", value) is not None),
                "invalid_fork_integer")
        parsed = int(value, 0) if isinstance(value, str) and value.startswith("0x") else int(value)
        require(parsed >= 0, "negative_fork_integer")
        return parsed
    required = {"realized_profit", "flash_premium", "pair_amount_out", "ordered_logs_digest",
                "operator_usdc_delta", "pair_reserve0_after", "pair_reserve1_after",
                "executor_runtime_keccak256"}
    require(required <= set(left), "fork_evidence_missing")
    for key in ("flash_premium", "pair_amount_out", "pair_reserve0_after", "pair_reserve1_after"):
        integer(left[key])
    for key in ("ordered_logs_digest", "executor_runtime_keccak256"):
        require(type(left[key]) is str and re.fullmatch(r"0x[0-9a-f]{64}", left[key]) is not None,
                "invalid_fork_digest")
    require(left.get("transaction_hash") == TX and integer(left.get("block_number", 0)) == 25252136
            and left.get("parent_hash") == PARENT and nl.get("transaction_hash") == TX,
            "historical_anchor_mismatch")
    require(integer(left["realized_profit"]) > 0 and
            left["realized_profit"] == left["operator_usdc_delta"], "profit_reconciliation_failed")
    require(integer(nl.get("atomic_rejection_pass", 0)) == 1 and
            integer(nl.get("shortfall_before_gas", 0)) > 0, "negative_case_failed")
    return {"positive": left, "negative": nl, "provider_consensus": True,
            "protocol_fork_truth": "NOT_CLOSED", **{k: False for k in FALSE_AUTHORITY}}


def source_checkout(work: Path) -> Path:
    source = work / "original-source"
    run(["git", "clone", "--no-checkout", "https://github.com/" + SOURCE + ".git", source], work)
    run(["git", "sparse-checkout", "init", "--no-cone"], source)
    (source / ".git/info/sparse-checkout").write_text(
        "/AGENTS.md\n/nqc-census/\n/ci/nqc-build-truth/\n/ci/nqc-census/\n"
        "/ci/nqc-protocol-fork/\n/ci/nqc-t35/\n/ci/nqc-t36/\n/ci/nqc-t37/\n"
        "/.github/workflows/nqc-*.yml\n")
    run(["git", "checkout", "--detach", SOURCE_COMMIT], source)
    run(["git", "fsck", "--full", "--no-reflogs"], source)
    return source


def replay(work: Path, head: str):
    pin = strict_json(read_regular(ROOT / "ci/nqc-census/rmc006-recertification-source.json"))
    api = "https://api.github.com/repos/" + SOURCE
    for name, path in {"run": "/actions/runs/36820687233", "artifact": "/actions/artifacts/11143129177",
                       "commit": "/git/commits/" + pin["run"]["head_sha"]}.items():
        download(api + path, work / (name + ".json"), api=True, limit=2*1024*1024)
    archive = work / "d06.zip"
    download(api + "/actions/artifacts/11143129177/zip", archive, api=True,
             sha256=pin["artifact"]["digest"].removeprefix("sha256:"), limit=16*1024*1024)
    seed = work / "authenticated-seed"
    run([sys.executable, ROOT / "ci/nqc-census/verify_rmc006_recertification_source.py",
         "--archive", archive, "--run-metadata", work / "run.json", "--artifact-metadata",
         work / "artifact.json", "--commit-metadata", work / "commit.json",
         "--provenance", work / "provenance.json", "--extract-to", seed], ROOT)
    # The unchanged historical runner expects target/release inside its checkout.
    # Build in a disposable exact-commit clone; keep the producer checkout pristine.
    build = work / "replay-checkout"
    run(["git", "clone", "--no-local", str(ROOT), build], work)
    run(["git", "checkout", "--detach", head], build)
    verify_clean_head(build, head)
    cargo = build / "nqc-census"
    run(["cargo", "+1.98.1", "fetch", "--locked"], cargo)
    run(["cargo", "+1.98.1", "test", "--workspace", "--all-targets", "--locked", "--offline"], cargo)
    run(["cargo", "+1.98.1", "build", "--workspace", "--bins", "--release", "--locked", "--offline"], cargo)
    # Add one Omega example to a disposable copy using its unchanged lockfile.
    # Remove it before the original clean-tree and replay gates.
    from rust_store_intake import EXAMPLE, read_bridge_source
    example = build / EXAMPLE
    require(example.parent.is_dir() and not example.exists(), 'bridge_example_destination')
    try:
        with example.open('xb') as f: f.write(read_bridge_source(ROOT))
        run(["cargo", "+1.98.1", "build", "-p", "nqc-census-store", "--example",
             "nqc_omega_bridge", "--release", "--locked", "--offline"], cargo)
    finally:
        example.unlink(missing_ok=True)
    verify_checkout_bytes(build, head)
    out = work / "replay-result"
    parent = os.readlink("/proc/self/ns/net")
    # The historical replay exceeded the generic 20-minute process budget.
    # Preserve provider pacing and all crash cases; bound the root process group
    # to 50 minutes within the existing 60-minute job.
    run(["sudo", "-n", "timeout", "--signal=TERM", "--kill-after=30", "3000",
         "unshare", "--net", "--mount", "--", sys.executable, "-B",
         ROOT / "omega/h2_actions.py", "--replay-worker", "--source", seed,
         "--out", out, "--repo", build, "--parent", parent], work, timeout=3060)
    verify_checkout_bytes(build, head)
    report = strict_json(read_regular(out / "offline-verification.json"))
    require(report["code_commit"] == head, "replay_producer_mismatch")
    evidence("network-isolation", strict_json(read_regular(out / "network-isolation.json")))
    evidence("disconnected-replay", report)
    from rust_store_intake import verify_report
    transport = strict_json(read_regular(work / "rust-store-bridge/report.json"))
    verify_report(transport)
    evidence("rust-store-bridge", transport)
    from dependency_intake import verify_report as verify_dependency_report
    dependent = strict_json(read_regular(work / "dependency-store-bridge/report.json"))
    verify_dependency_report(dependent)
    evidence("dependency-store-bridge", dependent)
    return report


def prepare_harness(effective: Path, work: Path) -> tuple[Path, Path]:
    harness = work / "historical/contracts"
    outputs = work / "historical/evidence"
    (harness / "src").mkdir(parents=True)
    (harness / "test").mkdir()
    outputs.mkdir()
    shutil.copyfile(effective / "contracts/src/NqcAaveV3Executor.sol", harness / "src/NqcAaveV3Executor.sol")
    shutil.copyfile(ROOT / "ci/nqc-protocol-fork/parity/PftAaveExecutorHistoricalFork.t.sol",
                    harness / "test/PftAaveExecutorHistoricalFork.t.sol")
    (harness / "foundry.toml").write_text('[profile.default]\nsrc = "src"\ntest = "test"\n'
        'solc_version = "0.8.24"\noptimizer = true\noptimizer_runs = 200\n'
        'fs_permissions = [{ access = "read-write", path = "../evidence" }]\n')
    return harness, outputs


def forks(work: Path, source: Path, head: str):
    probe_providers()
    prior = work / "reference"
    run([sys.executable, source / "ci/nqc-census/materialize_effective_source.py", "--output", prior], source)
    bound = work / "bound"
    binding = build_binding(ROOT, source, prior / "MATERIALIZATION.json", bound, head)
    evidence("source-binding", binding)
    effective = bound / "effective/recovered-source"
    run(["cargo", "+1.98.1", "fetch", "--locked"], effective)
    run(["cargo", "+1.98.1", "test", "--workspace", "--all-targets", "--locked", "--offline"], effective)
    binaries = work / "foundry"
    binaries.mkdir()
    archive = work / "foundry.tar.gz"
    download("https://github.com/foundry-rs/foundry/releases/download/v1.7.1/foundry_v1.7.1_linux_amd64.tar.gz",
             archive, sha256="cf7e688ed0c4c48adffca788b496076e31060b67ac5afe1e43dbb5499c20c88b",
             limit=128*1024*1024)
    run(["tar", "-xzf", archive, "-C", binaries, "forge"], work)
    forge = binaries / "forge"
    solc = work / "solc-0.8.24"
    download("https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.8.24+commit.e11b9ed9",
             solc, sha256="fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f")
    solc.chmod(0o755)
    run([forge, "--version"], work)
    run([solc, "--version"], work)
    run([forge, "test", "--offline", "--use", solc, "--fuzz-seed", "0x39", "-vvv"], effective / "contracts")
    harness, outputs = prepare_harness(effective, work)
    run([forge, "build", "--force", "--offline", "--use", solc], harness)
    reports = []
    for index, (name, url, interval) in enumerate(PROVIDERS):
        port = 18581 + index
        output = outputs / (name + ".json")
        env = clean_env({"NQC_PFT_PROXY_PORT": str(port), "NQC_PFT_UPSTREAM_URL": url,
            "NQC_PFT_UPSTREAM_ID": name, "NQC_PFT_MIN_INTERVAL_SECONDS": str(interval),
            "NQC_PFT_MAX_ATTEMPTS": "12", "NQC_PFT_UPSTREAM_TIMEOUT_SECONDS": "60",
            "NQC_PFT_PROXY_LOG": str(outputs / (name + "-proxy.jsonl"))})
        with (outputs / (name + "-proxy.log")).open("wb") as proxy_log:
            child = subprocess.Popen([sys.executable, str(ROOT / "omega/h2_actions.py"), "--rpc-proxy"],
                                      env=env, stdout=proxy_log, stderr=subprocess.STDOUT)
            try:
                ready = False
                for _ in range(100):
                    require(child.poll() is None, "proxy_exited")
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                            ready = response.status == 200
                    except OSError:
                        time.sleep(0.1)
                    if ready:
                        break
                require(ready, "proxy_not_ready")
                log = run([forge, "test", "--offline", "--use", solc, "--match-contract",
                    "PftAaveExecutorHistoricalForkTest", "-vvvv"], harness,
                    extra={"PFT_RPC_URL": f"http://127.0.0.1:{port}", "PFT_EVIDENCE_PATH": str(output)})
                for test in ("testFork_ExecutorSettlesHistoricalWethUsdcLiquidation()",
                             "testFork_ExecutorRejectsOriginalUnprofitableRouteAtomically()"):
                    require(("[PASS] " + test).encode() in log, "fork_test_missing")
                positive = strict_json(read_regular(output))
                negative = strict_json(read_regular(Path(str(output) + ".negative.json")))
                reports.append((positive, negative))
                evidence(name, {"positive": positive, "negative": negative})
            finally:
                child.terminate()
                child.wait(timeout=10)
    report = compare_forks(reports[0][0], reports[1][0], reports[0][1], reports[1][1])
    evidence("historical-forks", report)
    return report


def main():
    global _EVIDENCE_RECORDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("forks", "replay"))
    parser.add_argument("--rpc-proxy", action="store_true")
    parser.add_argument("--namespace-probe", action="store_true")
    parser.add_argument("--replay-worker", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--parent")
    parser.add_argument("--probe-source", type=Path)
    args = parser.parse_args()
    if args.replay_worker:
        require(all((args.source, args.out, args.repo, args.parent)), "replay_arguments_required")
        from rust_store_intake import exercise
        module = load_pinned_python(ROOT / REPLAY_PATH, REPLAY_BLOB, "omega_bridge_network")
        exercise(args.out.parent / "rust-store-bridge",
                 args.repo / "nqc-census/target/release/examples/nqc_omega_bridge",
                 args.repo / "nqc-census/target/release/nqc-census-store-verify",
                 module.network_proof(args.parent))
        from dependency_intake import exercise as exercise_dependencies
        exercise_dependencies(args.out.parent / "dependency-store-bridge",
                 args.repo / "nqc-census/target/release/examples/nqc_omega_bridge",
                 args.repo / "nqc-census/target/release/nqc-census-store-verify",
                 module.network_proof(args.parent))
        observed_replay(args.source, args.out, args.repo, args.parent)
        return
    if args.rpc_proxy:
        proxy()
        return
    if args.namespace_probe:
        namespace_probe(args.parent, args.probe_source)
        return
    require(args.stage in ("forks", "replay"), "stage_required")
    head = os.environ.get("GITHUB_SHA", "")
    tree = verify_clean_head(ROOT, head)
    verify_checkout_bytes(ROOT, head)
    require((ROOT / WORKFLOW).is_file(), "active_workflow_missing")
    identity = producer_context(os.environ, head, tree)
    _EVIDENCE_RECORDS = []
    evidence("producer", identity)
    work = Path(tempfile.mkdtemp(prefix="omega-h2-", dir=os.environ["RUNNER_TEMP"]))
    probe_source = work / "probe-source"
    probe_source.mkdir()
    (probe_source / "sentinel").write_text("immutable namespace probe\n")
    parent = os.readlink("/proc/self/ns/net")
    run(["sudo", "-n", "unshare", "--net", "--mount", "--", sys.executable,
         "-B", ROOT / "omega/h2_actions.py", "--namespace-probe", "--parent", parent,
         "--probe-source", probe_source], work, timeout=30)
    source = source_checkout(work)
    evidence("isolation-before", verify_repository(ROOT, source))
    run([sys.executable, ROOT / "omega/regression.py", "--start-directory", ROOT / "omega",
         "--pattern", "test_h2_actions.py", "--report", work / "runner-tests.json"], ROOT)
    evidence("runner-unit-tests", strict_json(read_regular(work / "runner-tests.json")))
    run([sys.executable, ROOT / "omega/regression.py", "--start-directory", ROOT / "omega",
         "--pattern", "test_ci_evidence.py", "--report", work / "capture-tests.json"], ROOT)
    evidence("ci-capture-tests", strict_json(read_regular(work / "capture-tests.json")))
    run([sys.executable, ROOT / "omega/ci_evidence.py"], ROOT)
    for name, pattern in (
        ("historical-intake-tests", "test*intake.py"),
        ("evidence-store-tests", "test_evidence_store.py"),
        ("historical-pipeline-tests", "test_historical_pipeline.py"),
        ("runtime-artifact-tests", "test_runtime_artifact.py"),
    ):
        report_path = work / (name + ".json")
        run([sys.executable, ROOT / "omega/regression.py", "--start-directory", ROOT / "omega",
             "--pattern", pattern, "--report", report_path], ROOT)
        evidence(name, strict_json(read_regular(report_path)))
    pipeline = work / "historical-pipeline"
    run([sys.executable, ROOT / "omega/historical_pipeline.py", "--output-directory", pipeline], ROOT)
    run([sys.executable, ROOT / "omega/historical_pipeline.py", "--output-directory", pipeline,
         "--verify"], ROOT)
    evidence("historical-pipeline", strict_json(read_regular(pipeline / "report.json")))
    run(["rustup", "toolchain", "install", "1.98.1", "--profile", "minimal"], work)
    result = replay(work, head) if args.stage == "replay" else forks(work, source, head)
    verify_clean_head(ROOT, head)
    verify_checkout_bytes(ROOT, head)
    evidence("isolation-after", verify_repository(ROOT, source))
    evidence("stage-complete", {"stage": args.stage, "status": "PHYSICAL_GATE_PASS",
             "producer": identity, "result_sha256": digest(canonical(result)),
             "certified_components": 0, **{k: False for k in FALSE_AUTHORITY}})
    from runtime_artifact import write_packet
    packet_dir = Path(os.environ["RUNNER_TEMP"]) / ("omega-evidence-" + args.stage)
    commitment = write_packet(packet_dir, identity, args.stage, _EVIDENCE_RECORDS)
    print("OMEGA_RUNTIME_PACKET " + json.dumps({"sha256": commitment, "stage": args.stage}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("OMEGA_H2_FAILED " + json.dumps({"reason": str(error),
              **{k: False for k in FALSE_AUTHORITY}}, sort_keys=True), flush=True)
        sys.exit(1)
