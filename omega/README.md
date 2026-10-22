# Sovereign Radar Omega — integración offline de Census

**Estado: 0/36 componentes certificados; Census no cerrado.** Hay código de
integración y pruebas con evidencia histórica auténtica. No es un motor en vivo,
una certificación del mercado actual ni una autorización para gastar.
**H2: 100% de integración auditada**, con forks y replay desconectado físicos
aprobados. Esto no mide la terminación global de Omega: Census mantiene 9/9
componentes con base parcial y 0/9 certificados.

Base: `NQC_Sovereign_Radar_Omega.pdf`, v1.0, 22 de octubre de 2026, SHA-256
`5c1739799ab5099bc95f7347aeed8bcc2e3b098e64c3688584331004f15edf0f`.

## Qué incorpora

- `architecture_v3.json`: los 36 componentes en 8 capas; fases Census/Shadow/
  Canary/Escala = 9/9/4/14. El catálogo conserva `not_assessed`; el mapeo parcial
  separado está en `census_map.json` y no certifica componentes.
- `audit.py` e `integrity.py`: controles estructurales, tipos, claves JSON únicas,
  límites de gas de diseño y carga de código original fijada por Git blob.
- `census_bridge.py`: reproduce el auditor RMC-016 original con dos archivos ZIP
  auténticos. Emite **OBSERVAR** ante evidencia histórica incompleta y **NO-GO**
  ante entradas inválidas. Nunca emite GO ni realiza llamadas de red.
- `isolation.py`: adaptador de aislamiento que no modifica el verificador
  histórico. Aparta los archivos explícitos de `EXTENSION_FILES` y el único
  workflow Omega revisado, después de comprobar su hash, bytes y modo. Entrega
  todos los demás archivos al verificador original; otros workflows o archivos
  de clientes siguen siendo rechazados.
- `evidence/historical-baseline.json`: resultado determinista del replay de
  agregados, no de transacciones/EVM. Conserva IDs, alcance y bloqueos originales.

## Reproducción

Desde la raíz del repositorio, con Python 3.10+ en un sistema POSIX:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 omega/audit.py
python3 -m unittest discover -s omega -p 'test*.py' -v
python3 ci/nqc-census/test_rmc016_winner_net_audit.py -v
```

Para ejecutar también las seis pruebas de archivos reales, suministrar
`NQC_D15_ARCHIVE` y `NQC_D16_ARCHIVE` con las rutas de los ZIP originales de los
artefactos `11504276505` y `11505504820` del repositorio fuente. Sin esas rutas,
las seis pruebas se marcan SKIP; no se reemplazan por datos ficticios.

```sh
python3 omega/census_bridge.py \
  --d15-archive "$NQC_D15_ARCHIVE" \
  --d16-archive "$NQC_D16_ARCHIVE" \
  --out-dir /tmp/nqc-omega-evidence
