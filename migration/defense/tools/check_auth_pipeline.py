"""Reproducible local auth evaluation with declared synthetic labels and measured costs."""
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import tracemalloc
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.codec import canonical
from nqc_defense.managed_integrity import ManagedIntegrity
from nqc_defense.operations import OperationsStore


def event(t, outcome="failure", principal="alice", address="192.0.2.1"):
    return canonical({"schema": "nqc-auth-log-v1", "time_ns": t * 1000000000,
                      "outcome": outcome, "principal": principal, "remote_address": address}) + b"\n"


def run():
    # Labels encode invented scenario context. They do not establish real attacker ground truth.
    scenarios = [
        ("routine_success", False, [event(i, "success") for i in range(5)]),
        ("single_typo_then_success", False, [event(0), event(1, "success")]),
        ("two_failures", False, [event(0), event(1)]),
        ("burst_requiring_review", True, [event(i) for i in range(3)]),
        ("burst_then_success_requiring_review", True, [event(i) for i in range(3)] + [event(3, "success")]),
        ("sustained_burst_requiring_review", True, [event(i) for i in range(12)]),
        ("benign_repeated_password_typo", False, [event(i) for i in range(4)]),
        ("distributed_failures_requiring_review", True, [event(i, address=f"192.0.2.{i+1}") for i in range(4)]),
        ("spaced_benign_failures", False, [event(i * 100) for i in range(4)]),
    ]
    confusion = {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0}
    results = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for index, (name, label, lines) in enumerate(scenarios):
            log = root / f"scenario-{index}.jsonl"; log.write_bytes(b"".join(lines))
            store = OperationsStore.create(root / f"store-{index}")
            monitor = AuthLogMonitor.register(store, "auth", "evaluation", "host", root, log.name, 3, 60)
            monitor.poll()
            predicted = bool(store.cases("evaluation", "host"))
            bucket = ("true_" if predicted == label else "false_") + ("positive" if predicted else "negative")
            confusion[bucket] += 1
            results.append({"scenario": name, "synthetic_review_label": label, "case_opened": predicted})
        store = OperationsStore.create(root / "integrated")
        log = root / "integrated.jsonl"; log.write_bytes(event(1) + event(2))
        monitor = AuthLogMonitor.register(store, "auth", "evaluation", "host", root, log.name, 3, 60)
        assert monitor.poll(max_records=1)["records_committed"] == 1
        log.rename(root / "previous.jsonl"); log.write_bytes(event(3))
        assert monitor.poll("previous.jsonl")["records_committed"] == 1
        monitor.rotate("previous.jsonl")
        reopened = AuthLogMonitor(OperationsStore(store.root), "auth", monitor.digest)
        assert reopened.poll()["cases_opened"] == 1
        assert reopened.poll()["records_committed"] == 0
        source = root / "config.json"; source.write_bytes(b'{"enabled":true}')
        managed = ManagedIntegrity.create(source, root / "managed")
        (managed.root / "assets/artifact.json").write_bytes(b"{}")
        managed.inspect(); store.capture_managed(managed, "evaluation", "host")
        assert len(store.cases("evaluation", "host")) == 2
        managed.recover(); store.capture_managed(managed, "evaluation", "host")
        assert len(store.cases("evaluation", "host")) == 2
        assert source.read_bytes() == b'{"enabled":true}'
        benchmark_log = root / "benchmark.jsonl"
        benchmark_log.write_bytes(b"".join(event(i, "success") for i in range(500)))
        benchmark_store = OperationsStore.create(root / "benchmark")
        benchmark = AuthLogMonitor.register(benchmark_store, "auth", "evaluation", "host", root, benchmark_log.name)
        tracemalloc.start(); wall_start = time.perf_counter_ns(); cpu_start = time.process_time_ns()
        observed = benchmark.poll()
        cpu_ns = time.process_time_ns() - cpu_start; wall_ns = time.perf_counter_ns() - wall_start
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        assert observed["records_committed"] == 500
        return {"verified": True, "rule": "auth_failure_burst_v1", "threshold": 3, "window_seconds": 60,
                "evaluation_kind": "nine synthetic scenarios with declared review labels; not independent or production validation",
                "scenarios": results, "confusion_matrix": confusion,
                "precision_on_synthetic_scenarios": confusion["true_positive"] / (confusion["true_positive"] + confusion["false_positive"]),
                "recall_on_synthetic_scenarios": confusion["true_positive"] / (confusion["true_positive"] + confusion["false_negative"]),
                "known_false_positive": "benign repeated errors can open a case",
                "known_false_negative": "failures spread across addresses do not meet the same-address rule",
                "integration": {"rotation_drained": True, "restart_without_duplicate": True,
                "auth_and_integrity_cases_in_shared_view": True, "recovered_source_status_imported": True,
                "cross_source_causality_claimed": False, "automatic_auth_response": False},
                "local_measurement": {"python": platform.python_version(), "records": 500,
                "input_bytes": benchmark_log.stat().st_size, "wall_ns": wall_ns, "cpu_ns": cpu_ns,
                "python_traced_peak_bytes": peak, "database_bytes_after_commit": benchmark_store.path.stat().st_size,
                "runs": 1, "tracing_enabled": True, "production_slo_or_competitor_comparison": False}}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
