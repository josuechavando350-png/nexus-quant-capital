"""Join verified archive bytes with a separately pinned custody trust policy."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import zipfile

from . import bundle_recovery as recovery, custody, owned_capture, preserved_index as index, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, strict_json, write_new_bundle

PROFILE = 'preserved-index-custody-review-v1'
FILES = {'custody.json', 'REVIEW.md', 'COMPLETE.json'}
LIMITS = {**index.LIMITS, 'human_identity_verified': False, 'independent_custodian_proved': False,
          'trusted_timestamp': False, 'vulnerability_confirmed': False, 'platform_complete': False}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _closed(bundle: Path, names: set[str], anchor: str, label: str) -> tuple[dict[str, bytes], dict]:
    owned_capture._digest(anchor)
    raw, identities = recovery._capture(bundle)
    need(set(raw) == names | {'COMPLETE.json'}, label + '_INVENTORY')
    marker = canonical({'schema_version': 1, 'sha256': {name: quality.sha(value) for name, value in raw.items()
                                                     if name != 'COMPLETE.json'}})
    need(raw['COMPLETE.json'] == marker and quality.sha(marker) == anchor, label + '_ANCHOR')
    return raw, identities


def _locations(bundle: Path, seal: Path, trust: Path, out: Path | None = None, *, new: bool = False) -> None:
    owned_capture._path(bundle, new=False); owned_capture._path(seal, new=False)
    roots = [bundle.resolve(), seal.resolve()]
    if out is not None:
        owned_capture._path(out, new=new); roots.append(out.resolve())
    for number, first in enumerate(roots):
        for second in roots[number+1:]:
            need(not first.is_relative_to(second) and not second.is_relative_to(first), 'PRESERVED_CUSTODY_OVERLAP')
        need(not trust.resolve().is_relative_to(first), 'PRESERVED_CUSTODY_EXTERNAL_TRUST_REQUIRED')


def _stable(bundle: Path, archive_root: Path, seal: Path, trust: Path, captured: dict, *,
            index_anchor: str, seal_anchor: str, case_id: str, producer_id: str) -> dict:
    index._stable(archive_root, captured['stamps'], captured['snapshot'])
    need(index._saved(bundle, index_anchor) == captured['index'], 'PRESERVED_CUSTODY_INDEX_CHANGED')
    need(_closed(seal, custody.SEAL_FILES, seal_anchor, 'PRESERVED_CUSTODY_SEAL') == captured['seal'],
         'PRESERVED_CUSTODY_SEAL_CHANGED')
    need(index._read_manifest(trust) == captured['trust'], 'PRESERVED_CUSTODY_TRUST_CHANGED')
    # Check current local-clock expiry and revocation again at the end. No replay
    # timestamp flag and no claim that this host's clock is an authenticated time.
    signature = custody.verify_seal(bundle, seal, trust, case_id=case_id, producer_id=producer_id)
    need(signature['signature_valid'] is True and signature['trusted_key_scope_matched'] is True,
         'PRESERVED_CUSTODY_SIGNATURE')
    need(index._saved(bundle, index_anchor) == captured['index'] and
         _closed(seal, custody.SEAL_FILES, seal_anchor, 'PRESERVED_CUSTODY_SEAL') == captured['seal'] and
         index._read_manifest(trust) == captured['trust'], 'PRESERVED_CUSTODY_EVIDENCE_CHANGED')
    index._stable(archive_root, captured['stamps'], captured['snapshot'])
    return signature


def _collect(bundle: Path, archive_root: Path, seal: Path, trust: Path, *, source_digest: str,
             manifest_anchor: str, index_anchor: str, seal_anchor: str, trust_anchor: str,
             case_id: str, producer_id: str, index_source_digest: str | None,
             review_source_digest: str) -> tuple[dict, dict]:
    _locations(bundle, seal, trust)
    for anchor in (seal_anchor, trust_anchor, review_source_digest): owned_capture._digest(anchor)
    custody.case_uuid(case_id); custody.producer(producer_id)
    snapshot = index._snapshot(source_digest)
    raw_index = index._saved(bundle, index_anchor)
    manifest = index._manifest(raw_index[0]['inputs.json'], manifest_anchor)
    raw_seal = _closed(seal, custody.SEAL_FILES, seal_anchor, 'PRESERVED_CUSTODY_SEAL')
    raw_trust = index._read_manifest(trust)
    need(quality.sha(raw_trust[0]) == trust_anchor, 'PRESERVED_CUSTODY_TRUST_ANCHOR')
    custody.validate_trust(strict_json(raw_trust[0]))
    stamps = {}; total = 0
    for row in manifest['archives']:
        stamp = index._stamp(archive_root / row['file']); total += stamp[1][3]
        need(total <= index.MAX_TOTAL_BYTES, 'PRESERVED_CUSTODY_TOTAL_BYTES')
        stamps[row['file']] = stamp
    signature = custody.verify_seal(bundle, seal, trust, case_id=case_id, producer_id=producer_id)
    checked = index.verify(bundle, archive_root, source_digest=source_digest, manifest_anchor=manifest_anchor,
                           index_anchor=index_anchor, index_source_digest=index_source_digest)
    captured = {'index': raw_index, 'seal': raw_seal, 'trust': raw_trust, 'stamps': stamps, 'snapshot': snapshot}
    final_signature = _stable(bundle, archive_root, seal, trust, captured, index_anchor=index_anchor,
                              seal_anchor=seal_anchor, case_id=case_id, producer_id=producer_id)
    need(signature['key_id'] == final_signature['key_id'] and signature['manifest_sha256'] == index_anchor,
         'PRESERVED_CUSTODY_SIGNATURE_CONTEXT')
    report = {'schema_version': 1, 'profile': PROFILE, 'state': 'PRESERVED_INDEX_AND_CUSTODY_VERIFIED',
              'review_source_digest': review_source_digest, 'index_source_digest': checked['index_source_digest'],
              'manifest_anchor': manifest_anchor, 'index_anchor': index_anchor, 'seal_anchor': seal_anchor,
              'trust_anchor': trust_anchor, 'case_id': case_id, 'producer_id': producer_id,
              'custody_key_id': signature['key_id'], 'custody_signature_verified': True,
              'custody_key_scope_verified': True, 'archive_bytes_checked': True,
              'counts': checked['counts'], 'limitations': dict(LIMITS)}
    return report, captured


def render(report: dict) -> bytes:
    c = report['counts']
    return (f"# Índice y custodia verificados\n\nEntradas: {c['entries']}; ZIP distintos: {c['unique_archives']}; "
            f"inventarios originales: {c['unique_input_inventories']}.\n"
            f"Capturas incompletas por ZIP único: {c['incomplete_unique_archives']}.\n\n"
            'Se verificó cada archivo y el índice, además de la firma Ed25519 y el alcance de su clave.\n'
            'La política de confianza y el sello tienen anclas externas explícitas.\n'
            'La firma vincula custodia de bytes a esa clave y caso; no autentica ejecución ni identidad humana.\n'
            'Una captura incompleta permanece incompleta. No demuestra productores o custodios independientes.\n'
            'La vigencia se comprueba con el reloj local actual, sin acreditar tiempo confiable.\n').encode()


def _result(report: dict, report_anchor: str, source_digest: str, *, built: bool) -> dict:
    return {key: report[key] for key in ('profile', 'state', 'review_source_digest', 'index_source_digest',
        'manifest_anchor', 'index_anchor', 'seal_anchor', 'trust_anchor', 'counts',
        'custody_signature_verified', 'custody_key_scope_verified', 'archive_bytes_checked')} | {
        'operation': 'PRESERVED_CUSTODY_REVIEW_BUILT' if built else 'PRESERVED_CUSTODY_REVIEW_VERIFIED',
        'source_digest': source_digest, 'report_anchor': report_anchor, **LIMITS}


def create(bundle: Path, archive_root: Path, seal: Path, trust: Path, out: Path, *, source_digest: str,
           manifest_anchor: str, index_anchor: str, seal_anchor: str, trust_anchor: str,
           case_id: str, producer_id: str, index_source_digest: str | None = None) -> dict:
    _locations(bundle, seal, trust, out, new=True)
    context = {'source_digest': source_digest, 'manifest_anchor': manifest_anchor, 'index_anchor': index_anchor,
               'seal_anchor': seal_anchor, 'trust_anchor': trust_anchor, 'case_id': case_id,
               'producer_id': producer_id, 'index_source_digest': index_source_digest}
    report, captured = _collect(bundle, archive_root, seal, trust, **context, review_source_digest=source_digest)
    payload = {'custody.json': canonical(report), 'REVIEW.md': render(report)}
    write_new_bundle(out, payload)
    marker = canonical({'schema_version': 1, 'sha256': {name: quality.sha(raw) for name, raw in payload.items()}})
    report_anchor = quality.sha(marker)
    saved, unused = _closed(out, FILES - {'COMPLETE.json'}, report_anchor, 'PRESERVED_CUSTODY_REPORT')
    need(saved == {**payload, 'COMPLETE.json': marker}, 'PRESERVED_CUSTODY_OUTPUT_CHANGED')
    _stable(bundle, archive_root, seal, trust, captured, index_anchor=index_anchor,
            seal_anchor=seal_anchor, case_id=case_id, producer_id=producer_id)
    return _result(report, report_anchor, source_digest, built=True)


def verify(bundle: Path, archive_root: Path, seal: Path, trust: Path, report: Path, *, source_digest: str,
           manifest_anchor: str, index_anchor: str, seal_anchor: str, trust_anchor: str,
           case_id: str, producer_id: str, report_anchor: str, index_source_digest: str | None = None,
           review_source_digest: str | None = None) -> dict:
    _locations(bundle, seal, trust, report, new=False)
    producer = source_digest if review_source_digest is None else review_source_digest
    owned_capture._digest(producer)
    saved = _closed(report, FILES - {'COMPLETE.json'}, report_anchor, 'PRESERVED_CUSTODY_REPORT')
    fresh, captured = _collect(bundle, archive_root, seal, trust, source_digest=source_digest,
        manifest_anchor=manifest_anchor, index_anchor=index_anchor, seal_anchor=seal_anchor, trust_anchor=trust_anchor,
        case_id=case_id, producer_id=producer_id, index_source_digest=index_source_digest, review_source_digest=producer)
    need(saved[0]['custody.json'] == canonical(fresh) and saved[0]['REVIEW.md'] == render(fresh), 'PRESERVED_CUSTODY_CONTENT')
    _stable(bundle, archive_root, seal, trust, captured, index_anchor=index_anchor,
            seal_anchor=seal_anchor, case_id=case_id, producer_id=producer_id)
    need(_closed(report, FILES - {'COMPLETE.json'}, report_anchor, 'PRESERVED_CUSTODY_REPORT') == saved,
         'PRESERVED_CUSTODY_REPORT_CHANGED')
    return _result(fresh, report_anchor, source_digest, built=False)


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Verify preserved index bytes and separately trusted custody together')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('review-preserved-custody'); check = sub.add_parser('verify-preserved-custody')
    for command in (make, check):
        for name in ('bundle', 'archive-root', 'seal', 'trust'): command.add_argument('--' + name, required=True, type=Path)
        for name in ('source-digest', 'manifest-anchor', 'index-anchor', 'seal-anchor', 'trust-anchor', 'case-id', 'producer-id'):
            command.add_argument('--' + name, required=True)
        command.add_argument('--index-source-digest')
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--report', type=Path, required=True); check.add_argument('--report-anchor', required=True)
    check.add_argument('--review-source-digest')
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = create(**args) if command == 'review-preserved-custody' else verify(**args)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['counts']['incomplete_unique_archives'] == 0 else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError,
            zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, EOFError, struct.error):
        print(json.dumps({'state': 'PRESERVED_CUSTODY_REJECTED', 'custody_signature_verified': False})); return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
