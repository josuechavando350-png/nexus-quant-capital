"""Replay-verified, *offline* critical-impact research and chain triage.

Consumes three specific types of existing SuperHunter forensic/EVM receipts,
verifies their content via the ORIGINAL module verifiers, resolves exact event
or trace identities and ranks research hypotheses. All impact labels remain
operator CLAIMS, never confirmed findings. No network, exploit or active test.
External source bundles are deliberately NOT copied into the triage package:
the verifier must re-open those same original private bundles, supplied anew.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
from typing import Any

from . import forensic_timeline as ft
from . import journal_correlation as jc
from . import evm_bounded_replay as evm
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PROFILE = 'offline-critical-chain-research-v1'
ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ('critical_chain.py', 'forensic_timeline.py',
                'journal_correlation.py', 'evm_bounded_replay.py',
                'evm_forensic_binding.py', 'evm_opcode_trace.py',
                'safe_io.py', 'privacy.py', 'quality.py', '__main__.py')
FILES = frozenset({'input.json', 'source-pins.json', 'assessment.json',
                   'receipt.json', 'REVIEW.md'})
KINDS = frozenset({'forensic_timeline', 'journal_correlation', 'evm_bounded_replay'})
DOMAINS = frozenset({'evm', 'defi', 'web', 'api', 'cloud', 'identity', 'network',
                     'os', 'supply_chain', 'distributed', 'other'})
RELATIONS = frozenset({'enables', 'requires', 'amplifies'})
IMPACTS = {'unknown': 0, 'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
ID = re.compile(r'[a-z0-9][a-z0-9._-]{0,95}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_SOURCE = 8
MAX_OBS = 128
MAX_LINKS = 128
MAX_CANDIDATES = 32


class TriageError(ValueError):
    """Diagnostic code, never private evidence or paths."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise TriageError(code)


def fields(value: Any, keys: set[str], code: str) -> None:
    need(type(value) is dict and set(value) == keys, code)


def ident(value: Any, code: str) -> str:
    need(type(value) is str and ID.fullmatch(value) is not None, code)
    return value


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot() -> dict[str, str]:
    return {x: digest(read_artifact(ROOT, x)) for x in SOURCE_FILES}


def require_sha(x: Any, code: str) -> str:
    need(type(x) is str and SHA.fullmatch(x) is not None, code)
    return x


def parse_sources(raw: bytes) -> list[dict]:
    value = strict_json(raw)
    fields(value, {'schema_version', 'sources'}, 'SOURCE_MAP_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version'] == 1,
         'SOURCE_MAP_VERSION')
    entries = value['sources']
    need(type(entries) is list and 1 <= len(entries) <= MAX_SOURCE, 'SOURCE_COUNT')
    unique: set[str] = set()
    for entry in entries:
        fields(entry, {'source_id', 'kind', 'bundle_path'}, 'SOURCE_ITEM_SCHEMA')
        sid = ident(entry['source_id'], 'SOURCE_ID')
        need(sid not in unique, 'DUPLICATE_SOURCE_ID')
        unique.add(sid)
        need(type(entry['kind']) is str and entry['kind'] in KINDS, 'SOURCE_KIND')
        path = entry['bundle_path']
        need(type(path) is str and 0 < len(path) <= 1024 and '\x00' not in path,
             'SOURCE_PATH')
        need(Path(path).is_absolute(), 'ABSOLUTE_SOURCE_PATH_REQUIRED')
    return entries


def source_evidence(source: dict) -> dict:
    """Verify and identify exact objects in source; no inferred authenticity."""
    path = Path(source['bundle_path'])
    need(path.is_dir() and not path.is_symlink(), 'SOURCE_NOT_DIRECTORY')
    kind = source['kind']
    try:
        if kind == 'forensic_timeline':
            receipt = ft.verify(path)
            result = strict_json(read_artifact(path, 'timeline.json'))
            objects = {x['event_id']: x['record_sha256'] for x in result['timeline']}
        elif kind == 'journal_correlation':
            receipt = jc.verify(path)
            result = strict_json(read_artifact(path, 'case.json'))
            objects = {x['event_id']: x['sha256'] for x in result['event_proofs']}
        else:
            receipt = evm.verify(path)
            result = strict_json(read_artifact(path, 'semantic.json'))
            objects = {result['trace_sha256']: result['context_sha256']}
        marker_sha = digest(read_artifact(path, 'COMPLETE.json'))
    except (ValueError, UnicodeError, OSError, KeyError, TypeError, OverflowError) as exc:
        raise TriageError('SOURCE_VERIFICATION_FAILED') from exc
    need(type(receipt) is dict and type(receipt.get('status')) is str,
         'SOURCE_RECEIPT_INVALID')
    need(objects and all(type(k) is str and type(v) is str for k, v in objects.items()),
         'SOURCE_OBJECTS_INVALID')
    return {'source_id': source['source_id'], 'kind': kind,
            'complete_sha256': marker_sha, 'status': receipt['status'],
            'objects': dict(sorted(objects.items()))}


