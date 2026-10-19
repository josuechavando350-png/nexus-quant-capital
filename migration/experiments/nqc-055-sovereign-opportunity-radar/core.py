"""Small offline evidence and interval kernel; no transport, signing or execution."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Protocol

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse(raw):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            require(k not in out, 'duplicate JSON identifier')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=unique)


def integer(value):
    if type(value) is str and re.fullmatch(r'0|[1-9][0-9]*', value):
        value = int(value)
    require(type(value) is int and value >= 0, 'exact nonnegative integer required')
    return value


def units(text, decimals):
    """Reject floats, exponents, signs and any precision beyond the asset scale."""
    require(type(text) is str and re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?', text), 'decimal string required')
    require(type(decimals) is int and 0 <= decimals <= 255, 'invalid decimals')
    whole, _, tail = text.partition('.')
    require(len(tail) <= decimals, 'precision exceeds asset decimals')
    return int(whole) * 10**decimals + int(tail.ljust(decimals, '0') or '0')


@dataclass(frozen=True)
class Asset:
    chain: int
    address: str
    decimals: int

    def __post_init__(self):
        require(type(self.chain) is int and self.chain > 0, 'chain identity')
        require(self.address == 'native:ETH' or bool(re.fullmatch(r'0x[0-9a-f]{40}', self.address)), 'asset identity')
        require(type(self.decimals) is int and 0 <= self.decimals <= 255, 'asset scale')

    def json(self):
        return {'chain_id': self.chain, 'address': self.address, 'decimals': self.decimals}


@dataclass(frozen=True)
class Interval:
    asset: Asset
    lower: int | None
    upper: int | None
    refs: tuple

    def __post_init__(self):
        for value in (self.lower, self.upper):
            require(value is None or type(value) is int and value >= 0, 'interval exact units')
        require(self.lower is None or self.upper is None or self.lower <= self.upper, 'inverted interval')
        require(bool(self.refs), 'missing interval provenance')


@dataclass(frozen=True)
class Cost:
    name: str
    category: str
    amount: Interval
    covers: frozenset


REQUIRED_COSTS = frozenset({'debt', 'gas', 'financing', 'inclusion', 'failures', 'operations', 'other'})


def bounds(sale, costs, *, sale_kind='realized_sale_output', embedded=frozenset(), hypothetical=False):
    """Interval subtraction. Unknown liability upper bounds leave net lower unknown.

    A zero lower bound on a nonnegative unknown cost is a mathematical bound,
    never a claim that the actual cost is zero. This kernel grants no admission.
    """
    require(sale_kind == 'realized_sale_output', 'advance or collateral is not sale income')
    require({c.category for c in costs} >= REQUIRED_COSTS, 'missing cost categories')
    covered, names = set(embedded), set()
    for c in costs:
        require(c.name not in names, 'duplicate cost identifier')
        require(c.amount.asset == sale.asset, 'asset/chain/decimal mismatch')
        require(c.covers and not covered.intersection(c.covers), 'double-counted economic component')
        covered.update(c.covers); names.add(c.name)
    upper = None if sale.upper is None or any(c.amount.lower is None for c in costs) else sale.upper - sum(c.amount.lower for c in costs)
    lower = None if sale.lower is None or any(c.amount.upper is None for c in costs) else sale.lower - sum(c.amount.upper for c in costs)
    decision = 'DESCARTADO_DENTRO_DE_CONDICIONES' if upper is not None and upper <= 0 else 'EVIDENCIA_INSUFICIENTE'
    return {'asset': sale.asset.json(), 'net_lower_raw': None if lower is None else str(lower),
        'net_upper_raw': None if upper is None else str(upper), 'decision': decision,
        'hypothetical_conditions': hypothetical, 'nqc_captured_net': None, 'commercial_admission': False,
        'unbounded_costs': sorted(c.name for c in costs if c.amount.upper is None),
        'embedded_effects_not_subtracted_again': sorted(embedded),
        'costs': [{'name': c.name, 'category': c.category, 'lower_raw': None if c.amount.lower is None else str(c.amount.lower),
            'upper_raw': None if c.amount.upper is None else str(c.amount.upper), 'refs': list(c.amount.refs),
            'covers': sorted(c.covers), 'unknown_is_not_zero': c.amount.lower != c.amount.upper} for c in costs],
        'sale_refs': list(sale.refs)}


class Sources:
    def __init__(self, manifest=None):
        self.manifest = manifest or parse((HERE/'SOURCE_MANIFEST.json').read_bytes())
        self.cache = {}

    def raw(self, name):
        if name not in self.cache:
            p = self.manifest['files'][name]
            require(bool(re.fullmatch('[0-9a-f]{40}', p['commit'])), 'unpinned commit')
            raw = subprocess.check_output(['git', '-C', str(REPO), 'show', p['commit']+':'+p['path']])
            require(len(raw) == p['bytes'] and hashlib.sha256(raw).hexdigest() == p['sha256'], 'source hash mismatch')
            require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == p['git_blob_sha1'], 'source blob mismatch')
            self.cache[name] = raw
        return self.cache[name]

    def json(self, name):
        return parse(self.raw(name))

    def ref(self, name, pointer=''):
        value = self.json(name) if pointer else None
        if pointer:
            require(pointer.startswith('/'), 'JSON pointer')
            for part in pointer[1:].split('/'):
                part = part.replace('~1', '/').replace('~0', '~')
                value = value[int(part)] if isinstance(value, list) else value[part]
        else:
            self.raw(name)
        return {'source': name, 'pointer': pointer, 'sha256': self.manifest['files'][name]['sha256']}

    def verify_all(self):
        for name in sorted(self.manifest['files']):
            self.raw(name)
        return len(self.cache)


class Adapter(Protocol):
    family: str
    def candidates(self, sources: Sources) -> list[dict]: ...
    def evaluate(self, sources: Sources, candidates: list[dict]) -> list[dict]: ...


class Registry:
    """One case per chain/protocol/transaction; events are not independent P&Ls."""
    def __init__(self):
        self.rows = {}
        self.duplicates = 0

    def add(self, candidate):
        require(bool(re.fullmatch(r'0x[0-9a-f]{64}', candidate['tx_hash'])), 'transaction hash identity')
        identity = f"eip155:{candidate['chain_id']}/{candidate['protocol']}/{candidate['tx_hash']}"
        require(candidate['id'] == identity, 'candidate identifier conflict')
        require(type(candidate['chain_id']) is int and candidate['chain_id'] > 0, 'invalid candidate chain')
        require(candidate['commercial_admission'] is False and candidate['NQC_capture_demonstrated'] is False,
                'offline adapter cannot grant commercial admission or capture')
        if identity in self.rows:
            previous = self.rows[identity]
            require(digest(previous) == digest(candidate), 'conflicting duplicate dossier')
            self.duplicates += 1
        else:
            self.rows[identity] = candidate

    def ordered(self):
        return [self.rows[k] for k in sorted(self.rows)]
