# SUPERHUNTER — integración en NQC

Estado: integración defensiva local y revisión de evidencias. **No es el Hunter
completo ni confirma vulnerabilidades reales.** Se conservan los 27 puntos de
integración y las 50 capacidades adicionales, sin convertir tests de laboratorio
en una certificación de producción.

## Comprobación integrada

```bash
python3 -m superhunter review-platform --out /tmp/superhunter-review-001
python3 -m superhunter verify-platform --bundle /tmp/superhunter-review-001
```

El comando ejecuta la suite del paquete, el laboratorio nativo y fuzzing
numérico, verifica sus artefactos y genera un estado único con ambos checklists.
No recibe objetivos, PoCs, RPC ni comandos externos. Devuelve
`LOCAL_DEFENSIVE_REVIEW_PASS` solo para ese recorrido y mantiene
`platform_complete=false`. Ver [PLATFORM_REVIEW.md](PLATFORM_REVIEW.md).

Suite actual: **261 pruebas ejecutadas**, sin fallos, errores ni omisiones.
La base combinada anterior se verificó con 199 pruebas. Se cerró la deuda de
validación conjunta que antes existía entre QA, grafos y fuzzing. Se conservaron
los 25 tests de evidencia numérica incorporados concurrentemente y se reejecutó
el conjunto conciliado.
Los registros de entregas anteriores se preservan; el registro actual está en
`platform-validation.json`.

## Ejecución nativa local

`local-lab` ejecuta componentes originales de DIABLO (Target, ScopeGuard y
AuditLog) junto con el solucionador de capacidad RMC-016 de NQC. Compara sus
resultados con una implementación numérica independiente y produce evidencia.
Los cuatro archivos de origen se preservan byte a byte y se verifican antes
de cargarlos. Todo vive bajo `superhunter/` en NQC.

```bash
python3 -m superhunter local-lab --out /tmp/superhunter-local-001
python3 -m superhunter verify-lab --bundle /tmp/superhunter-local-001
```

Son cinco casos numéricos fijos y controles negativos; no una reconstrucción
de vulnerabilidades. Las cantidades son sintéticas. `LOCAL_INTEGRATION_PASS`
acredita esas regresiones, no un Finding, severidad o recompensa. Detalles:
[LOCAL_LAB.md](LOCAL_LAB.md).

La ejecución emite `proof-graph.json` con 24 nodos: procedencia, decisiones de
alcance, entradas, resultados NQC, comparación independiente, bitácora y
veredicto. `verify-lab` reconstruye el grafo y comprueba sus dependencias.
La comparación distingue tipos JSON, incluidos booleanos y números.
Ver [PROOF_GRAPH.md](PROOF_GRAPH.md).

## Fuzzing numérico

```bash
python3 -m superhunter fuzz-lab --seed 20261103 --cases 256 --out /tmp/sh-fuzz-001
python3 -m superhunter verify-fuzz --bundle /tmp/sh-fuzz-001
```

Hasta 256 casos sintéticos por semilla, controlados y auditados por DIABLO,
calculados por NQC y contrastados con una referencia y propiedades metamórficas.
No es fuzzing EVM ni detección de vulnerabilidades. El punto 3 continúa parcial.
Ver [FUZZ_LAB.md](FUZZ_LAB.md).

## Intercambio offline de evidencias

`export-diablo` convierte un Finding nativo existente en Candidate unverified.
Requiere scope_id, repo, commit, chain, chain_id, fork_block, block_hash, family
y poc_path (archivo.t.sol::test_nombre). No deduce autorización ni ejecución del
texto de un reporte.

```bash
python3 -m superhunter export-diablo finding.json context.json forge.log \
  --out /directorio-privado/solicitud-nueva
python3 -m superhunter import-nqc solicitud.json respuesta.json admission.json \
  --evidence-root /directorio-privado/evidencias \
  --out /directorio-privado/revision-nueva
```

La respuesta NQC requiere schema_version=1, request_sha256, chain_id y la
Reconstruction completa. Es recepción de evidencia existente, no reconstrucción
automática de contratos. Admission conserva scope, forge, nqc, duplicate y
severity. La evidencia debe vincular severidad, confianza y notas.

Se conserva la interfaz legacy:

```bash
python3 -m superhunter candidate.json reconstruction.json admission.json \
  --evidence-root /directorio-privado/evidencias \
  --out /directorio-privado/revision-nueva
```

Los estados siguen siendo EXPORTED_UNVERIFIED, REJECTED, INCOMPLETE o
REVIEW_REQUIRED. No se emiten REPORT_READY ni Findings confirmados.
target_bound, run_ok, confianza y revisores son declaraciones externas.
El cierre histórico Protocol/Fork no se acepta como Reconstruction.

## QA y registro de requisitos

```bash
python3 -m unittest discover -s superhunter/tests -v
python3 -m superhunter check --out /tmp/superhunter-qa-001
python3 -m superhunter verify-check --bundle /tmp/superhunter-qa-001
python3 -m superhunter capabilities
```

`capabilities.json` conserva los 50 puntos; `integration-checklist.json`, los 27
originales. La revisión conjunta comprueba el inventario completo de tests,
no solo una lista de pruebas obligatorias. Ver [QUALITY_GATE.md](QUALITY_GATE.md)
y [PLATFORM_REVIEW.md](PLATFORM_REVIEW.md).

Requisitos: Linux/POSIX, Python 3.11+ y PyYAML 6.0.3 para las fuentes nativas.
No se instalan dependencias automáticamente. Las salidas usan carpetas nuevas,
privadas y fuera del checkout. COMPLETE.json se escribe al final con hashes.
Un código 0 significa recorrido local aprobado, nunca plataforma completa.

No hay explotación autónoma de terceros, Forge, forks, RPC, firma, broadcasts
ni envío de reportes. No se heredan certificaciones históricas de NQC. Los
controles de proceso no son un sandbox para código hostil. Los hashes prueban
consistencia de bytes, no autenticidad de un productor remoto ni seguridad total.