def collect_sources(entries: list[dict]) -> list[dict]:
    return sorted((source_evidence(s) for s in entries), key=lambda s: s['source_id'])


def refs(value: Any, known: dict[str, dict], code: str) -> list[dict]:
    need(type(value) is list and 0 <= len(value) <= 8, code)
    normalized = []
    found = set()
    for obj in value:
        fields(obj, {'source_id', 'object_id'}, code)
        sid, oid = ident(obj['source_id'], code), ident(obj['object_id'], code)
        # An EVM replay binds to the hex SHA of an observed trace, not to an
        # arbitrary caller-provided object name.
        if sid in known and known[sid]['kind'] == 'evm_bounded_replay':
            require_sha(oid, code)
        need(sid in known and oid in known[sid]['objects'], 'UNKNOWN_EVIDENCE_OBJECT')
        key = (sid, oid)
        need(key not in found, 'DUPLICATE_EVIDENCE_REF')
        found.add(key)
        normalized.append({'source_id': sid, 'object_id': oid,
                           'object_sha256': known[sid]['objects'][oid]})
    return sorted(normalized, key=lambda r: (r['source_id'], r['object_id']))


def validate_and_score(spec: dict, pins: list[dict]) -> dict:
    fields(spec, {'schema_version', 'profile', 'scope', 'observations',
                  'links', 'candidates'}, 'INPUT_SCHEMA')
    need(type(spec['schema_version']) is int and spec['schema_version'] == 1
         and spec['profile'] == PROFILE, 'INPUT_PROFILE')
    scope = spec['scope']
    fields(scope, {'program_id', 'scope_id', 'policy_sha256', 'authorization'},
           'SCOPE_SCHEMA')
    ident(scope['program_id'], 'PROGRAM_ID')
    ident(scope['scope_id'], 'SCOPE_ID')
    require_sha(scope['policy_sha256'], 'POLICY_SHA')
    need(type(scope['authorization']) is str and
         scope['authorization'] in ('UNVERIFIED', 'OPERATOR_DECLARED'),
         'AUTHORIZATION_DECLARATION')
    raw_obs, raw_links, raw_cases = spec['observations'], spec['links'], spec['candidates']
    need(type(raw_obs) is list and 1 <= len(raw_obs) <= MAX_OBS, 'OBSERVATION_COUNT')
    need(type(raw_links) is list and len(raw_links) <= MAX_LINKS, 'LINK_COUNT')
    need(type(raw_cases) is list and 1 <= len(raw_cases) <= MAX_CANDIDATES,
         'CANDIDATE_COUNT')
    known = {x['source_id']: x for x in pins}
    obs: dict[str, dict] = {}
    for item in raw_obs:
        fields(item, {'observation_id', 'asset_id', 'domain', 'impact_hint',
                      'evidence_refs'}, 'OBSERVATION_SCHEMA')
        oid = ident(item['observation_id'], 'OBSERVATION_ID')
        ident(item['asset_id'], 'ASSET_ID')
        need(oid not in obs, 'DUPLICATE_OBSERVATION')
        need(type(item['domain']) is str and item['domain'] in DOMAINS, 'DOMAIN')
        need(type(item['impact_hint']) is str and item['impact_hint'] in IMPACTS,
             'IMPACT_HINT')
        obs[oid] = {'refs': refs(item['evidence_refs'], known, 'OBSERVATION_REFS'),
                    'impact_hint': item['impact_hint'], 'domain': item['domain']}
    links: dict[tuple[str, str], dict] = {}
    for link in raw_links:
        fields(link, {'from', 'to', 'relation', 'evidence_refs'}, 'LINK_SCHEMA')
        a, b = ident(link['from'], 'LINK_SOURCE'), ident(link['to'], 'LINK_TARGET')
        need(a in obs and b in obs and a != b, 'LINK_ENDPOINT')
        need(type(link['relation']) is str and link['relation'] in RELATIONS,
             'LINK_RELATION')
        need((a, b) not in links, 'DUPLICATE_LINK')
        links[(a, b)] = {'relation': link['relation'],
                         'refs': refs(link['evidence_refs'], known, 'LINK_REFS')}
    # Strict DAG: cycles cannot be interpreted as a demonstrated attack chain.
    remaining = {o: 0 for o in obs}
    outgoing = {o: [] for o in obs}
    for a, b in links:
        remaining[b] += 1
        outgoing[a].append(b)
    queue = sorted(o for o, n in remaining.items() if n == 0)
    visited = 0
    while queue:
        o = queue.pop(0)
        visited += 1
        for b in sorted(outgoing[o]):
            remaining[b] -= 1
            if remaining[b] == 0:
                queue.append(b)
        queue.sort()
    need(visited == len(obs), 'CHAIN_CYCLE')
    seen = set()
    results = []
    contradicted = {p['source_id'] for p in pins if p['status'] ==
                    'DECLARED_CONSTRAINT_CONTRADICTION'}
    for item in raw_cases:
        fields(item, {'candidate_id', 'observation_ids', 'kind', 'potential_impact',
                      'lab_cost_units'}, 'CANDIDATE_SCHEMA')
        cid = ident(item['candidate_id'], 'CANDIDATE_ID')
        need(cid not in seen, 'DUPLICATE_CANDIDATE')
        seen.add(cid)
        nodes = item['observation_ids']
        need(type(nodes) is list and 1 <= len(nodes) <= 12 and
             all(type(x) is str and x in obs for x in nodes) and
             len(set(nodes)) == len(nodes), 'CANDIDATE_OBSERVATIONS')
        need(type(item['kind']) is str and item['kind'] in ('single', 'chain') and
             (len(nodes) == 1 if item['kind'] == 'single' else len(nodes) >= 2),
             'CANDIDATE_KIND')
        need(type(item['potential_impact']) is str and
             item['potential_impact'] in IMPACTS, 'CANDIDATE_IMPACT')
        cost = item['lab_cost_units']
        need(type(cost) is int and 0 <= cost <= 100, 'LAB_COST')
        selected = set(nodes)
        edges = [(a, b, v) for (a, b), v in links.items()
                 if a in selected and b in selected]
        if len(nodes) > 1:
            # Undirected connectedness of an acyclic directed prerequisite graph.
            neighbours = {x: set() for x in nodes}
            for a, b, _ in edges:
                neighbours[a].add(b)
                neighbours[b].add(a)
            reached, todo = set(), [nodes[0]]
            while todo:
                n = todo.pop()
                if n not in reached:
                    reached.add(n)
                    todo.extend(neighbours[n] - reached)
            need(reached == selected, 'DISCONNECTED_CHAIN')
        def reliable(rs: list[dict]) -> bool:
            return any(r['source_id'] not in contradicted for r in rs)
        grounded = sum(reliable(obs[x]['refs']) for x in nodes)
        grounded_edges = sum(reliable(v['refs']) for _, _, v in edges)
        missing = (len(nodes) - grounded) + (len(edges) - grounded_edges)
        # This numeric score is a deterministic research order, *not* a
        # calibrated probability, CVSS value, economic impact or severity.
        impact_weight = (50, 150, 400, 700, 1000)[IMPACTS[item['potential_impact']]]
        score = max(0, impact_weight + 30*grounded + 12*grounded_edges +
                    (40 if len(nodes) > 1 else 0) - 100*missing - cost)
        if scope['authorization'] == 'UNVERIFIED':
            status = 'NEEDS_SCOPE_REVIEW'
        elif missing:
            status = 'NEEDS_EVIDENCE'
        else:
            status = 'READY_FOR_AUTHORIZED_LAB_REVIEW'
        results.append({'candidate_id': cid, 'kind': item['kind'],
                        'potential_impact': item['potential_impact'],
                        'priority_score': score, 'status': status,
                        'observation_count': len(nodes),
                        'linked_steps': len(edges), 'grounded_observations': grounded,
                        'evidence_backed_links_not_causation': grounded_edges,
                        'missing_evidence_slots': missing,
                        'critical_impact_confirmed': False,
                        'vulnerability_confirmed': False,
                        'authorized_active_testing': False})
    results.sort(key=lambda row: (-row['priority_score'], row['candidate_id']))
    return {'schema_version': 1, 'profile': PROFILE,
            'status': 'OFFLINE_RESEARCH_TRIAGE_ONLY',
            'scope_id': scope['scope_id'], 'program_id': scope['program_id'],
            'source_count': len(pins), 'observation_count': len(obs),
            'candidate_count': len(results), 'ranked_candidates': results,
            'claims': {'critical_impact_confirmed': False,
                       'vulnerability_confirmed': False,
                       'causation_proved': False,
                       'producer_identity_authenticated': False,
                       'authorization_authenticated': False,
                       'active_testing_permitted': False,
                       'vulnerability_severity_calibrated': False}}


