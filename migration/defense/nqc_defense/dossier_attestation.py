"""Publicly verifiable issuer statements over dossiers; no independent custody claim."""
import hmac
from pathlib import Path
import re
import stat

from .codec import Rejected, canonical, decode, fields
from .files import create_local, publish_local, read_local, sha256
from .receipts import hex_digest
from .review_dossier import MAX_DOSSIER, validate_pins, verify_dossier
from .review_policy import read_credential

SCHEMA = 'nqc-dossier-attestation-v1'
DOMAIN = b'NQC-DOSSIER-ATTESTATION-v1\x00'
MAX_ATTESTATION = 16 * 1024 * 1024


def backend():
    """Keep the existing standard-library-only engine usable without the signing extra."""
    try:
        from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    except ImportError as exc:
        raise Rejected('attestation_dependency_unavailable') from exc
    return Ed25519PrivateKey, Ed25519PublicKey, InvalidSignature, UnsupportedAlgorithm


def public_bytes(private_key):
    if not isinstance(private_key, bytes) or len(private_key) != 32:
        raise Rejected('attestation_private_key_size')
    private_type, _, _, unsupported = backend()
    try:
        return private_type.from_private_bytes(private_key).public_key().public_bytes_raw()
    except unsupported as exc:
        raise Rejected('attestation_algorithm_unavailable') from exc


def check_public(public_key, expected_digest):
    hex_digest(expected_digest)
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise Rejected('attestation_public_key_size')
    if sha256(public_key) != expected_digest:
        raise Rejected('attestation_public_key_pin')


def private_parent(path):
    path = Path(path).absolute()
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise Rejected('attestation_directory_permissions')
    return path


def create_signer(root):
    private_type, _, _, unsupported = backend()
    try:
        private_key = private_type.generate().private_bytes_raw()
    except unsupported as exc:
        raise Rejected('attestation_algorithm_unavailable') from exc
    public_key = public_bytes(private_key)
    root = Path(root).absolute()
    root.mkdir(mode=0o700, exist_ok=False)
    create_local(root, 'signing.key', private_key)
    create_local(root, 'verify.key', public_key)
    pin = sha256(public_key)
    load_signer(root, pin)
    return {'created': True, 'algorithm': 'Ed25519', 'public_key_sha256': pin,
            'key_custody': 'local_files', 'independent_custody': False}


def load_signer(root, expected_digest):
    root = private_parent(root)
    private_key = read_credential(root / 'signing.key')
    public_key = read_local(root, 'verify.key', 32)
    check_public(public_key, expected_digest)
    if not hmac.compare_digest(public_bytes(private_key), public_key):
        raise Rejected('attestation_key_pair_mismatch')
    return private_key


def validate_report(report, pins, dossier_digest):
    """Check bindings only. Public verification trusts the issuer's HMAC replay claim."""
    fields(report, ('verified', 'schema', 'dossier_digest', 'captured_ns', 'tenant', 'asset', 'case_id',
                    'facts', 'assessment', 'timeline', 'limits'))
    if report['verified'] is not True or report['schema'] != 'nqc-review-dossier-report-v1':
        raise Rejected('attestation_report_schema')
    if report['dossier_digest'] != dossier_digest or any(report[k] != pins[k] for k in ('tenant', 'asset', 'case_id')):
        raise Rejected('attestation_report_binding')
    facts = report['facts']
    fields(facts, ('trigger_records', 'case_snapshot', 'review', 'credentials', 'clock'))
    fields(facts['trigger_records'], ('count', 'event_ids', 'evidence_digest', 'origin_authenticated'))
    fields(facts['case_snapshot'], ('digest', 'detection_status'))
    fields(facts['review'], ('stage', 'notes_count', 'closed_by', 'checkpoint'))
    fields(facts['credentials'], ('changes', 'checkpoint'))
    if (facts['trigger_records']['evidence_digest'] != pins['evidence_digest'] or
            facts['case_snapshot']['digest'] != pins['case_digest'] or
            canonical(facts['review']['checkpoint']) != canonical(pins['case_checkpoint']) or
            canonical(facts['credentials']['checkpoint']) != canonical(pins['credential_checkpoint'])):
        raise Rejected('attestation_report_binding')


