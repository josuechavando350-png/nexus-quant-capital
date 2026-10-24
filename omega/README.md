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
  política de gas Titan sin capital propio y carga de código original fijada por Git blob.
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
**Titan aporta el gas. El presupuesto propio de $2,000 MXN queda descartado**
por instrucción del usuario del 23 de octubre de 2026. No hay anticipo propio ni
alternativa de gas propio. La cobertura de Titan y su remuneración se deben
acreditar por ejecución; una simulación positiva no prueba esa cobertura.
Ver [política activa](TITAN_GAS_POLICY.md). Las autoridades y auditorías históricas
conservan sus bytes y reglas originales, sin otorgar permisos actuales.

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

Auditoría: **32 pruebas nuevas**, **273/273 Omega**, **531/531 Rust Census**,
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
Omega 314/314, Rust Census 531/531, Rust PFT 56/56, Solidity 14/14, forks 4/4
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

## H15 — identidad de liquidadores con logs reales

`liquidator_intake.py` enlaza 139 logs recién recuperados con todos los compromisos
históricos originales. Identifica liquidadores por evento en las **127/127
transacciones**, con **49 direcciones distintas**, y conserva 127 prestatarios.
GasUsed/gasPrice también coincide con dRPC en todo el corpus. Esta concordancia
no sustituye paridad completa de recibos ni demuestra margen neto.

El resultado se almacena por separado del ledger histórico H14, con read-back,
restauración y rechazo de identidades falsificadas. Oracle delay, costos completos,
beneficiario económico y ejecución NQC permanecen desconocidos. La API no devolvió
block hash ni removed: se mantiene explícita esa limitación.
Ver [contrato H15](LIQUIDATOR_INTAKE_CONTRACT.md) y [auditoría H15](AUDIT_H15.md).


## H16: original WETH cashflow sample

`cashflow_intake.py` combines the H14/H15 source-bound records with the original
1979-byte price artifact 11527902751 (run 37726618359). Nine historical WETH/WETH
transactions have exact raw gross-minus-full-transaction-gas arithmetic. Two
have independently observed previous-block oracle references, at ranks 1 and 3;
seven retain null price valuations. Five-bps flash fees are explicitly hypothetical.
Complete net profit, oracle-delay and unknown costs remain null. Store admission,
recovery and queries revalidate all underlying artifacts and derived ledgers.
See `CASHFLOW_INTAKE_CONTRACT.md` and `AUDIT_H16.md`. This does not certify a
component or establish the requested 45% completion target.


**H14–H16 implementados y auditados en su alcance:** regresión local **445/445**,
con **93 pruebas nuevas**. El productor combinado
`af4fe54f1dc25d1e3b1ab620db874549b15af2ea` aprobó ambos jobs del run
[39874530238](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39874530238).
La auditoría posterior contrastó artifacts, metadata externa, logs y hashes de
pruebas: Rust PFT 56, Rust Census 528, Solidity 14, forks 4 y replay de 16 pasos.
Se conservan fuente y estado originales; los cambios posteriores son documentación.
Ver [auditoría final H16](AUDIT_H16.md). **Census sigue abierto, certificación
0/36; el 45% global todavía no está demostrado.**


## H17 — estado previo y comisión condicional

`historical_state_intake.py` integra tres artifacts originales autenticados: el
precio histórico de rango 2, tasas del Pool y estados de salud previos de los
tres principales casos WETH. Quedan 3/9 con precios/estado/tasa y 6/9 desconocidos.
Los tres HF previos superan 1; ninguna fila se convierte en oportunidad ejecutable.
La comisión calculada es condicional, no un costo pagado observado. El reporte
H16 se conserva y el nuevo reporte se valida al guardar, recuperar y consultar.
Ver `HISTORICAL_STATE_CONTRACT.md` y `AUDIT_H17.md`.

**H17 implementado y auditado en su alcance:** 471/471 pruebas locales, incluidas
26 nuevas. El productor `d99e0b332db7ef8cde70e195b67edd949ab17adb` aprobó forks
y replay desconectado en el run
[39884845749](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39884845749).
La auditoría posterior contrastó archivos, metadata de GitHub, logs y hashes del
código y pruebas. Precios previos: 2/9 → 3/9 de la muestra WETH; certificación
global: 0/36. Ver [auditoría final H17](AUDIT_H17.md) y
[medidas de avance y pendientes](PRODUCT_PROGRESS.md).

## H18 — evolución temporal histórica

`temporal_intake.py` vincula los tres diagnósticos originales de avance de tiempo
con el estado previo H17. Una medición cruza HF por debajo de uno, dos permanecen
por encima y seis casos conservan `null`. El caso de rango 2 aumenta su HF.
Las fechas de los bloques tienen acuerdo de dos proveedores; los forks originales
usan solo dRPC. Ningún resultado se convierte en señal prospectiva, causa oracle
demostrada, operación ejecutable o ganancia. Se conservan y validan todos los
reportes y archivos originales al guardar, consultar y recuperar el almacenamiento.
Ver [contrato H18](TEMPORAL_INTAKE_CONTRACT.md) y [auditoría H18](AUDIT_H18.md).

