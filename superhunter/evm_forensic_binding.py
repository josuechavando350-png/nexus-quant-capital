"""Bound real Geth-formatted opcode traces to replay-verified offline journal records.

The trace decoder is the existing EVM parser, not a substitute mock. This
bridge never runs an EVM, compiles source, acquires logs, or asserts trace/log
producer authenticity. A digest inside a journal record creates an exact
byte-level *claim* of association, NOT proof of execution time or causality.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

from . import evm_opcode_trace as op
from . import journal_ingest as journal
from . import forensic_timeline as ft
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-offline-evm-journal-byte-binding-v1'
SOURCE_FILES = ('evm_forensic_binding.py', 'evm_opcode_trace.py',
                'evm_execution.py', 'journal_ingest.py', 'forensic_timeline.py',
                'quality.py', 'safe_io.py', 'privacy.py')
FILES = frozenset({'trace.jsonl', 'context.json', 'journal.jsonl',
                   'metadata.json', 'finding.json', 'receipt.json', 'REVIEW.md'})
ANCHOR_FIELD = 'SH_EVM_TRACE_SHA256'


class BindingError(ValueError):
    """Only fixed diagnostic codes may be shown to the operator."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise BindingError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_snapshot() -> dict[str, str]:
    return {name: sha(read_artifact(ROOT, name)) for name in SOURCE_FILES}


def context_fields(value: Any) -> dict:
    need(type(value) is dict and set(value) == {
        'schema_version', 'profile', 'bytecode_hex', 'gas_budget',
        'observed', 'journal_event_id'}, 'CONTEXT_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version'] == 1
         and value['profile'] == PROFILE, 'CONTEXT_PROFILE')
    # Reuse the real Geth trace parser's bytecode position decoder to reject
    # invalid, unbounded or non-canonical code before studying evidence.
    try:
        op.instruction_positions(value['bytecode_hex'])
    except (ValueError, TypeError) as exc:
        raise BindingError('BYTECODE_INVALID') from exc
    need(type(value['gas_budget']) is int and value['gas_budget'] in (1, op.evm.GAS),
         'GAS_BUDGET')
    obs = value['observed']
    need(type(obs) is dict and set(obs) == {'return_data', 'error'} and
         type(obs['return_data']) is str and obs['return_data'].startswith('0x') and
         (obs['error'] is None or type(obs['error']) is str), 'OBSERVED_SCHEMA')
    ft.ident(value['journal_event_id'], 'JOURNAL_EVENT_ID')
    return value