def verify_attestation(data, digest, dossier, dossier_digest, pins, public_key, public_key_digest):
    """Verify a pinned issuer's signature and exact dossier bytes, without any private key."""
    validate_pins(pins)
    hex_digest(digest); hex_digest(dossier_digest)
    check_public(public_key, public_key_digest)
    if not isinstance(data, bytes) or len(data) > MAX_ATTESTATION:
        raise Rejected('attestation_size')
    if sha256(data) != digest:
        raise Rejected('attestation_digest')
    if not isinstance(dossier, bytes) or len(dossier) > MAX_DOSSIER:
        raise Rejected('dossier_size')
    if sha256(dossier) != dossier_digest:
        raise Rejected('dossier_digest')
    value = decode(data, max_bytes=MAX_ATTESTATION, max_nodes=65536)
    fields(value, ('schema', 'statement', 'signature_hex'))
    if value['schema'] != SCHEMA or canonical(value) != data:
        raise Rejected('attestation_schema')
    statement = value['statement']
    fields(statement, ('schema', 'algorithm', 'signer_key_sha256', 'dossier_digest', 'pins', 'report'))
    if statement['schema'] != 'nqc-dossier-validation-statement-v1' or statement['algorithm'] != 'Ed25519':
        raise Rejected('attestation_statement_schema')
    if (statement['signer_key_sha256'] != public_key_digest or statement['dossier_digest'] != dossier_digest or
            canonical(statement['pins']) != canonical(pins)):
        raise Rejected('attestation_statement_binding')
    signature = value['signature_hex']
    if not isinstance(signature, str) or re.fullmatch(r'[0-9a-f]{128}', signature) is None:
        raise Rejected('attestation_signature_encoding')
    _, public_type, invalid, unsupported = backend()
    try:
        public_type.from_public_bytes(public_key).verify(bytes.fromhex(signature), DOMAIN + canonical(statement))
    except invalid as exc:
        raise Rejected('attestation_signature_invalid') from exc
    except unsupported as exc:
        raise Rejected('attestation_algorithm_unavailable') from exc
    validate_report(statement['report'], pins, dossier_digest)
    return {'schema': 'nqc-dossier-signature-report-v1', 'signature_verified': True, 'dossier_bytes_matched': True,
            'attestation_digest': digest, 'dossier_digest': dossier_digest, 'public_key_sha256': public_key_digest,
            'tenant': pins['tenant'], 'asset': pins['asset'], 'case_id': pins['case_id'],
            'signer_report': statement['report'],
            'limits': {'hmac_history_replayed_by_this_verifier': False, 'report_is_issuer_assertion': True,
                       'current_state_attested': False, 'independent_time_attested': False,
                       'independent_custody': False, 'origin_authenticated': False,
                       'signer_human_identity_verified': False, 'key_revocation_checked': False,
                       'private_key_required_for_verification': False}}


def attest_dossier(dossier, dossier_digest, pins, audit_key, signing_key, public_key_digest):
    """Issue only after full v0.17 replay. Does not assert that the snapshot is current."""
    public_key = public_bytes(signing_key)
    check_public(public_key, public_key_digest)
    if isinstance(audit_key, bytes) and hmac.compare_digest(signing_key, audit_key):
        raise Rejected('attestation_key_must_differ')
    report = verify_dossier(dossier, dossier_digest, pins, audit_key)
    statement = {'schema': 'nqc-dossier-validation-statement-v1', 'algorithm': 'Ed25519',
                 'signer_key_sha256': public_key_digest, 'dossier_digest': dossier_digest, 'pins': pins, 'report': report}
    private_type, _, _, unsupported = backend()
    try:
        signature = private_type.from_private_bytes(signing_key).sign(DOMAIN + canonical(statement))
    except unsupported as exc:
        raise Rejected('attestation_algorithm_unavailable') from exc
    data = canonical({'schema': SCHEMA, 'statement': statement, 'signature_hex': signature.hex()})
    verify_attestation(data, sha256(data), dossier, dossier_digest, pins, public_key, public_key_digest)
    return data


def publish_attestation(output, dossier, dossier_digest, pins, audit_key, signing_key, public_key_digest):
    data = attest_dossier(dossier, dossier_digest, pins, audit_key, signing_key, public_key_digest)
    output = Path(output).absolute()
    private_parent(output.parent)
    publish_local(output.parent, output.name, data)
    persisted = read_local(output.parent, output.name, MAX_ATTESTATION)
    if persisted != data:
        raise Rejected('attestation_publication_changed')
    result = verify_attestation(persisted, sha256(data), dossier, dossier_digest, pins,
                                public_bytes(signing_key), public_key_digest)
    return {'published': True, 'attestation_digest': result['attestation_digest'], 'bytes': len(data),
            'dossier_digest': dossier_digest, 'public_key_sha256': public_key_digest, 'signature_reverified': True,
            'independent_custody': False}
