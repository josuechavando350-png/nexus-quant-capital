"""Use immutable R3/R6 synthetic fixtures; never relabel them as market data."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
R6 = ROOT.parent / "r6-witness-ingress"
sys.path[:0] = [str(ROOT / "python"), str(R6 / "scripts")]
from corpus import cases, policy_from, R3, R4, R5
from stream_ingress import StreamIngress
from native_math import NativeMath
from witness_gateway import StableGateway


def chunks(raw, width):
    return tuple(raw[i:i+width] for i in range(0, len(raw), width))