def analyze(trace_raw: bytes, context_raw: bytes, journal_raw: bytes,
            metadata_raw: bytes) -> dict:
    """Reconstruct every claim from original bytes, never trust a stored result."""
    context = context_fields(strict_json(context_raw))
    metadata = strict_json(metadata_raw)
    projection, line_receipts = journal.normalized(journal_raw, metadata)
    # journal.normalized verifies timestamp microseconds, cursors, record
    # lengths and offsets; the timeline verifies source clock parameters.
    ft.analyze(projection)
    selected = [(i, row) for i, row in enumerate(projection['events'])
                if row['event_id'] == context['journal_event_id']]
    need(len(selected) == 1, 'JOURNAL_EVENT_NOT_FOUND')
    index, event = selected[0]
    line = line_receipts[index]
    record = journal_raw[line['offset']:line['offset'] + line['length']]
    need(len(record) == line['length'] and sha(record) == line['sha256'] and
         event['artifact_sha256'] == line['sha256'], 'JOURNAL_RECORD_MISMATCH')
    # The purported association is a journal field, NOT merely an operator
    # naming two separate files in a context object.
    entry = strict_json(record[:-1] if record.endswith(b'\n') else record)
    anchor = entry.get(ANCHOR_FIELD)
    need(type(anchor) is str and ft.HEX64.fullmatch(anchor) is not None,
         'TRACE_ANCHOR_REQUIRED')
    need(anchor == sha(trace_raw), 'TRACE_ANCHOR_MISMATCH')
    try:
        decoded = op.decode_trace(trace_raw, context['bytecode_hex'],
                                  context['observed'], budget=context['gas_budget'])
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        raise BindingError('EVM_TRACE_STRUCTURALLY_INVALID') from exc
    return {
        'schema_version': 1, 'profile': PROFILE,
        'status': 'TRACE_AND_JOURNAL_BYTES_BOUND_UNAUTHENTICATED',
        'raw': {'trace_sha256': sha(trace_raw), 'context_sha256': sha(context_raw),
                'journal_sha256': sha(journal_raw), 'metadata_sha256': sha(metadata_raw)},
        'journal': {
            'source_id': projection['sources'][0]['source_id'],
            'event_id': event['event_id'], 'event_timestamp': event['timestamp'],
            'clock_uncertainty_ms': projection['sources'][0]['clock_uncertainty_ms'],
            'record_offset': line['offset'], 'record_length': line['length'],
            'record_sha256': line['sha256'], 'record_sequence': line['sequence'],
            'anchor_field': ANCHOR_FIELD},
        'evm': {'bytecode_sha256': sha(bytes.fromhex(context['bytecode_hex'])),
                'steps': decoded['steps'], 'instruction_sites': decoded['instruction_sites'],
                'conditional_edge_set': decoded['conditional_edge_set'],
                'trace_pc_opcode_sha256': decoded['pc_opcode_sha256'],
                'jump_transitions_sha256': decoded['jump_transitions_sha256'],
                'gas_used': decoded['gas_used'],
                'terminal_error': decoded['terminal_error'],
                'terminal_output_sha256': sha(decoded['terminal_output'].encode('ascii')),
                'all_reachable_sites_enumerated': False},
        'claims': {'journal_record_matches_trace_bytes': True,
                   'geth_trace_structure_checked': True,
                   'journal_producer_authenticated': False,
                   'evm_execution_replayed_here': False,
                   'execution_timestamp_authenticated': False,
                   'cross_source_causation_proved': False,
                   'vulnerability_confirmed': False,
                   'incident_confirmed': False}}


def render(result: dict) -> bytes:
    return (f'# SUPERHUNTER — journal / EVM opcode trace evidence bridge\n\n'
            f"Status: **{result['status']}**. Observed EVM trace steps: "
            f"{result['evm']['steps']}; unique observed PCs: "
            f"{len(result['evm']['instruction_sites'])}.\n\n"
            'Verified exactly one journal record with a matching 256-bit trace '
            'content hash. The original trace, journal and context remain in a '
            'PRIVATE bundle. EVM trace structure is decoded with the existing '
            'Geth trace parser; no EVM executable or source compiler was run '
            'during this bridge. The producer supplied both the journal log '
            'and the declared EVM observations, so an internally consistent '
            'association is NOT proof of authentic execution, timing, '
            'incident, exploitability or causality. The journal timestamp is '
            'not an opcode execution timestamp.\n').encode('utf-8')


def summary(result: dict) -> dict:
    return {'status': result['status'], 'observed_steps': result['evm']['steps'],
            'trace_bound_to_journal_record': True,
            'evm_execution_replayed_here': False,
            'vulnerability_confirmed': False}