**H18 implementado y auditado en su alcance:** **498/498 pruebas locales**,
incluidas 27 nuevas. El productor `bd4b120e78603617473f2750bcff367271459375`
aprobó ambas etapas físicas H2 y la auditoría de artefactos, metadata y logs del
[run 39889427564](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39889427564).
La cobertura temporal integrada es 3/9 de la muestra WETH; son diagnósticos
originales retenidos, no tres forks temporales nuevos. Certificación: **0/36**.

### H19 — transporte de evidencia al almacén Rust

El adaptador conserva objetos, snapshot y journal entre Python y el almacén Rust
original. La comprobación exige inventario externo completo porque la raíz Rust
excluye los artefactos sin referencias. Pruebas locales: **532/532 Omega** y
**66/66 del almacén Rust**; ida y vuelta real de **28 artefactos**, sin pérdida de
bytes ni del estado de revocación local. La validación remota aislada y su
auditoría final aprobaron el productor `fcbe6cac8c69c58b55d4ccf67c399dd359db6a96`,
[run 39897180333](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39897180333). Ver [contrato](RUST_STORE_TRANSPORT_CONTRACT.md)
y [auditoría H19](AUDIT_H19.md). Cero rangos certificados; producto **0/36**.

Cierre de H19: **4/4 pasos (100% de este incremento)**. La regresión completa se
repitió tras recuperar los ZIP históricos auténticos: 532/532, sin omisiones.
La auditoría documenta qué evidencia local anterior no sobrevivió al reinicio.

### H20 — revocación entre lotes con dependencias declaradas

`dependency_intake.store_chain` admite cinco etapas históricas autenticadas bajo
identidades nuevas y cuatro dependencias explícitas. Revocar la raíz bloquea las
consultas de todos sus descendientes y conserva sus bytes para auditoría; una
rama sin dependencia permanece activa. Los manifiestos anteriores mantienen su
semántica. La copia recuperada exige el journal externo actual para rechazar
snapshots previos a la revocación. No acredita una reorganización real de cadena.
Ver [contrato H20](DEPENDENCY_REVOCATION_CONTRACT.md) y [auditoría H20](AUDIT_H20.md).
**H20 cerrado y auditado: 561/561 pruebas, 29 nuevas; 4/4 pasos de este incremento.**
Forks, replay aislado y auditoría posterior aprobaron el productor `641ffb4c5a49514fdca346e57b06f6526f4b7dcf`
en el [run 40019225049](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/40019225049).
Certificación del producto: 0/36.

## H21 — evidencia económica y gas Titan

El lector incorpora el fork histórico de liquidación y su gas medido: un caso
de nueve WETH, cinco sensibilidades y catorce categorías de costo explícitas.
La comisión del flash loan y el excedente WETH simulados, el gas medido y los
presupuestos supuestos se conservan separados de pagos reales. Los costos
completos, la cobertura concreta de Titan y la ganancia realizada siguen sin
demostrarse. Ocho casos no tienen ese diagnóstico; no se inventan ceros.

El sexto lote declara su dependencia temporal. Consultas, revocación y recuperación
conservan esa relación. Runtime v4 exige su replay económico desconectado y vincula
la política activa. **H21 cerrado y auditado: 589/589 pruebas, 28 nuevas, 4/4 controles.**
Forks, replay y auditoría posterior aprobaron el productor `668ddb5f26225e9f9f545b1c1e07740c01d783c8`
en el [run 40027689852](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/40027689852).
Ver [contrato](EXECUTION_INTAKE_CONTRACT.md) y [auditoría](AUDIT_H21.md).

## H22 - gas quemado y propinas observadas

`inclusion_fee_intake.py` incorpora seis respuestas de Blockscout para los tres
primeros ganadores WETH de la muestra histórica. Contrasta gas, precio efectivo,
bloque, índice, tarifa base y desglose. La propina ya está incluida en el gas total;
no se vuelve a restar. Las tres propinas observadas son cero, pero los pagos
directos al builder siguen desconocidos. Las otras seis filas permanecen sin
desglose observado. No cambia 0/127 filas de costos completos ni 0/36 componentes
certificados. Añade un séptimo lote dependiente de H21, verificable y revocable.
El paquete runtime v5 exige reconstruir ese lote en el worker desconectado y
vincularlo a la política Titan: capital propio cero, sin anticipo ni alternativa
propia. Rechaza cobertura inventada y conserva el alcance original de v1-v4.
Ver [contrato](INCLUSION_FEE_CONTRACT.md) y [auditoría](AUDIT_H22.md).
