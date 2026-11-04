"""Capa 0 · Modelos de dominio de la jaula.

Dataclasses planas y un par de enums. No tienen lógica de red: son el
vocabulario compartido que usan `scope`, `ratelimit` y `audit`, y que
usarán las capas futuras (observador, motores, fork-validador...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Decision(Enum):
    """Veredicto binario de la jaula: dentro o fuera de alcance."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class Severity(str, Enum):
    """Severidad de un hallazgo (escala tipo Immunefi)."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Target:
    """Algo contra lo que el sistema podría actuar.

    `value` es el identificador que se compara con el scope: un host
    (`a.x.com`), una IP (`10.0.0.9`) o una dirección de contrato
    (`0xabc...`). `kind` deja claro cómo interpretarlo.
    """

    value: str
    kind: str = "host"  # "host" | "ip" | "contract"
    chain: str | None = None
    label: str | None = None

    def normalized(self) -> str:
        """Forma canónica para comparar: sin espacios, sin punto final, minúsculas."""
        return self.value.strip().rstrip(".").lower()


@dataclass(frozen=True)
class Contract:
    """Un contrato Web3 in-scope (el objeto real del nicho Immunefi)."""

    address: str
    chain: str
    name: str | None = None
    verified: bool = False

    def as_target(self) -> Target:
        return Target(value=self.address, kind="contract", chain=self.chain, label=self.name)


@dataclass(frozen=True)
class Verdict:
    """Resultado de `ScopeGuard.check`: decisión + por qué."""

    decision: Decision
    target: Target
    reason: str
    matched_rule: str | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class Finding:
    """Un hallazgo de vulnerabilidad (lo que el humano firma y envía)."""

    id: str
    title: str
    severity: Severity
    target: Target
    description: str = ""
    invariant: str | None = None
    poc_ref: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)


@dataclass
class Report:
    """Paquete de hallazgos para un programa."""

    program: str
    author: str
    findings: list[Finding] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now_iso)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def __len__(self) -> int:
        return len(self.findings)
