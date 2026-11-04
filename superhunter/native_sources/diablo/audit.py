"""Capa 0 · AuditLog — bitácora inmutable con hash encadenado.

Cada entrada incluye el hash de la anterior (como una mini-blockchain), de
modo que alterar cualquier entrada rompe la cadena de forma detectable.
Es la prueba de que, si algún día hace falta, se actuó dentro de lo permitido.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

GENESIS_PREV = "0" * 64


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_hash(index: int, timestamp: str, event: str, data: dict, prev_hash: str) -> str:
    """Hash canónico y determinista de una entrada, ligado al hash previo."""
    payload = json.dumps(
        {
            "index": index,
            "timestamp": timestamp,
            "event": event,
            "data": data,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    index: int
    timestamp: str
    event: str
    data: dict
    prev_hash: str
    hash: str

    def recompute(self) -> str:
        return compute_hash(self.index, self.timestamp, self.event, self.data, self.prev_hash)


@dataclass
class VerifyResult:
    ok: bool
    broken_index: int | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.ok


class AuditError(RuntimeError):
    pass


class AuditLog:
    """Cadena de entradas append-only, verificable de punta a punta."""

    def __init__(self, *, path: str | Path | None = None, clock: Callable[[], str] = _utc_now_iso) -> None:
        self._entries: list[AuditEntry] = []
        self._clock = clock
        self._path = Path(path) if path else None

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS_PREV

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, event: str, data: dict[str, Any] | None = None) -> AuditEntry:
        index = len(self._entries)
        prev = self.head
        timestamp = self._clock()
        payload = dict(data or {})
        digest = compute_hash(index, timestamp, event, payload, prev)
        entry = AuditEntry(index, timestamp, event, payload, prev, digest)
        self._entries.append(entry)
        if self._path is not None:
            self._persist(entry)
        return entry

    def verify(self) -> VerifyResult:
        """Recorre la cadena y confirma que no fue alterada."""
        prev = GENESIS_PREV
        for i, entry in enumerate(self._entries):
            if entry.index != i:
                return VerifyResult(False, i, "index out of order")
            if entry.prev_hash != prev:
                return VerifyResult(False, i, "broken previous-hash link")
            if entry.recompute() != entry.hash:
                return VerifyResult(False, i, "entry hash mismatch (tampered content)")
            prev = entry.hash
        return VerifyResult(True)

    def assert_intact(self) -> None:
        result = self.verify()
        if not result.ok:
            raise AuditError(f"audit chain broken at #{result.broken_index}: {result.reason}")

    # ---- persistencia opcional (JSONL) ----------------------------------
    def _persist(self, entry: AuditEntry) -> None:
        assert self._path is not None
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry), default=str) + "\n")

    @classmethod
    def load(cls, path: str | Path, *, clock: Callable[[], str] = _utc_now_iso) -> "AuditLog":
        log = cls(path=None, clock=clock)
        p = Path(path)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                log._entries.append(AuditEntry(**json.loads(line)))
        log._path = p
        return log
