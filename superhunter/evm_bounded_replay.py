"""Independent, STRICTLY BOUNDED EVM stack/PC replay for owned forensic traces.

A second interpreter of a small, stateless EVM opcode subset checks full step
order and stack operands. It neither invokes Geth nor trusts supplied stack
values, gas charges, execution timestamps, or producer identity. Unsupported
opcodes fail closed rather than being reported as replayed.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import sys
from typing import Any

from . import evm_forensic_binding as bridge
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-offline-bounded-evm-stack-pc-replay-v1'
SOURCE_FILES = ('evm_bounded_replay.py', 'evm_forensic_binding.py',
                'evm_opcode_trace.py', 'safe_io.py', 'privacy.py',
                'quality.py', '__main__.py')
# Copy the complete previous PRIVATE receipt, but use a different name for its
# COMPLETE marker so the new package has exactly one authoritative manifest.
PARENT = frozenset(bridge.FILES)
PAYLOAD = PARENT | {'parent-complete.json', 'semantic.json',
                    'replay-receipt.json', 'REPLAY.md'}
MASK = (1 << 256) - 1
MAX_STEPS = 4096
MAX_STACK = 1024
BINARY = {0x01: 'ADD', 0x02: 'MUL', 0x03: 'SUB',
          0x10: 'LT', 0x11: 'GT', 0x14: 'EQ', 0x16: 'AND',
          0x17: 'OR', 0x18: 'XOR', 0x1b: 'SHL', 0x1c: 'SHR'}
UNARY = {0x15: 'ISZERO', 0x19: 'NOT'}


class ReplayError(ValueError):
    """Safe, fixed diagnostic codes only. Never echo private log bytes."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ReplayError(code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot() -> dict[str, str]:
    return {path: sha(read_artifact(ROOT, path)) for path in SOURCE_FILES}


def instructions(code: bytes) -> dict[int, int]:
    """Independent opcode map; PUSH payload is not executable."""
    need(0 < len(code) <= 32000, 'CODE_LIMIT')
    positions = {}
    pc = 0
    while pc < len(code):
        op = code[pc]
        width = op - 0x5f if 0x60 <= op <= 0x7f else 0
        need(pc + 1 + width <= len(code), 'TRUNCATED_PUSH')
        positions[pc] = op
        pc += 1 + width
    return positions


def trace_steps(raw: bytes) -> tuple[list[dict], dict]:
    need(type(raw) is bytes and 0 < len(raw) <= 2_000_000, 'TRACE_LIMIT')
    lines = raw.splitlines()
    need(2 <= len(lines) <= MAX_STEPS + 1, 'REPLAY_STEP_LIMIT')
    rows = [strict_json(line) for line in lines]
    steps = rows[:-1]
    for row in steps:
        need(type(row.get('pc')) is int and type(row.get('op')) is int,
             'TRACE_PC_OP')
    terminal = rows[-1]
    need(set(terminal) in ({'output', 'gasUsed'}, {'output', 'gasUsed', 'error'}),
         'TERMINAL_SCHEMA')
    return steps, terminal


