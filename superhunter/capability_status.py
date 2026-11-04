"""Complete, dependency-checked backlog; no capability is marked done by prose.

The registry is a planning artifact, not executable plugins. Only the existing
local evidence checks below get checkmarks. None of the 50 requested end-to-end
capabilities is certified implemented by this registry.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .safe_io import read_artifact, strict_json

ROOT = Path(__file__).resolve().parent
STATES = {"pending": "○", "partial": "◐", "redesign": "↺"}


def validate_registry(plan: dict) -> dict:
    if type(plan) is not dict or set(plan) != {"schema_version", "capabilities"} or type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValueError("invalid capability registry")
    items = plan["capabilities"]
    if type(items) is not list or len(items) != 50:
        raise ValueError("registry must cover exactly 50 requested capabilities")
    by_id = {}
    for item in items:
        if type(item) is not dict or set(item) != {"id", "title", "status", "dependencies", "code_refs", "acceptance", "scope"}:
            raise ValueError("invalid capability entry")
        n = item["id"]
        if type(n) is not int or not 1 <= n <= 50 or n in by_id:
            raise ValueError("missing or duplicate capability ID")
        if type(item["status"]) is not str or item["status"] not in STATES:
            raise ValueError("no evidence for completed capability; unsupported status")
        for key in ("title", "acceptance", "scope"):
            if type(item[key]) is not str or not item[key].strip():
                raise ValueError("capability description missing")
        deps, refs = item["dependencies"], item["code_refs"]
        if type(deps) is not list or any(type(d) is not int or not 1 <= d <= 50 for d in deps) or len(set(deps)) != len(deps):
            raise ValueError("invalid capability dependencies")
        if type(refs) is not list or any(type(p) is not str or not p.endswith(".py") for p in refs):
            raise ValueError("invalid code references")
        if item["status"] == "partial" and not refs:
            raise ValueError("partial capability needs actual code reference")
        for path in refs:
            read_artifact(ROOT, path)  # bounded, no traversal, symlinks or execution
        by_id[n] = item
    if set(by_id) != set(range(1, 51)):
        raise ValueError("registry does not cover 1..50")
    active, visited = set(), set()

    def visit(n):
        if n in active:
            raise ValueError("capability dependency cycle")
        if n in visited:
            return
        active.add(n)
        for parent in by_id[n]["dependencies"]:
            visit(parent)
        active.remove(n)
        visited.add(n)

    for n in by_id:
        visit(n)
    return {"listed": 50, "implemented_end_to_end": 0, "states": dict(Counter(x["status"] for x in items))}


def load_registry() -> dict:
    plan = strict_json(read_artifact(ROOT, "capabilities.json"))
    validate_registry(plan)
    return plan


def render_checklist(plan: dict, circuit_root: str, bounded_cases: int) -> str:
    summary = validate_registry(plan)
    lines = ["# SUPERHUNTER — estado comprobado y alcance pendiente", "",
             "## Base de integración", "",
             "✅ Ejecución local DIABLO → NQC → referencia independiente → bitácora.",
             "✅ Enlaces verificados entre autorización, entradas, cálculos y resultados.",
             "✅ Rechazo de contradicciones aunque los hashes del paquete se hayan recalculado.",
             f"✅ {bounded_cases} casos del dominio numérico FINITO declarados, ejecutados y contrastados.",
             "✅ Registro de los 50 requisitos con dependencias y criterios de aceptación.", "",
             f"Raíz de evidencia de esta ejecución: `{circuit_root}`.",
             "Estas palomitas no certifican búsqueda de vulnerabilidades ni contratos externos.", "",
             "## Las 50 capacidades solicitadas", "",
             "○ Pendiente · ◐ Base parcial, no capacidad completa · ↺ Rediseño defensivo necesario.",
             "**Capacidades completas verificadas de las 50: 0.** No convertir este conteo en porcentaje de producto.", ""]
    for item in sorted(plan["capabilities"], key=lambda x: x["id"]):
        deps = ", ".join(str(x) for x in item["dependencies"]) or "base de integración"
        lines.extend([f"### {STATES[item['status']]} {item['id']}. {item['title']}",
                      f"Alcance: {item['scope']}", f"Criterio de aceptación: {item['acceptance']}",
                      f"Dependencias: {deps}.", ""])
    lines.extend(["## Límites", "",
                  "No hay ejecución de exploits, evasión de defensas, extracción de claves ni investigaciones autónomas de terceros.",
                  "Los componentes pendientes no son funciones vacías: no existen todavía como implementación.",
                  "La prueba exhaustiva solo cubre el dominio finito descrito; no garantiza ausencia universal de errores.",
                  "Los hashes detectan discrepancias; no autentican por sí mismos a un productor remoto.", ""])
    return "\n".join(lines)