def report(result: dict) -> bytes:
    return (f'# SUPERHUNTER — offline critical-chain research triage\n\n'
            f'Verdict: {result["status"]}. Sources: {result["source_count"]}; '
            f'observations: {result["observation_count"]}; '
            f'candidates: {result["candidate_count"]}.\n\n'
            'Scores rank hypotheses for laboratory investigation, not confirmed '
            'severity or exploitation feasibility. Sources are locally replay-' 
            'verified but their producers, timestamps, assets and claimed '
            'relationships are not authenticated. A low+medium chain with '
            'potentially critical impact is a research candidate, NOT a '
            'critical finding. No tests run on external systems. '
            'Verification requires the exact original private source bundles.\n').encode()


def summary(result: dict) -> dict:
    return {'status': result['status'], 'sources': result['source_count'],
            'observations': result['observation_count'],
            'candidates': result['candidate_count'],
            'critical_impact_confirmed': False, 'vulnerability_confirmed': False}


def review(input_file: Path, sources_file: Path, output: Path) -> dict:
    raw = read_artifact(input_file.parent, input_file.name)
    spec = strict_json(raw)
    source_specs = parse_sources(read_artifact(sources_file.parent, sources_file.name))
    pins = collect_sources(source_specs)
    result = validate_and_score(spec, pins)
    receipt = {'schema_version': 1, 'input_sha256': digest(raw),
               'sources_sha256': digest(canonical(pins)),
               'assessment_sha256': digest(canonical(result)),
               'source_snapshot': snapshot()}
    write_new_bundle(output, {'input.json': raw,
                              'source-pins.json': canonical(pins),
                              'assessment.json': canonical(result),
                              'receipt.json': canonical(receipt),
                              'REVIEW.md': report(result)})
    return summary(result)