def replay(trace_raw: bytes, context_raw: bytes) -> dict:
    """Check every observed instruction against a *computed* stack/PC path.

    This checks no gas-cost table and cannot prove who created a trace. It
    rejects memory/storage/call/environmental ops, RETURN/REVERT and all
    semantics outside this strict subset rather than approximating them.
    """
    context = bridge.context_fields(strict_json(context_raw))
    code = bytes.fromhex(context['bytecode_hex'])
    sites = instructions(code)
    steps, terminal = trace_steps(trace_raw)
    need(terminal.get('error') is None and terminal['output'] == '' and
         context['observed'] == {'return_data': '0x', 'error': None},
         'ONLY_SUCCESSFUL_STOP_PROFILE')
    stack: list[int] = []
    pc, terminated = 0, False
    counts: Counter[str] = Counter()
    jump_edges = []
    visited = []

    def pop() -> int:
        need(bool(stack), 'STACK_UNDERFLOW')
        return stack.pop()

    for idx, row in enumerate(steps):
        need(not terminated, 'TRACE_AFTER_STOP')
        need(pc in sites and row['pc'] == pc and row['op'] == sites[pc],
             'SEMANTIC_PC_MISMATCH')
        op = sites[pc]
        visited.append(pc)
        next_pc = pc + 1
        if op == 0x00:
            counts['STOP'] += 1
            terminated = True
            need(idx == len(steps) - 1, 'TRACE_AFTER_STOP')
        elif op == 0x5f:
            stack.append(0)
            counts['PUSH0'] += 1
        elif 0x60 <= op <= 0x7f:
            width = op - 0x5f
            stack.append(int.from_bytes(code[next_pc:next_pc + width], 'big'))
            next_pc += width
            counts['PUSH'] += 1
        elif op == 0x50:
            pop()
            counts['POP'] += 1
        elif 0x80 <= op <= 0x8f:
            depth = op - 0x7f
            need(len(stack) >= depth, 'STACK_UNDERFLOW')
            stack.append(stack[-depth])
            counts['DUP'] += 1
        elif 0x90 <= op <= 0x9f:
            depth = op - 0x8f
            need(len(stack) > depth, 'STACK_UNDERFLOW')
            stack[-1], stack[-1-depth] = stack[-1-depth], stack[-1]
            counts['SWAP'] += 1
        elif op in BINARY:
            a, b = pop(), pop()
            result = {
                0x01: lambda: (a + b) & MASK,
                0x02: lambda: (a * b) & MASK,
                0x03: lambda: (a - b) & MASK,
                0x10: lambda: int(a < b),
                0x11: lambda: int(a > b),
                0x14: lambda: int(a == b),
                0x16: lambda: a & b,
                0x17: lambda: a | b,
                0x18: lambda: a ^ b,
                0x1b: lambda: ((b << a) & MASK) if a < 256 else 0,
                0x1c: lambda: (b >> a) if a < 256 else 0,
            }[op]()
            stack.append(result)
            counts[BINARY[op]] += 1
        elif op in UNARY:
            a = pop()
            stack.append(int(a == 0) if op == 0x15 else (MASK ^ a))
            counts[UNARY[op]] += 1
        elif op == 0x5b:
            counts['JUMPDEST'] += 1
        elif op in (0x56, 0x57):
            dest = pop()
            cond = pop() if op == 0x57 else 1
            if cond != 0:
                need(dest in sites and sites[dest] == 0x5b, 'INVALID_JUMPDEST')
                next_pc = dest
            jump_edges.append({'at_pc': pc, 'next_pc': next_pc,
                               'taken': bool(cond)})
            counts['JUMP' if op == 0x56 else 'JUMPI'] += 1
        else:
            raise ReplayError('UNSUPPORTED_OPCODE')
        need(len(stack) <= MAX_STACK, 'STACK_OVERFLOW')
        pc = next_pc
    need(terminated, 'TRACE_DID_NOT_REACH_STOP')
    return {'schema_version': 1, 'profile': PROFILE,
            'status': 'BOUNDED_STACK_PC_REPLAY_MATCH',
            'trace_sha256': sha(trace_raw), 'context_sha256': sha(context_raw),
            'step_count': len(steps), 'unique_pc_count': len(set(visited)),
            'pc_sequence_sha256': sha(canonical(visited)),
            'opcode_counts': dict(sorted(counts.items())),
            'computed_jump_edges': jump_edges,
            'claims': {'bounded_stack_pc_semantics_replayed': True,
                       'full_evm_execution_replayed': False,
                       'native_evm_engine_invoked': False,
                       'gas_costs_replayed': False,
                       'storage_memory_environment_replayed': False,
                       'source_and_trace_producer_authenticated': False,
                       'journal_time_authenticated': False,
                       'incident_confirmed': False,
                       'vulnerability_confirmed': False}}


