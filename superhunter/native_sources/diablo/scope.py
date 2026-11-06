"""Capa 0 · ScopeGuard — la puerta de la jaula.

Reglas duras, no negociables:

* **default-deny:** lo que no está declarado explícitamente in-scope NO existe.
* **OUT gana sobre IN siempre:** si un target cae en una regla out-scope, se
  deniega aunque también caiga en una regla in-scope.
* El wildcard `*.x.com` cubre `a.x.com` y `a.b.x.com` pero NUNCA la raíz
  `x.com`, y nunca el truco de sufijo `app.x.com.attacker.net`.

Invariante del sistema completo: ninguna capa futura abre un socket sin
llamar antes a `ScopeGuard.assert_allowed(target)`.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from .audit import AuditLog
from .models import Decision, Target, Verdict

_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class _NormTarget:
    """Target normalizado para comparar contra reglas."""

    host: str
    ip: _IPAddress | None


def _norm(target: Target) -> _NormTarget:
    raw = target.value.strip()
    try:
        ip: _IPAddress | None = ipaddress.ip_address(raw)
    except ValueError:
        ip = None
    return _NormTarget(host=raw.rstrip(".").lower(), ip=ip)


@dataclass(frozen=True)
class _Rule:
    """Una entrada de scope, ya clasificada en wildcard / network / literal."""

    raw: str
    kind: str  # "wildcard" | "network" | "literal"
    domain: str | None = None
    network: _IPNetwork | None = None
    literal: str | None = None

    @classmethod
    def parse(cls, raw: str) -> "_Rule":
        s = str(raw).strip()
        low = s.lower().rstrip(".")
        if low.startswith("*."):
            return cls(raw=s, kind="wildcard", domain=low[2:])
        try:
            net = ipaddress.ip_network(s, strict=False)
            return cls(raw=s, kind="network", network=net)
        except ValueError:
            return cls(raw=s, kind="literal", literal=low)

    def matches(self, t: _NormTarget) -> bool:
        if self.kind == "network":
            assert self.network is not None
            return t.ip is not None and t.ip in self.network
        # Las reglas de host nunca matchean una IP cruda.
        if t.ip is not None:
            return False
        if self.kind == "wildcard":
            assert self.domain is not None
            # Subdominio propio: termina en ".<domain>".
            # Esto excluye la raíz ("x.com" no termina en ".x.com") y
            # el truco de sufijo ("app.x.com.attacker.net" termina en
            # ".attacker.net", no en ".x.com").
            return t.host.endswith("." + self.domain)
        # literal: igualdad exacta (host o dirección de contrato).
        return t.host == self.literal


def _coerce_target(target: Target | str) -> Target:
    return target if isinstance(target, Target) else Target(value=str(target))


class ScopeGuard:
    """Carga un scope y decide ALLOW/DENY con default-deny y OUT>IN."""

    def __init__(
        self,
        in_scope: Iterable[str],
        out_scope: Iterable[str] | None = None,
        *,
        rps: float = 1.0,
        rps_per_host: dict[str, float] | None = None,
        program: str | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        self.program = program
        self.rps = float(rps)
        self.rps_per_host = {str(k): float(v) for k, v in (rps_per_host or {}).items()}
        self._in = [_Rule.parse(x) for x in in_scope]
        self._out = [_Rule.parse(x) for x in (out_scope or [])]
        self._audit = audit_log

    # ---- carga ----------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict, *, audit_log: AuditLog | None = None) -> "ScopeGuard":
        return cls(
            in_scope=data.get("in_scope") or [],
            out_scope=data.get("out_scope") or [],
            rps=data.get("rps", 1.0),
            rps_per_host=data.get("rps_per_host") or {},
            program=data.get("program"),
            audit_log=audit_log,
        )

    @classmethod
    def from_yaml(cls, path: str | Path, *, audit_log: AuditLog | None = None) -> "ScopeGuard":
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.from_dict(data, audit_log=audit_log)

    # ---- decisión -------------------------------------------------------
    def check(self, target: Target | str) -> Verdict:
        tgt = _coerce_target(target)
        norm = _norm(tgt)

        out_hit = self._first_match(self._out, norm)
        if out_hit is not None:
            verdict = Verdict(Decision.DENY, tgt, f"explicitly out of scope ({out_hit})", out_hit)
        else:
            in_hit = self._first_match(self._in, norm)
            if in_hit is not None:
                verdict = Verdict(Decision.ALLOW, tgt, f"in scope ({in_hit})", in_hit)
            else:
                verdict = Verdict(Decision.DENY, tgt, "not declared in scope (default-deny)", None)

        self._record(verdict)
        return verdict

    def assert_allowed(self, target: Target | str) -> Verdict:
        """Lanza PermissionError si el target no está permitido."""
        verdict = self.check(target)
        if not verdict.allowed:
            raise PermissionError(f"scope denied for {verdict.target.value!r}: {verdict.reason}")
        return verdict

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def _first_match(rules: list[_Rule], norm: _NormTarget) -> str | None:
        for rule in rules:
            if rule.matches(norm):
                return rule.raw
        return None

    def _record(self, verdict: Verdict) -> None:
        if self._audit is None:
            return
        self._audit.append(
            "scope.check",
            {
                "target": verdict.target.value,
                "kind": verdict.target.kind,
                "decision": verdict.decision.value,
                "reason": verdict.reason,
                "matched_rule": verdict.matched_rule,
            },
        )

    def rate_limiter(self, **kwargs):
        """Construye un RateLimiter que obedece el rps declarado en el scope."""
        from .ratelimit import RateLimiter

        return RateLimiter(self.rps, per_host=self.rps_per_host, **kwargs)
