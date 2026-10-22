# Sovereign Radar Omega — integración offline de Census

**Estado: 0/36 componentes certificados; Census no cerrado.** Hay código de
integración y pruebas con evidencia histórica auténtica. No es un motor en vivo,
una certificación del mercado actual ni una autorización para gastar.

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
  histórico. Sólo aparta los archivos explícitos declarados en `EXTENSION_FILES` en una copia
  temporal y entrega TODOS los demás archivos al verificador original.
  No oculta workflows, archivos de clientes ni otras incorporaciones.
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
workflows. Canary conserva el techo de **$2,000 MXN**, recargas máximas de
**$500 MXN** y revisión tras **$1,000 MXN** sin captura. Son límites del diseño,
no autorización de gasto. La autoridad histórica con `OWN_CAPITAL = 0` no se
reescribe para aparentar certificación bajo la política nueva.

Un hash detecta cambios, pero por sí solo no autentica un reporte externo.
Reproducir las entradas fijadas es obligatorio. El almacenamiento local es
atómico y no sobrescribe evidencia existente; no equivale a un Evidence Vault
certificado, replicado ni probado frente a reorganizaciones de cadena.

Faltan paridad de las tres vías de verdad, todas las posiciones del alcance,
el ledger por transacción, costos completos, ganadores, retrasos del oráculo y
propinas al builder. No se extrapolan agregados de otros liquidadores a P&L de
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
