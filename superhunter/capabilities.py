"""Fifty requested capabilities, tracked honestly; this is NOT fifty engines.

All original capabilities remain unimplemented at their requested scope.
Foundations are reported separately, using actual test and stage receipts.
No capability is promoted merely because its name appears in this catalogue.
"""
from __future__ import annotations

# id, requested title, prerequisites. Dependencies describe a proposed design,
# not callable plug-ins, attack paths or authority to execute any operation.
ITEMS = (
    (1, "Consultas de grafos SlithIR", ()),
    (2, "Taint analysis de contratos", (1,)),
    (3, "Fuzzing guiado por invariantes", (1,)),
    (4, "Fork fuzzing", (3, 45)),
    (5, "Simulación de préstamos flash", (4,)),
    (6, "Integración de oráculos", (1,)),
    (7, "Inferencia simbólica estocástica", (1, 34)),
    (8, "Secuencias multibloque", (3,)),
    (9, "Mutaciones del estado local", (4,)),
    (10, "Orquestación neuro-simbólica", (7, 33)),
    (11, "Diferenciales de bytecode", (1,)),
    (12, "Estrés de retiros y liquidez", (3,)),
    (13, "Taint binario dinámico", (45,)),
    (14, "Grafos de permisos", (1,)),
    (15, "Extractor automático de PoC", (3,)),
    (16, "Verificación de firmas y nonces", (1,)),
    (17, "Fallos de sistemas distribuidos", (45,)),
    (18, "Reentrancia entre contratos", (1, 3)),
    (19, "Diferenciales del compilador", (11,)),
    (20, "Pruebas de API por gramática", (45,)),
    (21, "Pruebas de protocolos de red", (45,)),
    (22, "Análisis de canales laterales", (45,)),
    (23, "HTTP smuggling y cache poisoning", (45,)),
    (24, "Consistencia dinámica RBAC", (14,)),
    (25, "Deserialización y cadenas de gadgets", (30,)),
    (26, "Restricciones de circuitos ZK", (34,)),
    (27, "Concurrencia y memoria compartida", (45,)),
    (28, "Consenso ante fallos bizantinos", (45,)),
    (29, "Detección de secretos en logs", (45,)),
    (30, "Dependencias y funciones alcanzables", ()),
    (31, "Integridad de carga de bibliotecas", (30,)),
    (32, "Evasión genética de sandboxes", (45,)),
    (33, "Coherencia documentación/código", (1,)),
    (34, "Verificación formal acotada", ()),
    (35, "Planificación de exploits MCTS", (3, 34)),
    (36, "Grafo de conocimiento entre dominios", (1, 30)),
    (37, "Triaje e impacto financiero", (6, 12)),
    (38, "Aprendizaje con retroalimentación humana", (47, 48)),
    (39, "Análisis visual del frontend", (45,)),
    (40, "Análisis de topología de grafos", (1,)),
    (41, "Lectura de diagramas y especificaciones", (33,)),
    (42, "Secretos expuestos en grabaciones", (29,)),
    (43, "Navegación stealth y evasión de captchas", (45,)),
    (44, "Payloads adaptativos para evadir filtros", (20,)),
    (45, "Entornos clonados de pruebas", ()),
    (46, "Despliegue de contratos de ataque", (4, 15)),
    (47, "Reportes ejecutivos y técnicos", (37,)),
    (48, "Verificación de parches y regresiones", (3, 11)),
    (49, "Inteligencia de amenazas y avisos", (30,)),
    (50, "Mapeo de controles de cumplimiento", (47,)),
)
REDESIGN = {
    5: "Pruebas de liquidez en modelos propios; sin generar secuencias para drenar protocolos.",
    8: "Pruebas temporales de propiedades; no planificación autónoma de ataques multibloque.",
    15: "Minimizar y documentar contraejemplos de pruebas propias; no generar exploits de terceros.",
    22: "Evaluar tiempo constante con secretos de prueba; no extraer claves ni credenciales.",
    23: "Verificar coherencia de parsers propios; sin secuestro de sesiones ni pruebas activas a terceros.",
    25: "Inventario y endurecimiento de deserialización; no construir cadenas automáticas RCE.",
    28: "Simulación local de tolerancia a fallos; sin interrumpir validadores o redes reales.",
    31: "Validar procedencia y permisos de bibliotecas; no desviar la ejecución legítima.",
    32: "Verificación de límites de aislamiento; sin optimizar payloads de escape o evasión.",
    35: "Planificar cobertura de pruebas defensivas; no encadenar errores para optimizar exploits.",
    36: "Relacionar activos, dependencias y controles; no diseñar ataques integrales.",
    38: "Aprendizaje explícito, consentido, versionado y reversible; sin observación oculta ni autoedición libre.",
    42: "Material propio autorizado, detección y redacción de secretos; no recopilar credenciales de terceros.",
    43: "Automatización de navegador transparente en pruebas autorizadas; sin evasión WAF, bots o captchas.",
    44: "Verificar validación y sanitización en componentes propios; sin evasión adaptativa de filtros.",
    46: "Aserciones de regresión locales revisadas; sin generar ni desplegar contratos de explotación.",
}
QUALIFICATIONS = {
    7: "Las reglas inferidas son hipótesis hasta contar con una especificación y verificación.",
    9: "Declarar toda mutación artificial; un estado fabricado no demuestra un fallo alcanzable.",
    10: "El modelo propone; las pruebas deciden. No existe garantía general de cero alucinaciones.",
    13: "Motor distinto al análisis EVM; limitarlo a binarios propios e instrumentación defensiva.",
    26: "Precisar circuito, entradas públicas, constraints y límites del verificador.",
    34: "Una prueba es relativa al modelo, propiedades y límites; timeout o unknown no equivalen a seguro.",
    37: "Importes con unidades, fuentes y fecha; dinero en riesgo no equivale a beneficio ni a recompensa.",
    39: "Una captura visual no demuestra por sí sola una vulnerabilidad del navegador.",
    40: "Un patrón de grafo es una señal, no una demostración de vulnerabilidad.",
    45: "Inventariar diferencias de la réplica; no afirmar identidad exacta sin comprobarla.",
    47: "Borradores basados en evidencias, revisados antes de divulgarse.",
    48: "Mismo contrato de pruebas antes/después; no modificar aserciones para ocultar regresiones.",
    49: "Avisos públicos con fuentes y revisión; nunca instalar o ejecutar reglas remotas automáticamente.",
    50: "Mapeo orientativo versionado; no certifica ISO/SOC ni determina por sí solo una infracción legal.",
}
FOUNDATIONS = {
    "F01": ("Puente de datos DIABLO/NQC", ("test_integration.IntegrationTests.test_native_roundtrip_always_requires_review",)),
    "F02": ("Ejecución conjunta de componentes locales", ("test_local_lab.LocalLabTests.test_real_nqc_and_diablo_functions_are_called",)),
    "F03": ("Integridad y almacenamiento privado", ("test_integration.IntegrationTests.test_output_private_and_content_committed",)),
    "F04": ("Bitácora vinculada a cada entrada y resultado", ("test_assurance.AssuranceTests.test_resealed_unrelated_case_rejected",)),
    "F05": ("Catálogo de las 50 capacidades sin falsas palomitas", ("test_assurance.AssuranceTests.test_catalogue_has_all_fifty_and_no_completed_engines",)),
}