def verify(bundle: Path, sources_file: Path) -> dict:
    need(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    need({x.name for x in bundle.iterdir()} == FILES | {'COMPLETE.json'},
         'BUNDLE_FILES')
    marker = strict_json(read_artifact(bundle, 'COMPLETE.json'))
    fields(marker, {'schema_version', 'sha256'}, 'MANIFEST_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
         'MANIFEST_VERSION')
    saved = {x: read_artifact(bundle, x) for x in FILES}
    need(all(marker['sha256'][x] == digest(saved[x]) for x in FILES),
         'ARTIFACT_TAMPERED')
    receipt = strict_json(saved['receipt.json'])
    fields(receipt, {'schema_version', 'input_sha256', 'sources_sha256',
                     'assessment_sha256', 'source_snapshot'}, 'RECEIPT_SCHEMA')
    need(type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
         receipt['source_snapshot'] == snapshot(), 'SOURCE_CHANGED')
    need(receipt['input_sha256'] == digest(saved['input.json']), 'INPUT_CHANGED')
    source_specs = parse_sources(read_artifact(sources_file.parent, sources_file.name))
    pins = collect_sources(source_specs)
    need(saved['source-pins.json'] == canonical(pins) and
         receipt['sources_sha256'] == digest(canonical(pins)), 'EXTERNAL_SOURCES_CHANGED')
    result = validate_and_score(strict_json(saved['input.json']), pins)
    need(saved['assessment.json'] == canonical(result) and
         receipt['assessment_sha256'] == digest(canonical(result)),
         'ASSESSMENT_CHANGED')
    need(saved['REVIEW.md'] == report(result), 'REPORT_CHANGED')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Offline evidence-bound critical chain triage')
    sub = p.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    a = sub.add_parser('triage-critical-chains')
    a.add_argument('--input', type=Path, required=True)
    a.add_argument('--sources', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    b = sub.add_parser('verify-critical-triage')
    b.add_argument('--bundle', type=Path, required=True)
    b.add_argument('--sources', type=Path, required=True)
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = (review(args.input, args.sources, args.out)
                  if args.command == 'triage-critical-chains'
                  else verify(args.bundle, args.sources))
        print(canonical(result).decode().strip())
        return 0
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, OverflowError) as exc:
        error = exc.args[0] if type(exc) is TriageError else 'TRIAGE_REJECTED'
        print(error, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