def review(journal_bundle: Path, trace_file: Path, context_file: Path,
           out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'PRIVATE_NEW_OUTPUT_REQUIRED')
    try:
        journal.verify(journal_bundle)
    except (ValueError, OSError, TypeError) as exc:
        raise BindingError('JOURNAL_BUNDLE_UNVERIFIED') from exc
    trace_raw = read_artifact(trace_file.parent, trace_file.name)
    context_raw = read_artifact(context_file.parent, context_file.name)
    log_raw = read_artifact(journal_bundle, 'journal.jsonl')
    meta_raw = read_artifact(journal_bundle, 'metadata.json')
    snap = source_snapshot()
    result = analyze(trace_raw, context_raw, log_raw, meta_raw)
    need(source_snapshot() == snap, 'SOURCE_CHANGED_DURING_REVIEW')
    receipt = {'schema_version': 1, 'source_snapshot': snap,
               'finding_sha256': sha(canonical(result)),
               'source_bundle_complete_sha256': sha(read_artifact(journal_bundle, 'COMPLETE.json'))}
    write_new_bundle(out, {'trace.jsonl': trace_raw, 'context.json': context_raw,
                           'journal.jsonl': log_raw, 'metadata.json': meta_raw,
                           'finding.json': canonical(result),
                           'receipt.json': canonical(receipt), 'REVIEW.md': render(result)})
    return summary(result)


def verify(bundle: Path, expected_complete_sha256: str | None = None) -> dict:
    need(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    marker_raw = read_artifact(bundle, 'COMPLETE.json')
    if expected_complete_sha256 is not None:
        need(type(expected_complete_sha256) is str and
             ft.HEX64.fullmatch(expected_complete_sha256) is not None,
             'EXTERNAL_SHA_FORMAT')
        need(sha(marker_raw) == expected_complete_sha256,
             'EXTERNAL_SHA_MISMATCH')
    marker = strict_json(marker_raw)
    need(type(marker) is dict and set(marker) == {'schema_version', 'sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES and
         {p.name for p in bundle.iterdir()} == FILES | {'COMPLETE.json'},
         'BUNDLE_MANIFEST_INVALID')
    content = {name: read_artifact(bundle, name) for name in FILES}
    need(all(type(marker['sha256'][name]) is str and
             marker['sha256'][name] == sha(raw) for name, raw in content.items()),
         'ARTIFACT_TAMPERED')
    receipt = strict_json(content['receipt.json'])
    need(type(receipt) is dict and set(receipt) == {
            'schema_version', 'source_snapshot', 'finding_sha256',
            'source_bundle_complete_sha256'} and
         type(receipt['schema_version']) is int and receipt['schema_version'] == 1,
         'RECEIPT_SCHEMA')
    need(receipt['source_snapshot'] == source_snapshot(), 'SOURCE_SNAPSHOT_CHANGED')
    result = analyze(content['trace.jsonl'], content['context.json'],
                     content['journal.jsonl'], content['metadata.json'])
    need(content['finding.json'] == canonical(result) and
         receipt['finding_sha256'] == sha(canonical(result)), 'FINDING_REPLAY_MISMATCH')
    need(content['REVIEW.md'] == render(result), 'REPORT_MISMATCH')
    need(type(receipt['source_bundle_complete_sha256']) is str and
         ft.HEX64.fullmatch(receipt['source_bundle_complete_sha256']) is not None,
         'SOURCE_BUNDLE_DIGEST_FORMAT')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Offline Geth trace and journald evidence binding')
    sub = p.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    a = sub.add_parser('review-evm-forensic')
    a.add_argument('--journal-bundle', required=True, type=Path)
    a.add_argument('--trace', required=True, type=Path)
    a.add_argument('--context', required=True, type=Path)
    a.add_argument('--out', required=True, type=Path)
    b = sub.add_parser('verify-evm-forensic')
    b.add_argument('--bundle', required=True, type=Path)
    b.add_argument('--expected-complete-sha256', default=None)
    args = p.parse_args(argv)
    try:
        result = (review(args.journal_bundle, args.trace, args.context, args.out)
                  if args.command == 'review-evm-forensic'
                  else verify(args.bundle, args.expected_complete_sha256))
        print(canonical(result).decode('ascii').strip())
        return 0
    except (ValueError, OSError, TypeError, UnicodeError, OverflowError) as exc:
        code = exc.args[0] if type(exc) is BindingError else 'EVM_FORENSIC_BINDING_REJECTED'
        print(code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