python3 omega/isolation.py
```

El último comando requiere el checkout COMPLETO. Conserva la opción
`--source-git /ruta/al/almacen-original` del verificador histórico. Una copia
parcial falla: las pruebas unitarias no reemplazan ese requisito. El comando
histórico directo sigue rechazando `omega/`; esto se conserva deliberadamente.

## Límites y aceptación

Census y Shadow no conectan fondos. Observador, firmante y ejecutor siguen
separados; este cambio no contiene firmante, broadcasting, despliegues ni
ejecución con fondos. El workflow H2E sólo comprueba evidencia y forks locales.
Canary conserva el techo de **$2,000 MXN**, recargas máximas de
**$500 MXN** y revisión tras **$1,000 MXN** sin captura. Son límites del diseño,
no autorización de gasto. La autoridad histórica con `OWN_CAPITAL = 0` no se
reescribe para aparentar certificación bajo la política nueva.

Un hash detecta cambios, pero por sí solo no autentica un reporte externo.
Reproducir las entradas fijadas es obligatorio. El almacenamiento local es
atómico y no sobrescribe evidencia existente; no equivale a un Evidence Vault
certificado, replicado ni probado frente a reorganizaciones de cadena.

Existe ya el contrato offline de paridad de tres vías y el esquema de ledger por transacción; faltan poblar triadas reales independientes, todas las posiciones del alcance y filas autenticadas con costos completos, ganadores, retrasos del oráculo y propinas al builder. No se extrapolan agregados de otros liquidadores a P&L de
NQC ni a mercados actuales. Ver `AUDIT_H2.md` para resultados y bloqueos exactos.

## Evaluación estática de Census

`census_assessment.json` enlaza los nueve componentes Census del diseño con los
Git blobs revisados. El resultado actual es **7 foundational_partial, 2 historical_partial, 0 not_evidenced y 0 certificadas**. Ejecutar `python3 omega/census_assessment.py` y
`python3 -m unittest -v omega/test_census_assessment.py` para validar el mapa.

## H4 · Opportunity Dossier / Evidence Vault

`opportunity_vault.py` añade un expediente Census ligado a bloque, mercado y
posición, con decisión, vector de 14 costos, competencia, escenarios, outcome y
referencias de evidencia. Census sólo admite `NO-GO` u `OBSERVAR`; `GO`,
firma, broadcast, gasto, cierre de Census y P&L de NQC no demostrado se bloquean.

El hito H4 tiene **19/19 pruebas nuevas aprobadas** y read-back de los Git blobs.
Esto completa el hito de implementación offline, pero el componente 29 sigue
`foundational_partial`: falta poblar expedientes reales, integrarlos con el
store Rust y probar recuperación/replicación/reorg de extremo a extremo.

## H5 · Libro de órdenes de liquidaciones

`liquidation_order_book.py` implementa un índice offline de umbrales racionales
exactos, sin `float`, ligado a bloque y compromiso de evidencia. Detecta sólo
posiciones que cruzan por primera vez entre dos precios y conserva el orden exacto
de encuentro para movimientos ascendentes o descendentes.

H5 tiene **19/19 pruebas nuevas aprobadas** y **38/38 combinadas H4 + H5**. El
componente 8 sigue `foundational_partial`: faltan los umbrales generados por
matemática de protocolo verificada, población completa, accrual de intereses,
integración con Causal Graph y replay de mercado.

## H6 · Causal Graph

`causal_graph.py` añade un grafo de dependencias offline, ligado a bloque y
evidencia. Cada posición debe relacionarse con mercado, oráculo, modelo de
intereses, liquidez y ruta; cambios en dependencias se propagan en reversa para
identificar exactamente qué posiciones recalcular.

H6 tiene **20/20 pruebas nuevas aprobadas** y **58/58 combinadas H4 + H5 + H6**.
El componente 7 sube de `not_evidenced` a `foundational_partial`, no a
certificado: todavía faltan población completa, prueba de completitud, replay
temporal e integración directa con el Libro de órdenes.

## H7 · Oracle Semantics / Depeg Radar

`oracle_semantics.py` clasifica oráculos únicamente mediante semántica
evidence-bound: `MARKET_PRICE` o `EXCHANGE_RATE`. No usa símbolos, nombres ni
heurísticas. La clasificación de exchange-rate sólo afirma que el depeg spot no
se refleja directamente por ese oráculo; no afirma inmunidad a liquidación.

H7 tiene **18/18 pruebas nuevas aprobadas** y **76/76 combinadas H4–H7**. El
componente 10 sube de `not_evidenced` a `foundational_partial`; falta poblar
el catálogo real, probar semántica por protocolo y replay de depegs.

## H8 · Long-Tail Research Prioritizer

`long_tail.py` ordena cobertura de investigación con frentes Pareto sobre
novedad, tamaño, L2 y complejidad de ruta. No usa pesos arbitrarios ni genera
score económico, EV, captura probable o GO/NO-GO. Trade-offs permanecen en el
mismo frente no dominado.

H8 tiene **19/19 pruebas nuevas aprobadas**. El componente 32 sube de
`not_evidenced` a `foundational_partial`. Con esto los **9/9 componentes Census
tienen al menos una base demostrada**, pero ninguno está certificado: faltan
población real completa, evidencia out-of-sample y los gates de H2.

## H9 · Protocol Adapter Registry

`protocol_adapters.py` define identidad y conformance común para adaptadores:
familia, cadena, despliegue, versión/código y seis capacidades evidence-bound.
Una capacidad sólo puede declararse soportada si lleva evidencia; una familia
nombrada sin implementación real permanece no conformante.

H9 tiene **20/20 pruebas nuevas aprobadas**. El componente 1 sigue
`foundational_partial`, pero ya existe un contrato común auditable; faltan los
adaptadores reales de Morpho y subastas, fixtures cross-adapter y PFT por familia.

## H10 · Truth Triad

`truth_engine.py` exige tres vías independientes por sujeto y estado:
reconstrucción eventos/storage, lectura directa y replay EVM. La paridad es
igualdad exacta; una discrepancia genera `MISMATCH`, sin mayoría ni tolerancias.
Los batches requieren cobertura explícita de todos los sujetos esperados.

H10 tiene **20/20 pruebas nuevas aprobadas**. El componente 6 sigue
`foundational_partial`: falta poblar triadas reales completas y reestablecer
el runtime closeout PFT vinculado al productor actual. `PARITY` nunca se
presenta como certificación PFT.

## H11 · Competition & Margin Ledger

`competition_ledger.py` materializa el formato exacto por transacción para
ganador, oracle update, bloque ganador, bono, builder payment, gas y otros costos.
Los desconocidos permanecen `null`; el margen observado sólo se deriva cuando
los costos están explícitamente completos y nunca se atribuye a NQC.

H11 tiene **20/20 pruebas nuevas aprobadas**. Los componentes 24 y 25 siguen
`historical_partial`: falta poblar las 127 transacciones con receipts/eventos
autenticados, reconciliar costos reales y añadir counterfactual de detección NQC.


## H2B · Full Git-object Isolation Audit

La rama fue auditada contra el manifest y el árbol fuente completos: **637/637
rutas**, **631/631 blobs byte-identical**, **6/6 transformaciones autorizadas**,
**10/10 refs históricas**, **106 workflows deshabilitados**, **0 activos**,
**0 symlinks** y **0 cambios fuera de `omega/`** respecto a main.

Con este control H2 avanza a **88%**. Sigue pendiente la parte ejecutable:
verificador local con object store, regresión Python/Rust y PFT/fork replay.
Esto no certifica ningún componente ni cierra Census.


## H12 · Candidate Coherence Gate

`candidate_coherence.py` conecta Adapter Registry, Truth Triad, Causal Graph,
Liquidation Order Book, Oracle Semantics y Opportunity Dossier para una misma
oportunidad. Exige el mismo estado, position/market/oracle coherentes y adapter
conforme. El único resultado positivo es `FOUNDATION_COHERENT`; nunca GO ni
certificación.

H12 tiene **21/21 pruebas propias aprobadas**. Además, una regresión conjunta
H4–H12 ejecutó **176/176 pruebas aprobadas** en el mismo entorno offline. Esto
demuestra coherencia entre las fundaciones, no cierre de Census ni rentabilidad.

## H2C · Regresión ejecutable del checkout completo

H2 alcanza **94% de integración auditada**. El verificador original pasó con
los 637 payloads y objetos fuente. Census Rust 1.98.1 aprobó 528 tests,
fmt, Clippy (`-D warnings`) y build. Omega aprobó 241 tests sin omisiones.

Discovery Python conserva siete errores de preparación heredados: 838 tests
descubiertos y 664 ejecutados/aprobados. La comparación con el snapshot original
es exacta. Las otras 174 pruebas aprobaron usando sus CLI, insumos auténticos
y catálogos históricos en copias separadas. `regression.py` y
`historical_regression.py` registran esa distinción sin convertir errores en PASS.

PFT materializado desde su fuente original aprobó 56 tests Rust y 14 Solidity.
En H2C quedaron pendientes forks, replay desconectado, revisión del formato
heredado y enlace al productor nuevo. H2D, abajo, actualiza esos pendientes.
Ver [auditoría H2C](AUDIT_H2_EXECUTABLE.md) y `evidence/h2-*`.

## H2D · Fuente PFT vinculada a NQC

`pft_source_binding.py` reproduce la materialización original conservando su
gate de ascendencia en un checkout separado. Verifica objetos Git, los bytes
protegidos, ambos árboles efectivos y el commit/tree limpio exacto de NQC.
Los recibos históricos mantienen sus identidades. El resultado es evidencia
local de procedencia; no crea autoridad de CI ni certificación.

Auditoría: **32 pruebas nuevas**, **273/273 Omega**, **528/528 Rust Census**,
**56/56 Rust PFT**, **14/14 Solidity**, más check/build release PFT y aislamiento.
El enlace real se ejecutó contra el commit publicado `b1a093e11e92acb59c796e220786ff6346d2a1f9`.
El commit posterior incorpora la evidencia y una prueba adicional de auditoría.

El contrato original registra los fallos de formato sin exigir reescritura de
fuentes; los fallos siguen visibles. Al terminar H2D, forks y replay seguían
pendientes y H2 estaba en 94%. H2E, abajo, cierra esos gates físicos.
Ver [contrato](PFT_SOURCE_BINDING_CONTRACT.md), [auditoría H2D](AUDIT_H2_PFT_BINDING.md)
y `evidence/h2-pft-*`.

## H2E · Runner físico en la rama de Omega

Se publicó y activó la migración para `feat/omega-h2-executable-audit-20261022`:
`h2_actions.py` comprueba forks con dos proveedores y replay D06 desconectado en
dos jobs Ubuntu estándar. Conserva los 106 workflows históricos desactivados.
La única excepción activa revisada es `.github/workflows/omega-h2-audit.yml`,
copia exacta de la plantilla fijada por SHA-256; ninguna otra ruta queda oculta
al verificador original. Logs y contexto de productor no equivalen a artifact
canónico autenticado. Certificación permanece en **0/36**.

**H2 100% auditado:** run
[39859932654](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39859932654),
commit `e21d528dabd83d7f14e7f236b9e6d4e3fc1706f7`, ambos jobs success.
Omega 314/314, Rust Census 528/528, Rust PFT 56/56, Solidity 14/14, forks 4/4
y replay físico byte-idéntico con fuente intacta. Identidad GitHub, compromisos,
aislamiento y timestamps se auditaron después de la ejecución. El discovery Python
genérico mantiene los siete errores heredados y la validación separada de 174 casos.
Faltan las evidencias y cierres por componente descritos en `census_assessment.json`;
los estados de ese catálogo corresponden a su `as_of_commit` histórico, no se
reescriben como certificación nueva por haber cerrado H2.

Ver [migración H2E](ACTIONS_MIGRATION.md) y [auditoría H2E](AUDIT_H2_ACTIONS.md)
para resultados locales, estado remoto y límites. No trasladar a Miner ni main.

## H13 — auditoría CI reproducible

`ci_evidence.py` conserva y verifica el paquete real de logs y metadata del run
H2 `39859932654`: identidad exacta, 54 compromisos y 16 pasos del replay.
El ZIP de 98297 bytes queda en `evidence/h2-ci-capture.zip`, con pin revisado.
El verificador rechaza otra versión del código como productor esperado.

Esto demuestra la auditoría offline de esa captura. No crea un artifact de
Actions ni una certificación nueva; Census sigue en 0/9 y Omega en 0/36.
Ver [contrato](CI_EVIDENCE_CONTRACT.md) y [auditoría H13](AUDIT_H13.md).

**H13 100% dentro de ese alcance, auditado:** Omega 352/352 local; 38/38 pruebas
nuevas y 41/41 del ejecutor en ambos jobs remotos. Run
[39866201976](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39866201976),
productor `4a521dd42a0c816cd6959cd0fb4ac4e5b871dab0`: ambos jobs success,
forks y replay completo aprobados, con auditoría posterior de identidad,
integridad, aislamiento, resultados y tiempos. Certificación sigue 0/36.

## H14 — datos por transacción, recuperación y artifacts

`historical_intake.py` reproduce tres artifacts originales: 139 eventos,
127 recibos dRPC y 139 legs de deuda/colateral. Conserva el fallo global del run
de recibos, la falta de paridad independiente y los campos desconocidos como null.
Gas se cuenta una vez por transacción; cantidades de tokens no se convierten
automáticamente en USD, margen neto ni ganancias de NQC.

`evidence_store.py` y `historical_pipeline.py` incorporan almacenamiento
transaccional, recuperación tras terminar procesos, escrituras concurrentes,
exportación/restauración verificadas y revocación local sin borrar evidencia.
La consulta vuelve a comprobar las fuentes originales. La prueba de revocación
es controlada; no certifica una reorganización real ni replicación remota.

La migración revisada amplía cobertura CI a todo el Python/evidencia Omega y
retiene un runtime.json acotado por job con el productor exacto. El consumidor
`runtime_artifact.py` exige metadata obtenida externamente y su digest confiable;
un archivo local con un hash propio no demuestra origen de GitHub.

Regresión local H14: **415/415 pruebas**, incluidas **63 nuevas**, sin omisiones.
Aislamiento completo: **104 archivos Omega**, 531 fuentes originales y 106
workflows históricos desactivados. Ejecución remota y auditoría posterior se
registran en [AUDIT_H14.md](AUDIT_H14.md). Producto final 45% aún no demostrado;
ver [PRODUCT_PROGRESS.md](PRODUCT_PROGRESS.md). Certificación **0/36**.