def catalogue() -> list[dict]:
    result = [{"id": n, "title": title, "depends_on": list(deps),
               "status": "REDESIGN_REQUIRED" if n in REDESIGN else "PENDING",
               "implemented": False, "evidence": [],
               "scope": REDESIGN.get(n, QUALIFICATIONS.get(n,
                   "Diseño defensivo, alcance explícito y pruebas reproducibles sobre componentes autorizados."))}
              for n, title, deps in ITEMS]
    validate_catalogue(result)
    return result


def validate_catalogue(rows: list[dict]) -> None:
    if type(rows) is not list or len(rows) != 50:
        raise ValueError("exactly fifty capability records required")
    ids = [row.get("id") for row in rows if type(row) is dict]
    if len(ids) != 50 or any(type(n) is not int for n in ids) or set(ids) != set(range(1, 51)):
        raise ValueError("capability ids must be unique 1..50")
    graph = {}
    for row in rows:
        if set(row) != {"id", "title", "depends_on", "status", "implemented", "evidence", "scope"}:
            raise ValueError("capability fields mismatch")
        if row["implemented"] is not False or row["evidence"] != [] or row["status"] not in ("PENDING", "REDESIGN_REQUIRED"):
            raise ValueError("unimplemented capabilities cannot be promoted by a manifest")
        if any(type(row[k]) is not str or not row[k].strip() for k in ("title", "scope")):
            raise ValueError("capability description required")
        deps = row["depends_on"]
        if (type(deps) is not list or any(type(n) is not int or n not in ids or n == row["id"] for n in deps)
                or len(set(deps)) != len(deps)):
            raise ValueError("invalid dependency")
        graph[row["id"]] = deps
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError("dependency cycle")
        if node in done:
            return
        visiting.add(node)
        for parent in graph[node]:
            visit(parent)
        visiting.remove(node)
        done.add(node)
    for node in graph:
        visit(node)


def checklist(test_records: list[dict], gates_passed: bool) -> dict:
    passed = {r["id"] for r in test_records if r.get("outcome") == "PASS"}
    return {"foundations": [{"id": name, "title": title,
                            "verified_this_run": gates_passed and set(required).issubset(passed),
                            "required_tests": list(required)}
                           for name, (title, required) in FOUNDATIONS.items()],
            "capabilities": catalogue(), "completed_requested_capabilities": 0,
            "warning": "Pruebas locales acotadas, no certificación de seguridad ni garantía de ausencia de fallos."}


def render_checklist(value: dict) -> str:
    lines = ["# SUPERHUNTER — checklist basado en evidencia", "", value["warning"], "", "## Fundamentos", ""]
    for row in value["foundations"]:
        mark = "✅" if row["verified_this_run"] else "☐"
        lines.append(f"{mark} {row['id']}. {row['title']}")
    lines.extend(["", "## Las 50 capacidades solicitadas", "", "Ninguna está completada a su alcance original. El registro no implementa sus motores.", ""])
    for row in value["capabilities"]:
        status = "Rediseño defensivo pendiente" if row["status"] == "REDESIGN_REQUIRED" else "Pendiente"
        lines.append(f"☐ {row['id']:02d}. {row['title']} — **{status}**. {row['scope']}")
    return "\n".join(lines) + "\n"
