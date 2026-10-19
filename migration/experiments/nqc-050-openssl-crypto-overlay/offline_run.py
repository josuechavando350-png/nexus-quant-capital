"""NQC050 guarded offline NQC037 compatibility entry point.

This program never sends RPC, reads credentials, mutates NQC037-049, initializes
budgets, or enables collection. The source is pinned by the original NQC049
bridge; Crypto and RLP shims are limited to this isolated Python process.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
OVERLAY = BASE / 'compat'
BRIDGE = BASE.parent / 'nqc-049-offline-nqc037-replay'


def fail(code):
    return {'status': code, 'requests_sent': 0,
            'commercial_admission': False, 'historical_state_proofs_acquired': 0}


def audit(repo_root):
    root = Path(repo_root).resolve()
    try:
        if not OVERLAY.is_dir() or not BRIDGE.is_dir():
            return fail('BLOCKED_MISSING_PINNED_MODULES')
        # No fallback to NIST SHA3; Keccak's empty-string vector differs.
        try:
            probe = hashlib.new('keccak-256', b'').hexdigest()
        except ValueError:
            return fail('BLOCKED_OPENSSL_KECCAK_UNAVAILABLE')
        if probe != 'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470':
            return fail('BLOCKED_OPENSSL_KECCAK_MISMATCH')
        sys.path.insert(0, str(OVERLAY))
        sys.path.insert(0, str(BRIDGE))
        import offline_bridge
        from Crypto.Hash import keccak
        import rlp
        if Path(keccak.__file__).resolve() != (OVERLAY / 'Crypto' / 'Hash' / 'keccak.py').resolve():
            return fail('BLOCKED_OVERLAY_ORIGIN')
        if Path(rlp.__file__).resolve() != (OVERLAY / 'rlp.py').resolve():
            return fail('BLOCKED_OVERLAY_ORIGIN')
        if keccak.new(digest_bits=256, data=b'abc').hexdigest() != (
                '4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45'):
            return fail('BLOCKED_CRYPTO_OVERLAY')
        if rlp.encode([b'cat', b'dog']).hex() != 'c88363617483646f67':
            return fail('BLOCKED_RLP_OVERLAY')
        # Pin original source/plan/data BEFORE loading original verify.py.
        experiments = root / 'migration' / 'experiments'
        try:
            offline_bridge.source_bindings(experiments)
            spec_path = experiments / 'nqc-038-archive-access' / 'TRIPORT_PLAN.json'
            spec = offline_bridge.decode_json(offline_bridge.read_limited(spec_path, 16*1024*1024))
            offline_bridge.check_plan(spec)
        except (offline_bridge.Blocked, OSError):
            return fail('BLOCKED_PINNED_SOURCE_OR_PLAN')
        source_path = experiments / 'nqc-037-historical-state' / 'src'
        sys.path.insert(0, str(source_path))
        try:
            import verify
            if Path(verify.__file__).resolve() != (source_path / 'verify.py').resolve():
                return fail('BLOCKED_VERIFIER_ORIGIN')
            parent_path = experiments / 'nqc-037-historical-state' / 'inputs' / 'parent-header.json'
            saved = offline_bridge.decode_json(offline_bridge.read_limited(parent_path, 16*1024*1024))
            header = saved['result']
            parent = verify.validate_header(header, verify.PARENT_HASH, verify.PARENT_NUMBER)
            if parent != verify.PARENT_HASH or header['stateRoot'] != verify.PARENT_ROOT:
                return fail('BLOCKED_PARENT_HEADER')
        except Exception:
            # Do not serialize exception messages, untrusted proof data or tokens.
            return fail('BLOCKED_AUTHENTIC_PARENT_HEADER_CHECK')
        # The original NQC037 validator is now importable and has checked the
        # captured parent header. Its dry-run receipt is deliberately non-RPC.
        output = offline_bridge.audit_repository(root)
        return {'status': output['status'],
                'parent_header_consistency': 'VERIFIED_RELATIVE_TO_CAPTURED_BYTES',
                'real_nqc037_header_validator_executed': True,
                'prefix_responses_checked': output.get('responses_validated', 0),
                'requests_sent': 0, 'historical_state_proofs_acquired': 0,
                'commercial_admission': False}
    except Exception:
        return fail('BLOCKED_OFFLINE_EXECUTION')
    finally:
        # No changes to source or system-wide packages. Process-local shim only.
        source_dir = str(root / 'migration' / 'experiments' / 'nqc-037-historical-state' / 'src')
        if source_dir in sys.path:
            sys.path.remove(source_dir)
        for p in (str(BRIDGE), str(OVERLAY)):
            if p in sys.path:
                sys.path.remove(p)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.repo_root)
    print(json.dumps(result, sort_keys=True))
    if result['status'] not in {'OFFLINE_VERIFIED_PREFIX_ONLY_NO_DISPATCH'}:
        sys.exit(2)
