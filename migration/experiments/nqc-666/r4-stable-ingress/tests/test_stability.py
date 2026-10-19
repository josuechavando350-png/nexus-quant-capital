import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT.parent / "r3-state-evidence"
sys.path[:0] = [str(ROOT / "python"), str(R3 / "src"), str(R3 / "scripts")]
from fixtures import encode, make_case, policy_from
from native_math import NativeMath
from stable_gateway import StableGateway
from state_evidence import Rejected


class Clock:
    def __init__(self): self.now = 1_000_000_000
    def __call__(self): return self.now


class StabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library = Path(os.environ["NQC_NATIVE_LIB"])
        cls.math = NativeMath(library, hashlib.sha256(library.read_bytes()).hexdigest())
        cls.packet, cls.policy, cls.words = make_case(666301)
        cls.raw = encode(cls.packet)
        cls.now = cls.policy.anchor.timestamp

    def gateway(self, **kw): return StableGateway(self.policy, kw.pop("math", self.math), **kw)

    def test_native_library_pin_and_arguments(self):
        with self.assertRaises(Rejected): NativeMath(os.environ["NQC_NATIVE_LIB"], "0" * 64)
        for args in ([], [0] * 5, [0] * 7, [True] * 6, [-1] * 6, [2**256] * 6, [2**128] * 6):
            with self.subTest(args=args):
                with self.assertRaises(Rejected): self.math.health(args)

    def test_all_proof_corpus_integrates_with_native_math(self):
        for row in json.loads((R3 / "fixtures/synthetic-index.json").read_text()):
            policy = policy_from(row["policy"])
            g = StableGateway(policy, self.math)
            now = policy.anchor.timestamp
            ticket = g.ingest((R3 / "fixtures" / row["packet"]).read_bytes(), now)
            f = g.facts(ticket, now)
            self.assertEqual(f.values(), row["words"])
            for price in (10**34, 10**36, 10**38):
                s = g.scenario(ticket, now, price)
                self.assertEqual(s.eligible_if_assumptions_hold, s.debt > s.capacity)
                self.assertFalse(s.commercial_admission)
            self.assertIsNone(g.authorize(ticket, now)["observed_candidate"])

    def test_foreign_and_copied_tickets_rejected(self):
        a, b = self.gateway(), self.gateway()
        ta, tb = a.ingest(self.raw, self.now), b.ingest(self.raw, self.now)
        with self.assertRaises(Rejected): b.facts(ta, self.now)
        with self.assertRaises(Rejected): b.facts(tb, self.now)
        with self.assertRaises(Rejected): a.facts(copy.copy(ta), self.now)

    def test_invalid_evidence_clears_ticket(self):
        for raw in (b"{}", self.raw[:-1], self.raw.replace(b'"0x1"', b'"0x2"', 1)):
            g = self.gateway()
            t = g.ingest(self.raw, self.now)
            with self.assertRaises(Rejected): g.ingest(raw, self.now)
            with self.assertRaises(Rejected): g.authorize(t, self.now)

    def test_reorg_reset_and_epoch(self):
        g = self.gateway()
        a = g.ingest(self.raw, self.now)
        b = g.ingest(self.raw, self.now)
        self.assertGreater(b.epoch, a.epoch)
        g.reset(replace(self.policy, anchor=replace(self.policy.anchor, block_hash=b"\1" * 32)))
        with self.assertRaises(Rejected): g.facts(b, self.now)
        with self.assertRaises(Rejected): g.ingest(self.raw, self.now)

    def test_frozen_wall_clock_does_not_freeze_expiry(self):
        clock = Clock()
        g = self.gateway(clock=clock)
        t = g.ingest(self.raw, self.now)
        clock.now += 31 * 10**9
        with self.assertRaisesRegex(Rejected, "monotonic snapshot expiry"): g.facts(t, self.now)

    def test_ingest_duration_over_budget_rejected_without_hiding_latency(self):
        values = iter((1, 51_000_002))
        g = self.gateway(clock=lambda: next(values))
        with self.assertRaisesRegex(Rejected, "ingress processing deadline"): g.ingest(self.raw, self.now)
        self.assertIsNone(g._facts)

    def test_ingest_expired_during_verification(self):
        values = iter((1, 2_000_000_001))
        g = StableGateway(replace(self.policy, max_age_s=1), self.math,
                          clock=lambda: next(values), max_ingest_ns=3_000_000_000)
        with self.assertRaisesRegex(Rejected, "expired during verification"): g.ingest(self.raw, self.now)

    def test_clock_failure_drops_state(self):
        clock = Clock()
        g = self.gateway(clock=clock)
        t = g.ingest(self.raw, self.now)
        clock.now -= 1
        with self.assertRaises(Rejected): g.facts(t, self.now)
        self.assertIsNone(g._facts)

    def test_delayed_calculation_result_rejected(self):
        clock = Clock()
        class Delayed:
            def health(_, args):
                clock.now += 5_000_001
                return (2, 1, True)
        g = self.gateway(clock=clock, math=Delayed())
        t = g.ingest(self.raw, self.now)
        with self.assertRaisesRegex(Rejected, "scenario processing deadline"): g.scenario(t, self.now, 10**36)
        self.assertIsNone(g._facts)

    def test_expiry_after_calculation_rejected(self):
        clock = Clock()
        class Expired:
            def health(_, args):
                clock.now += 31 * 10**9
                return (2, 1, True)
        g = self.gateway(clock=clock, math=Expired(), max_scenario_ns=40 * 10**9)
        t = g.ingest(self.raw, self.now)
        with self.assertRaisesRegex(Rejected, "expired during calculation"): g.scenario(t, self.now, 10**36)

    def test_base_exception_and_malformed_result_invalidate(self):
        for value in ((-1, 1, False), (2**256, 1, True), (1, 1, True), [1, 1, False], KeyboardInterrupt()):
            class Bad:
                def health(_, args):
                    if isinstance(value, BaseException): raise value
                    return value
            g = self.gateway(math=Bad())
            t = g.ingest(self.raw, self.now)
            with self.assertRaises((Rejected, KeyboardInterrupt)): g.scenario(t, self.now, 10**36)
            self.assertIsNone(g._facts)

    def test_reentrancy_cannot_restore_revoked_snapshot(self):
        class Reentrant:
            def health(_, args):
                try: g.reset(self.policy)
                except Rejected: pass
                return (2, 1, True)
        g = self.gateway(math=Reentrant())
        t = g.ingest(self.raw, self.now)
        with self.assertRaisesRegex(Rejected, "revoked"): g.scenario(t, self.now, 10**36)

    def test_thread_ownership(self):
        g = self.gateway()
        t = g.ingest(self.raw, self.now)
        caught = []
        def access():
            try: g.facts(t, self.now)
            except Rejected: caught.append(True)
        th = threading.Thread(target=access)
        th.start(); th.join()
        self.assertEqual(caught, [True])
        self.assertFalse(g.authorize(t, self.now)["commercial_admission"])

    def test_unknown_accrual_and_bad_price_remain_blocked(self):
        for price in (0, True, -1, 2**256):
            g = self.gateway()
            t = g.ingest(self.raw, self.now)
            with self.assertRaises(Rejected): g.scenario(t, self.now, price)
        p, policy, _ = make_case(666301, {"time_fee": (10**17 << 128) | (self.now - 1)})
        g = StableGateway(policy, self.math)
        t = g.ingest(encode(p), self.now)
        with self.assertRaises(Rejected): g.scenario(t, self.now, 10**36)

    def test_offline_import_preserves_inputs_and_rejects_missing_real_proof(self):
        from fixtures import policy_json
        with tempfile.TemporaryDirectory(prefix="nqc666-import-") as directory:
            tmp = Path(directory)
            packet = tmp / "packet.json"
            policy = tmp / "policy.json"
            packet.write_bytes(self.raw)
            policy.write_text(json.dumps(policy_json(self.policy)))
            lib = Path(os.environ["NQC_NATIVE_LIB"])
            command = [sys.executable, str(ROOT / "scripts/import_witness.py"),
                       "--packet", str(packet), "--policy", str(policy),
                       "--library", str(lib), "--library-sha256", hashlib.sha256(lib.read_bytes()).hexdigest(),
                       "--observed-now", str(self.now)]
            run = subprocess.run(command + ["--out", str(tmp / "accepted")], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual((tmp / "accepted/input-packet.json").read_bytes(), self.raw)
            result = json.loads((tmp / "accepted/result.json").read_text())
            self.assertFalse(result["commercial_admission"])
            # Real header paired with missing proof is deliberately a negative input.
            from state_evidence import Anchor
            h = json.loads((R3 / "fixtures/historical-header-26210229.json").read_text())["response"]["result"]
            a = Anchor(1, int(h["number"], 16), bytes.fromhex(h["hash"][2:]), int(h["timestamp"], 16), "historical_observation")
            p = copy.deepcopy(self.packet)
            p.update(header=h, blockHash=h["hash"])
            p["account"]["accountProof"] = []
            packet.write_bytes(encode(p))
            policy.write_text(json.dumps(policy_json(replace(self.policy, anchor=a))))
            command[-1] = str(a.timestamp)
            run = subprocess.run(command + ["--out", str(tmp / "rejected")], capture_output=True)
            self.assertEqual(run.returncode, 2, run.stderr)
            result = json.loads((tmp / "rejected/result.json").read_text())
            self.assertEqual(result["status"], "REJECTED")
            self.assertNotIn("facts", result)
            self.assertEqual((tmp / "rejected/input-packet.json").read_bytes(), encode(p))


if __name__ == "__main__": unittest.main()
