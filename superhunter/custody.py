"""Detached, operator-trusted Ed25519 custody attestations for existing bundles.

Signs byte inventories only. Does not authenticate legal scope, execution, data
truth or vulnerability impact. Public-key trust MUST come from the verifier, not
from the attestation. No wallet, broadcast, network, key provisioning or targets.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
DOMAIN = b'SUPERHUNTER-CUSTODY-ED25519-V1\x00'
PROFILE = 'superhunter-bytes-custody-v1'
MAX_FILES = 512
MAX_TOTAL_BYTES = 32_000_000
MAX_KEYS = 64
HEX = re.compile(r'[0-9a-f]+\Z')
ID = re.compile(r'[a-z0-9][a-z0-9._-]{0,95}\Z')
# Flat, generated bundle names only, matching the existing evidence producers.
FILENAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z')
LIMITS = {'execution_verified': False, 'vulnerability_confirmed': False,
          'scope_authorization_verified': False, 'data_truth_verified': False,
          'independent_reproduction_verified': False, 'trusted_timestamp': False}
SEAL_FILES = {'attestation.json', 'REVIEW.md'}


class CustodyError(ValueError):
    """Fixed error codes only. Never includes paths, policy text or key material."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise CustodyError(code)


def fields(value: Any, expected: set[str], code: str) -> None:
    need(type(value) is dict and set(value) == expected, code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def hex_bytes(value: Any, length: int) -> bytes:
    need(type(value) is str and len(value) == 2*length and HEX.fullmatch(value) is not None, 'HEX_FORMAT')
    return bytes.fromhex(value)


def case_uuid(value: Any) -> str:
    need(type(value) is str, 'CASE_ID')
    try:
        result = str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise CustodyError('CASE_ID') from exc
    need(value == result, 'CASE_ID_CANONICAL')
    return result


def producer(value: Any) -> str:
    need(type(value) is str and ID.fullmatch(value) is not None, 'PRODUCER_ID')
    return value


def utc(value: Any) -> datetime:
    need(type(value) is str and len(value) <= 40 and 'T' in value, 'TIMESTAMP')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise CustodyError('TIMESTAMP') from exc
    need(result.tzinfo is not None, 'TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def key_id(public_key: Ed25519PublicKey) -> str:
    return sha(public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def validate_trust(value: Any) -> dict:
    fields(value, {'schema_version', 'profile', 'keys'}, 'TRUST_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version'] == 1 and
         value['profile'] == PROFILE, 'TRUST_VERSION')
    need(type(value['keys']) is list and 1 <= len(value['keys']) <= MAX_KEYS, 'TRUST_KEYS')
    seen = set()
    for row in value['keys']:
        fields(row, {'key_id', 'public_key_hex', 'producer_id', 'case_ids',
                     'valid_from', 'valid_until', 'revoked'}, 'TRUST_KEY_SCHEMA')
        raw = hex_bytes(row['public_key_hex'], 32)
        need(row['key_id'] == sha(raw) and row['key_id'] not in seen, 'TRUST_KEY_ID')
        seen.add(row['key_id']); producer(row['producer_id'])
        need(type(row['revoked']) is bool, 'TRUST_REVOCATION_TYPE')
        need(utc(row['valid_from']) < utc(row['valid_until']), 'TRUST_INTERVAL')
        cases = row['case_ids']
        need(type(cases) is list and 1 <= len(cases) <= 256, 'TRUST_CASES')
        for case in cases:
            case_uuid(case)
        need(len(set(cases)) == len(cases), 'DUPLICATE_TRUST_CASE')
    return value


def _trusted_key(trust: dict, identifier: str, case: str, name: str,
                 issued: datetime, expires: datetime, current: datetime) -> Ed25519PublicKey:
    validate_trust(trust)
    rows = [r for r in trust['keys'] if r['key_id'] == identifier]
    need(len(rows) == 1, 'UNTRUSTED_KEY')
    row = rows[0]
    need(row['revoked'] is False, 'KEY_REVOKED')
    need(row['producer_id'] == name and case in row['case_ids'], 'KEY_SCOPE_MISMATCH')
    start, end = utc(row['valid_from']), utc(row['valid_until'])
    need(start <= issued <= current < end and issued < expires <= end, 'KEY_VALIDITY')
    need(current < expires, 'ATTESTATION_EXPIRED')
    return Ed25519PublicKey.from_public_bytes(hex_bytes(row['public_key_hex'], 32))


def _regular_root(root: Path) -> Path:
    # Reject symlink ancestors as well as the leaf; no resolving into another tree.
    absolute = Path(os.path.abspath(root))
    for parent in (*reversed(absolute.parents), absolute):
        need(not parent.is_symlink(), 'DIRECTORY_SYMLINK')
    need(absolute.is_dir(), 'DIRECTORY_REQUIRED')
    return absolute


def capture_bundle(root: Path) -> dict:
    """Verify the exact flat manifest and inventory before attesting its bytes.

    This is NOT a substitute for the producer's semantic evidence verifier.
    Files excluded by the manifest, directories and symlinks are not signed.
    """
    root = _regular_root(root)
    raw = read_artifact(root, 'COMPLETE.json')
    marker = strict_json(raw)
    fields(marker, {'schema_version', 'sha256'}, 'MANIFEST_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1, 'MANIFEST_VERSION')
    hashes = marker['sha256']
    need(type(hashes) is dict and 1 <= len(hashes) <= MAX_FILES, 'MANIFEST_FILES')
    for name, value in hashes.items():
        need(type(name) is str and FILENAME.fullmatch(name) is not None and name != 'COMPLETE.json', 'ARTIFACT_NAME')
        hex_bytes(value, 32)
    need({p.name for p in root.iterdir()} == set(hashes) | {'COMPLETE.json'}, 'UNDECLARED_ARTIFACT')
    entries, total = [], len(raw)
    for name, expected in sorted(hashes.items()):
        content = read_artifact(root, name)
        total += len(content)
        need(total <= MAX_TOTAL_BYTES, 'TOTAL_BYTES_LIMIT')
        need(sha(content) == expected, 'ARTIFACT_HASH_MISMATCH')
        entries.append({'name': name, 'sha256': expected, 'bytes': len(content)})
    need(read_artifact(root, 'COMPLETE.json') == raw, 'MANIFEST_CHANGED')
    need({p.name for p in root.iterdir()} == set(hashes) | {'COMPLETE.json'}, 'ARTIFACT_SET_CHANGED')
    return {'manifest_sha256': sha(raw), 'artifacts': entries, 'total_bytes': total}


def _audit(evidence: dict, case: str, name: str, identifier: str, issued: str) -> dict:
    native = load_components()
    log = native.audit.AuditLog(clock=lambda: issued)
    log.append('custody.capture', {'manifest_sha256': evidence['manifest_sha256'],
                                 'inventory_sha256': sha(canonical(evidence))})
    log.append('custody.bind', {'case_id': case, 'producer_id': name, 'key_id': identifier})
    log.append('custody.scope', {'profile': PROFILE, 'assertion': 'bytes-only'})
    log.assert_intact()
    return {'entries': [asdict(e) for e in log.entries], 'head': log.head}


def attest(bundle: Path, private_key: Ed25519PrivateKey, trust: dict, *,
           case_id: str, producer_id: str, issued_at: str, expires_at: str) -> dict:
    """Sign exact captured bytes with an explicitly provided custody-only key."""
    need(isinstance(private_key, Ed25519PrivateKey), 'ED25519_PRIVATE_KEY_REQUIRED')
    case, name = case_uuid(case_id), producer(producer_id)
    issued, expires = utc(issued_at), utc(expires_at)
    need(issued < expires, 'ATTESTATION_INTERVAL')
    identifier = key_id(private_key.public_key())
    _trusted_key(trust, identifier, case, name, issued, expires, issued)
    evidence = capture_bundle(bundle)
    payload = {'schema_version': 1, 'profile': PROFILE, 'case_id': case,
               'producer_id': name, 'key_id': identifier,
               'issued_at': issued.isoformat(), 'expires_at': expires.isoformat(),
               'evidence': evidence, 'limitations': dict(LIMITS),
               'audit': _audit(evidence, case, name, identifier, issued.isoformat())}
    signature = private_key.sign(DOMAIN + canonical(payload))
    need(capture_bundle(bundle) == evidence, 'EVIDENCE_CHANGED_DURING_SIGNING')
    return {'payload': payload, 'algorithm': 'Ed25519', 'signature_hex': signature.hex()}


def verify_attestation(bundle: Path, statement: Any, trust: dict, *,
                       expected_case_id: str, expected_producer_id: str, at: str) -> dict:
    """Authenticate against independent trust input; never self-trust an envelope.

    `at` is caller-controlled for deterministic testing, not a trusted timestamp.
    Public CLI verification always uses the current clock and has no replay flag.
    """
    case, name = case_uuid(expected_case_id), producer(expected_producer_id)
    fields(statement, {'payload', 'algorithm', 'signature_hex'}, 'ATTESTATION_SCHEMA')
    need(statement['algorithm'] == 'Ed25519', 'ALGORITHM_NOT_ALLOWED')
    payload = statement['payload']
    fields(payload, {'schema_version', 'profile', 'case_id', 'producer_id', 'key_id',
                     'issued_at', 'expires_at', 'evidence', 'limitations', 'audit'}, 'PAYLOAD_SCHEMA')
    need(type(payload['schema_version']) is int and payload['schema_version'] == 1 and
         payload['profile'] == PROFILE, 'PAYLOAD_VERSION')
    need(payload['case_id'] == case and payload['producer_id'] == name, 'CONTEXT_MISMATCH')
    identifier = payload['key_id']; hex_bytes(identifier, 32)
    need(canonical(payload['limitations']) == canonical(LIMITS), 'EXCESSIVE_CLAIM')
    issued, expires, current = utc(payload['issued_at']), utc(payload['expires_at']), utc(at)
    need(issued <= current < expires, 'ATTESTATION_TIME')
    pub = _trusted_key(trust, identifier, case, name, issued, expires, current)
    try:
        pub.verify(hex_bytes(statement['signature_hex'], 64), DOMAIN + canonical(payload))
    except InvalidSignature as exc:
        raise CustodyError('INVALID_SIGNATURE') from exc
    evidence = capture_bundle(bundle)
    need(canonical(evidence) == canonical(payload['evidence']), 'SIGNED_EVIDENCE_MISMATCH')
    need(canonical(_audit(evidence, case, name, identifier, payload['issued_at'])) ==
         canonical(payload['audit']), 'SIGNED_AUDIT_MISMATCH')
    need(capture_bundle(bundle) == evidence, 'EVIDENCE_CHANGED_DURING_VERIFICATION')
    return {'status': 'TRUSTED_CUSTODY_SIGNATURE_VALID', 'profile': PROFILE,
            'case_id': case, 'producer_id': name, 'key_id': identifier,
            'artifact_count': len(evidence['artifacts']), 'manifest_sha256': evidence['manifest_sha256'],
            'signature_valid': True, 'trusted_key_scope_matched': True,
            'human_identity_verified': False, 'semantic_evidence_verified': False,
            'verified_at': current.isoformat(), **LIMITS}


def _summary(statement: dict) -> bytes:
    count = len(statement['payload']['evidence']['artifacts'])
    return (f'# Custodia de evidencia\n\nArchivos declarados: {count}.\n'
            'Firma Ed25519 separada de los originales. Requiere una clave pública de confianza externa.\n'
            'Una firma valida custodia de bytes, NO ejecución, autorización, datos verdaderos ni vulnerabilidad.\n'
            'No adjuntar la clave privada. El registro de confianza no se toma del paquete firmado.\n').encode()


def _key_file(path: Path) -> Ed25519PrivateKey:
    _regular_root(path.parent)
    need(hasattr(os, 'O_NOFOLLOW'), 'POSIX_REQUIRED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and
             info.st_mode & 0o077 == 0 and info.st_nlink == 1 and info.st_size <= 16384,
             'PRIVATE_KEY_FILE_PROTECTION')
        raw = os.read(fd, 16385)
        need(len(raw) <= 16384, 'PRIVATE_KEY_FILE_SIZE')
    finally:
        os.close(fd)
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (ValueError, TypeError) as exc:
        raise CustodyError('PRIVATE_KEY_FORMAT') from exc
    need(isinstance(key, Ed25519PrivateKey), 'ED25519_PRIVATE_KEY_REQUIRED')
    return key


def seal(bundle: Path, out: Path, key_file: Path, trust_file: Path, *,
         case_id: str, producer_id: str, expires_at: str) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    b, o = bundle.resolve(), out.resolve()
    need(not o.is_relative_to(b) and not b.is_relative_to(o) and not o.is_relative_to(ROOT.parent), 'OUTPUT_LOCATION')
    for path in (key_file, trust_file):
        need(not path.resolve().is_relative_to(b) and not path.resolve().is_relative_to(o), 'TRUST_OR_KEY_INSIDE_EVIDENCE')
    _regular_root(trust_file.parent)
    raw_trust = read_artifact(trust_file.parent, trust_file.name)
    trust = validate_trust(strict_json(raw_trust))
    statement = attest(bundle, _key_file(key_file), trust, case_id=case_id,
                       producer_id=producer_id, issued_at=now_text(), expires_at=expires_at)
    need(read_artifact(trust_file.parent, trust_file.name) == raw_trust, 'TRUST_CHANGED')
    # Self-verification before publication; signing does not skip scope/time checks.
    result = verify_attestation(bundle, statement, trust, expected_case_id=case_id,
                                expected_producer_id=producer_id, at=now_text())
    write_new_bundle(out, {'attestation.json': canonical(statement), 'REVIEW.md': _summary(statement)})
    return result


def verify_seal(bundle: Path, seal_dir: Path, trust_file: Path, *,
                case_id: str, producer_id: str) -> dict:
    _regular_root(seal_dir)
    need(not trust_file.resolve().is_relative_to(bundle.resolve()) and
         not trust_file.resolve().is_relative_to(seal_dir.resolve()), 'TRUST_INSIDE_EVIDENCE')
    marker = strict_json(read_artifact(seal_dir, 'COMPLETE.json'))
    fields(marker, {'schema_version', 'sha256'}, 'SEAL_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == SEAL_FILES and
         {p.name for p in seal_dir.iterdir()} == SEAL_FILES | {'COMPLETE.json'}, 'SEAL_FILES')
    data = {name: read_artifact(seal_dir, name) for name in SEAL_FILES}
    need(all(sha(raw) == marker['sha256'][name] for name, raw in data.items()), 'SEAL_HASH')
    statement = strict_json(data['attestation.json'])
    _regular_root(trust_file.parent)
    raw_trust = read_artifact(trust_file.parent, trust_file.name)
    result = verify_attestation(bundle, statement, strict_json(raw_trust), expected_case_id=case_id,
                                expected_producer_id=producer_id, at=now_text())
    need(data['REVIEW.md'] == _summary(statement), 'SEAL_SUMMARY')
    need(read_artifact(trust_file.parent, trust_file.name) == raw_trust, 'TRUST_CHANGED')
    return result


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Authenticate custody bytes with external Ed25519 trust; not a Finding')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('seal-evidence')
    check = sub.add_parser('verify-custody')
    for command in (make, check):
        for option in ('bundle', 'trust'):
            command.add_argument('--'+option, type=Path, required=True)
        command.add_argument('--case-id', required=True)
        command.add_argument('--producer', required=True)
    make.add_argument('--key-file', type=Path, required=True)
    make.add_argument('--expires-at', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--seal', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (seal(args.bundle, args.out, args.key_file, args.trust,
                       case_id=args.case_id, producer_id=args.producer, expires_at=args.expires_at)
                  if args.command == 'seal-evidence' else
                  verify_seal(args.bundle, args.seal, args.trust, case_id=args.case_id, producer_id=args.producer))
        # No paths, identities, source text or private key values enter console logs.
        print(json.dumps({k: result[k] for k in ('status', 'artifact_count', 'signature_valid',
                                                'execution_verified', 'vulnerability_confirmed')}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print(json.dumps({'status': 'CUSTODY_REJECTED', 'signature_valid': False,
                          'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
