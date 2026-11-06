"""Offline directed-witness audit for evidence-bound vulnerability-chain hypotheses.

This derives *proof obligations*, not exploit paths or causal conclusions. It
reopens and verifies the original critical-chain bundle and its three permitted
kinds of underlying evidence, without contacting any remote target.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

from . import critical_chain as triage
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ('chain_path_audit.py', 'critical_chain.py', 'forensic_timeline.py',
                'journal_correlation.py', 'evm_bounded_replay.py',
                'evm_forensic_binding.py', 'evm_opcode_trace.py',
                'safe_io.py', 'privacy.py', 'quality.py', '__main__.py')
FILES = frozenset({'source-pin.json', 'path-audit.json', 'receipt.json', 'REVIEW.md'})
PROFILE = 'offline-directed-evidence-witness-v1'


class PathAuditError(ValueError):
    """Controlled error code (no supplied evidence in messages)."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PathAuditError(code)


def exact_fields(obj: Any, keys: set[str], code: str) -> None:
    require(type(obj) is dict and set(obj) == keys, code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot() -> dict[str, str]:
    return {name: sha(read_artifact(ROOT, name)) for name in SOURCE_FILES}


def trusted_ref(refs: Any, pinned: dict[str, dict]) -> bool:
    """A valid local anchor; NEVER proof of cause, authorization or impact."""
    return any(r['source_id'] in pinned and
               pinned[r['source_id']]['status'] != 'DECLARED_CONSTRAINT_CONTRADICTION'
               for r in refs)


def longest_directed_witness(nodes: list[str], edges: list[tuple[str, str, bool]]) -> list[str]:
    """Longest directed path, then least unanchored edges, then lexical tie-break.

    Uses memoized DAG dynamic programming. Cycles have already been rejected by
    the upstream triage verifier; this function guards against recursion cycles.
    All three criteria are evaluated over every selected node, not input order.
    """
    outgoing: dict[str, list[tuple[str, bool]]] = {n: [] for n in nodes}
    for start, end, anchored in edges:
        outgoing[start].append((end, anchored))
    cache: dict[str, tuple[tuple[str, ...], int]] = {}
    visiting: set[str] = set()

    def better(a: tuple[tuple[str, ...], int],
               b: tuple[tuple[str, ...], int]) -> bool:
        path_a, gaps_a = a
        path_b, gaps_b = b
        return (-len(path_a), gaps_a, path_a) < (-len(path_b), gaps_b, path_b)

    def solve(start: str) -> tuple[tuple[str, ...], int]:
        if start in cache:
            return cache[start]
        require(start not in visiting, 'DIRECTED_CYCLE')
        visiting.add(start)
        best = ((start,), 0)
        for dst, anchored in sorted(outgoing[start]):
            suffix, gap = solve(dst)
            candidate = ((start,) + suffix, gap + (0 if anchored else 1))
            if better(candidate, best):
                best = candidate
        visiting.remove(start)
        cache[start] = best
        return best

    winner: tuple[tuple[str, ...], int] | None = None
    for n in sorted(nodes):
        candidate = solve(n)
        if winner is None or better(candidate, winner):
            winner = candidate
    return list(winner[0]) if winner else []


def compute(spec: dict, pins: list[dict], old_assessment: dict) -> dict:
    """Re-derive upstream results and calculate directed evidence obligations."""
    require(triage.validate_and_score(spec, pins) == old_assessment,
            'UPSTREAM_ASSESSMENT_CHANGED')
    pinned = {p['source_id']: p for p in pins}
    observations = {o['observation_id']: o for o in spec['observations']}
    links = {(l['from'], l['to']): l for l in spec['links']}
    upstream = {c['candidate_id']: c for c in old_assessment['ranked_candidates']}
    reports = []
    for candidate in sorted(spec['candidates'], key=lambda x: x['candidate_id']):
        cid = candidate['candidate_id']
        nodes = sorted(candidate['observation_ids'])
        included = set(nodes)
        related = [links[e] for e in sorted(links)
                   if e[0] in included and e[1] in included]
        graph_edges = [(edge['from'], edge['to'],
                        trusted_ref(edge['evidence_refs'], pinned))
                       for edge in related]
        witness = longest_directed_witness(nodes, graph_edges)
        require(bool(witness), 'MISSING_WITNESS')
        uncovered = sorted(included - set(witness))
        obs_gaps = sorted(n for n in nodes if not trusted_ref(
            observations[n]['evidence_refs'], pinned))
        link_gaps = [{'from': e['from'], 'to': e['to'], 'relation': e['relation']}
                     for e in related if not trusted_ref(e['evidence_refs'], pinned)]
        broken = sorted({r['source_id'] for n in nodes
                         for r in observations[n]['evidence_refs']
                         if pinned[r['source_id']]['status'] ==
                         'DECLARED_CONSTRAINT_CONTRADICTION'} |
                        {r['source_id'] for e in related
                         for r in e['evidence_refs']
                         if pinned[r['source_id']]['status'] ==
                         'DECLARED_CONSTRAINT_CONTRADICTION'})
        # Every path step is a CLAIMED relation even when an event hash exists.
        witness_edges = [{'from': a, 'to': b,
                          'has_locally_verified_reference': trusted_ref(
                              links[(a, b)]['evidence_refs'], pinned),
                          'causation_proved': False}
                         for a, b in zip(witness, witness[1:])]
        obligations = ['AUTHENTICATE_SCOPE_AND_PERMISSION',
                       'ATTEST_EVIDENCE_PRODUCERS']
        if broken:
            obligations.append('RESOLVE_CONTRADICTORY_SOURCE')
        if obs_gaps:
            obligations.append('CAPTURE_OBSERVATION_SUPPORT')
        if link_gaps:
            obligations.append('TEST_DEPENDENCY_HYPOTHESES')
        if uncovered:
            obligations.append('DESIGN_BRANCH_COVERAGE_EXPERIMENT')
        obligations.extend(('REPRODUCE_IN_AUTHORIZED_LAB',
                            'VERIFY_IMPACT_INDEPENDENTLY'))
        if broken:
            disposition = 'SOURCE_CONTRADICTION_REQUIRES_REVIEW'
        elif obs_gaps or link_gaps:
            disposition = 'LOCAL_EVIDENCE_GAPS'
        elif uncovered:
            disposition = 'BRANCHED_OR_PARTIAL_DIRECTED_WITNESS'
        else:
            disposition = 'DIRECTED_WITNESS_ANCHORED_NOT_CAUSAL_PROOF'
        reports.append({
            'candidate_id': cid,
            'potential_impact_claim': candidate['potential_impact'],
            'upstream_priority_score': upstream[cid]['priority_score'],
            'upstream_status': upstream[cid]['status'],
            'nodes_in_hypothesis': len(nodes),
            'directional_witness': witness,
            'witness_edges': witness_edges,
            'witness_node_count': len(witness),
            'uncovered_nodes': uncovered,
            'unsupported_observations': obs_gaps,
            'unsupported_declared_links': link_gaps,
            'contradictory_source_ids': broken,
            'disposition': disposition,
            'proof_obligations': obligations,
            'critical_impact_confirmed': False,
            'causation_proved': False,
            'active_testing_permitted': False,
            'vulnerability_confirmed': False,
        })
    return {'schema_version': 1, 'profile': PROFILE,
            'result': 'OFFLINE_HYPOTHESIS_PATH_AUDIT',
            'candidates': reports,
            'claims': {'finding_confirmed': False,
                       'severity_confirmed': False,
                       'authorization_authenticated': False,
                       'producer_identity_authenticated': False,
                       'causation_proved': False,
                       'active_testing_permitted': False}}


def review_text(result: dict) -> bytes:
    count = len(result['candidates'])
    partial = sum(bool(x['uncovered_nodes']) for x in result['candidates'])
    gaps = sum(bool(x['unsupported_observations'] or x['unsupported_declared_links'])
               for x in result['candidates'])
    return (f'# SUPERHUNTER — directed chain evidence audit\n\n'
            f'Offline candidates: {count}; partial paths: {partial}; '
            f'local evidence gaps: {gaps}.\n\n'
            'An anchored directed path is a structural witness only. It does '
            'NOT establish causal dependence, producer authenticity, authorized '
            'testing, vulnerability existence or critical impact. No systems '
            'were contacted or experiments run. The original private triage '
            'and its private source map are REQUIRED for independent replay.\n').encode()


def obtain(triage_bundle: Path, sources_file: Path) -> tuple[dict, dict, str]:
    # Critical-chain verification recursively re-opens all underlying sources.
    try:
        triage.verify(triage_bundle, sources_file)
        raw_spec = read_artifact(triage_bundle, 'input.json')
        raw_pin = read_artifact(triage_bundle, 'source-pins.json')
        raw_assessment = read_artifact(triage_bundle, 'assessment.json')
        spec = strict_json(raw_spec)
        pins = strict_json(b'{"pins":' + raw_pin.strip() + b'}')['pins']
        require(type(pins) is list, 'UPSTREAM_PIN_SCHEMA')
        assessment = strict_json(raw_assessment)
        result = compute(spec, pins, assessment)
        return result, {'schema_version': 1,
                        'triage_complete_sha256': sha(read_artifact(triage_bundle, 'COMPLETE.json')),
                        'upstream_assessment_sha256': sha(raw_assessment),
                        'upstream_pin_sha256': sha(raw_pin)}, sha(raw_spec)
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as exc:
        if type(exc) is PathAuditError:
            raise
        raise PathAuditError('UPSTREAM_VERIFICATION_REJECTED') from exc


def summary(result: dict) -> dict:
    return {'status': result['result'], 'candidates': len(result['candidates']),
            'finding_confirmed': False, 'severity_confirmed': False}


def review(triage_bundle: Path, sources_file: Path, out: Path) -> dict:
    result, source_pin, spec_sha = obtain(triage_bundle, sources_file)
    receipt = {'schema_version': 1, 'snapshot': snapshot(),
               'source_pin_sha256': sha(canonical(source_pin)),
               'input_sha256': spec_sha,
               'report_sha256': sha(canonical(result))}
    write_new_bundle(out, {'source-pin.json': canonical(source_pin),
                           'path-audit.json': canonical(result),
                           'receipt.json': canonical(receipt),
                           'REVIEW.md': review_text(result)})
    return summary(result)


def verify(bundle: Path, triage_bundle: Path, sources_file: Path) -> dict:
    require(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    require({p.name for p in bundle.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILES')
    marker = strict_json(read_artifact(bundle, 'COMPLETE.json'))
    exact_fields(marker, {'schema_version', 'sha256'}, 'MARKER_SCHEMA')
    require(type(marker['schema_version']) is int and marker['schema_version'] == 1 and
            type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
            'MARKER_CONTENTS')
    saved = {x: read_artifact(bundle, x) for x in FILES}
    require(all(marker['sha256'][x] == sha(saved[x]) for x in FILES), 'BUNDLE_TAMPERED')
    source_pin = strict_json(saved['source-pin.json'])
    result, current_pin, spec_sha = obtain(triage_bundle, sources_file)
    require(source_pin == current_pin and saved['source-pin.json'] == canonical(current_pin),
            'UPSTREAM_SOURCE_CHANGED')
    require(saved['path-audit.json'] == canonical(result), 'PATH_AUDIT_CHANGED')
    require(saved['REVIEW.md'] == review_text(result), 'REPORT_CHANGED')
    receipt = strict_json(saved['receipt.json'])
    exact_fields(receipt, {'schema_version', 'snapshot', 'source_pin_sha256',
                           'input_sha256', 'report_sha256'}, 'RECEIPT_SCHEMA')
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
            receipt['snapshot'] == snapshot() and
            receipt['source_pin_sha256'] == sha(canonical(current_pin)) and
            receipt['input_sha256'] == spec_sha and
            receipt['report_sha256'] == sha(canonical(result)), 'RECEIPT_MISMATCH')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Offline directed chain hypothesis audit')
    sub = p.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    a = sub.add_parser('audit-chain-paths')
    a.add_argument('--triage', type=Path, required=True)
    a.add_argument('--sources', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    b = sub.add_parser('verify-chain-paths')
    b.add_argument('--bundle', type=Path, required=True)
    b.add_argument('--triage', type=Path, required=True)
    b.add_argument('--sources', type=Path, required=True)
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = (review(args.triage, args.sources, args.out)
                  if args.command == 'audit-chain-paths'
                  else verify(args.bundle, args.triage, args.sources))
        print(canonical(result).decode().strip())
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, OverflowError) as exc:
        error = exc.args[0] if type(exc) is PathAuditError else 'PATH_AUDIT_REJECTED'
        print(error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