def verified_parent(content: dict[str, bytes]) -> dict:
    """Reconstruct the preceding bridge verdict from preserved ORIGINAL bytes."""
    need(set(content) == PARENT | {'parent-complete.json'}, 'PARENT_FILES')
    marker = strict_json(content['parent-complete.json'])
    need(type(marker) is dict and set(marker) == {'schema_version', 'sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == PARENT,
         'PARENT_MANIFEST')
    need(all(marker['sha256'].get(name) == sha(content[name]) for name in PARENT),
         'PARENT_BYTES_TAMPERED')
    receipt = strict_json(content['receipt.json'])
    need(type(receipt) is dict and set(receipt) == {
        'schema_version', 'source_snapshot', 'finding_sha256',
        'source_bundle_complete_sha256'} and
         type(receipt['schema_version']) is int and receipt['schema_version'] == 1,
         'PARENT_RECEIPT')
    need(receipt['source_snapshot'] == bridge.source_snapshot(), 'PARENT_SOURCE_CHANGED')
    prior = bridge.analyze(content['trace.jsonl'], content['context.json'],
                           content['journal.jsonl'], content['metadata.json'])
    need(content['finding.json'] == canonical(prior) and
         receipt['finding_sha256'] == sha(canonical(prior)) and
         content['REVIEW.md'] == bridge.render(prior), 'PARENT_DERIVED_DATA')
    need(type(receipt['source_bundle_complete_sha256']) is str and
         bridge.ft.HEX64.fullmatch(receipt['source_bundle_complete_sha256']) is not None,
         'PARENT_RECEIPT_REFERENCE')
    return prior


def render(result: dict) -> bytes:
    return (f'# SUPERHUNTER — independent bounded EVM stack/PC replay\n\n'
            f"Status: **{result['status']}**. Observed steps verified: "
            f"{result['step_count']}; unique PCs: {result['unique_pc_count']}.\n\n"
            'An independent, bounded interpreter recomputed stack operands, '
            'PUSH data, jumps and complete PC sequence through STOP. No Geth, '
            'RPC, network, gas-cost computation, storage, memory or external '
            'state was executed. A fabricated trace can satisfy these rules; '
            'neither log/trace producer nor execution timestamp is authenticated. '
            'No incident, vulnerability, general EVM equivalence or original '
            'finding is claimed. Original evidence remains PRIVATE.\n').encode()


def summary(result: dict) -> dict:
    return {'status': result['status'], 'step_count': result['step_count'],
            'bounded_stack_pc_semantics_replayed': True,
            'full_evm_execution_replayed': False,
            'vulnerability_confirmed': False}


def review(parent: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'PRIVATE_NEW_OUTPUT_REQUIRED')
    need(parent.is_dir() and not parent.is_symlink(), 'PARENT_DIRECTORY')
    try:
        bridge.verify(parent)
    except (ValueError, OSError, TypeError) as exc:
        raise ReplayError('PARENT_VERIFICATION_FAILED') from exc
    source = snapshot()
    content = {name: read_artifact(parent, name) for name in PARENT}
    content['parent-complete.json'] = read_artifact(parent, 'COMPLETE.json')
    verified_parent(content)
    result = replay(content['trace.jsonl'], content['context.json'])
    need(snapshot() == source, 'SOURCE_CHANGED_DURING_REVIEW')
    receipt = {'schema_version': 1, 'source_snapshot': source,
               'parent_complete_sha256': sha(content['parent-complete.json']),
               'semantic_sha256': sha(canonical(result))}
    content.update({'semantic.json': canonical(result),
                    'replay-receipt.json': canonical(receipt),
                    'REPLAY.md': render(result)})
    write_new_bundle(out, content)
    return summary(result)


def verify(out: Path, expected_complete_sha256: str | None = None) -> dict:
    need(out.is_dir() and not out.is_symlink(), 'BUNDLE_DIRECTORY')
    marker_raw = read_artifact(out, 'COMPLETE.json')
    if expected_complete_sha256 is not None:
        need(type(expected_complete_sha256) is str and
             bridge.ft.HEX64.fullmatch(expected_complete_sha256) is not None and
             sha(marker_raw) == expected_complete_sha256, 'EXTERNAL_SHA_MISMATCH')
    marker = strict_json(marker_raw)
    need(type(marker) is dict and set(marker) == {'schema_version', 'sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == PAYLOAD and
         {p.name for p in out.iterdir()} == PAYLOAD | {'COMPLETE.json'},
         'BUNDLE_MANIFEST')
    content = {name: read_artifact(out, name) for name in PAYLOAD}
    need(all(marker['sha256'][name] == sha(raw) for name, raw in content.items()),
         'BUNDLE_TAMPERED')
    receipt = strict_json(content['replay-receipt.json'])
    need(type(receipt) is dict and set(receipt) == {
        'schema_version', 'source_snapshot', 'parent_complete_sha256', 'semantic_sha256'} and
         type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
         receipt['source_snapshot'] == snapshot(), 'SOURCE_CHANGED')
    verified_parent({key: content[key] for key in PARENT | {'parent-complete.json'}})
    result = replay(content['trace.jsonl'], content['context.json'])
    need(receipt['parent_complete_sha256'] == sha(content['parent-complete.json']),
         'PARENT_DIGEST_MISMATCH')
    need(content['semantic.json'] == canonical(result) and
         receipt['semantic_sha256'] == sha(canonical(result)), 'REPLAY_RESULT_MISMATCH')
    need(content['REPLAY.md'] == render(result), 'REPLAY_REPORT_MISMATCH')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Bounded offline stack and PC replay, own EVM traces')
    sub = p.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    a = sub.add_parser('replay-evm-forensic')
    a.add_argument('--bundle', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    b = sub.add_parser('verify-evm-replay')
    b.add_argument('--bundle', type=Path, required=True)
    b.add_argument('--expected-complete-sha256', default=None)
    args = p.parse_args(argv)
    try:
        result = (review(args.bundle, args.out)
                  if args.command == 'replay-evm-forensic'
                  else verify(args.bundle, args.expected_complete_sha256))
        print(canonical(result).decode().strip())
        return 0
    except (ValueError, OSError, TypeError, UnicodeError, OverflowError) as exc:
        code = exc.args[0] if type(exc) is ReplayError else 'BOUNDED_EVM_REPLAY_REJECTED'
        print(code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
