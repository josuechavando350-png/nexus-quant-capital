# NQC - Escala histórica, 11 microsegundos y magnitudes

## Dictamen acotado

No se localizó el artefacto original que demuestre **11 microsegundos**, ni una fuente primaria que defina **$14,000 billones**. El resultado es NO_LOCALIZADO_NO_REFUTADO, dentro de la búsqueda descrita; no se demuestra que tales archivos no existan en otras ramas o respaldos.

Sí se verificó documentalmente que un PR distinto reporta una aceleración de **11.3288 veces**, y que el cierre T37 separa expresamente cargas sintéticas de evidencia de mercado real. Ninguna de esas cantidades autoriza una cifra mensual de ingresos.

## Búsqueda realizada y límites

Fecha: 2026-10-17 UTC. Engine main fijado a `380eff1fc14336bd24d93c8ef807525a7078950d`, sólo lectura.

| Consulta o fuente | Resultado observado | Qué no permite concluir |
| --- | --- | --- |
| Código en default branch: `"11" "microseconds"` | 0 resultados en el índice consultado | Ausencia en toda la historia o todos los idiomas |
| Código en default branch: `"14000"` | 0 resultados | Ausencia de una cifra formateada o calculada de otro modo |
| Mensajes de commits: `"microsegundos"` | 0 resultados entre las respuestas del servicio | Ausencia en blobs o artefactos históricos |
| Mensajes de commits: `"billones"` | 0 resultados | Refutación de la cifra económica |
| V3_PERFORMANCE_TARGETS.md fijado a Engine main | Método documentado y ejecución no medida en ese expediente | Resultado de otra versión o benchmark posterior |
| PR730, metadatos/cuerpo leídos | 11.3288x en dos promedios de adquisición RPC | Latencia de 11 us; percentiles calibrados; acceso previo |
| T37_CLOSEOUT.json fijado a Engine main | Estrés sintético y autoridad comercial ausente | 50,000 mercados de producción o ingresos reales |
| API de artefactos del run T37 36278420240 | Artifact10918475121, `expired=false`, 9,997,371 bytes | Contenido del ZIP verificado; el archivo no fue descargado ni reejecutado |

La disponibilidad del artefacto se observó como metadato, no se infiere de ello integridad, repetibilidad o el supuesto resultado de 11 us. No se activó ningún workflow. La lectura se detuvo porque esas magnitudes no resuelven el bloqueo de financiación/captura ya identificado.

## Qué mide el resultado cercano

El [PR730](https://github.com/josuechavando350-png/nexus-engine/pull/730), cuyo head observado es `e1c8435badc24a64b2e58329b4d0ad80f4d843eb`, reporta dos pasadas secuenciales con media 4.528000195 s frente a dos de Multicall3 con media 0.399687732 s para nueve cuentas Aave. Su cociente es aproximadamente 11.3288x. Se lee el reporte del autor; aquí no se reejecuta el benchmark ni se descarga su artefacto11930913376. El cuerpo de un PR puede cambiar: el head identifica código, no congela todo su texto histórico.

El experimento corresponde a adquisición sobre un bloque ya minado. No cubre el intervalo desde que una señal privada estuvo disponible hasta el corte del builder, ni confirma precio de subasta, financiación o victoria. La frase 11.3288x no puede convertirse mediante cambio de etiqueta en 11 microsegundos.

En [V3_PERFORMANCE_TARGETS.md](https://github.com/josuechavando350-png/nexus-engine/blob/380eff1fc14336bd24d93c8ef807525a7078950d/docs/research/V3_PERFORMANCE_TARGETS.md), la ausencia de mediciones aplica al expediente V3 de ese archivo. No refuta resultados futuros o de otra versión; exige encontrar su evidencia particular.

## Cantidades que no deben sumarse como mercados

| Cantidad | Unidad y alcance documentados | Estado de esta revisión |
| --- | --- | --- |
| 523,424 | Filas históricas de pools Uniswap V2 | REPORTADO por Census; leído en cierre, no recuento de todos los payloads aquí |
| 67 | Reservas Aave del inventario histórico | REPORTADO y distinto de pools |
| 514,279 | Fichas de tokens | REPORTADO en el ledger de auditoría; no recuperadas íntegramente aquí |
| 1,045,459 | Fuentes de capital reconstruidas | REPORTADO; no un número de mercados |
| 14,407,412 | Coordenadas bloque/activo = 215,036 x 67 | Producto recalculable exacto; no 14 millones de mercados únicos |
| 50,000 | Mercados sintéticos de T37 | VERIFICADO_DOCUMENTALMENTE en closeout |
| 250,000 | Superficies sintéticas de T37 | VERIFICADO_DOCUMENTALMENTE en closeout |
| 1,000,000 | Señales sintéticas de estrés T37 | VERIFICADO_DOCUMENTALMENTE; no oportunidades |

Fuentes: [Census CLOSEOUT](https://github.com/josuechavando350-png/nexus-quant-capital/blob/6693542e675f930a7ef0a4fd60cb72e7a6608845/migration/census_v2/CLOSEOUT.md), [CLAIM_LEDGER](https://github.com/josuechavando350-png/nexus-quant-capital/blob/ddade5d099e19449e0c4e55079a2b0c9d9ee1141/migration/cross-repo-evidence-audit-20261017/CLAIM_LEDGER.json), [T37_CLOSEOUT](https://github.com/josuechavando350-png/nexus-engine/blob/380eff1fc14336bd24d93c8ef807525a7078950d/ci/nqc-t37/T37_CLOSEOUT.json).

T37 declara `production_latency_claim=NONE`, `real_live_market_evidence=false` y `live_pnl_evidence=false`. Leer esos campos demuestra el límite de la certificación reportada; no emite otra certificación ni califica la ejecución en producción.

## Evidencia que cambiaría el dictamen

Para 11 us: archivo/commit original, función y tramo medidos, CPU/OS, compilador y flags, carga, muestras crudas, relojes, calentamiento, p50/p95/p99 con método, fecha y procedimiento reproducible. Aun si un hot path alcanzara ese valor, habría que sumar y medir red, estado, simulación, construcción, entrega y admisión por separado.

Para $14,000 billones: fuente exacta, literal numérico sin ambigüedad regional, moneda y fecha, escala larga/corta, magnitud financiera definida, universo y deduplicación, método de conversión. Hasta entonces el dato no se utiliza como TVL, volumen, capital disponible, oportunidad ni P&L de NQC.
