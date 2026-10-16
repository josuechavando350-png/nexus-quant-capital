# Extensión histórica: 52 cuentas, cobertura 24.8973%

Captura única completada el **16/oct/2026 13:20:32.903052–13:21:47.168513 UTC**. Se amplió historia y cola sin huecos, se autenticó target y se congeló la cohorte antes de observar. Mejora técnica verificada; ninguna oportunidad liquidable en los tres bloques observados y ninguna demostración de rentabilidad.

El [protocolo c0fc579](https://github.com/josuechavando350-png/nexus-quant-capital/commit/c0fc579e3ec4ea68dcf5c77c4dc6c3d40333bd94), árbol `d686f2f3286cf9fd2ec5d95189d5139558f65fcf`, se publicó ANTES de RPC. Base PR19 `ca184cdd14d8d5a8a4d447a9723a0e792dc00132`. Sus fuentes, política y captura permanecen intactas. Se reutilizó el motor PR19 sin cambios, con nuevos adaptadores de carga/auditoría y política de ventana/fuente explícita; no se ejecutó su main con la ventana antigua.

## Qué añadió esta captura

| Intervalo | Bloques | Borrow | Cuentas nuevas |
|---|---:|---:|---:|
| Historia 87846281–88246280 | 400000 | 25 | 5 |
| Cola 90080878–90109721 | 28844 | 3 | 1 |
| Acumulado 87846281–90109721 | 2263441 | 125 | 52 totales |

Selección por ventana contigua, independiente de salud y liquidaciones conocidas. Todas las cuentas se conservaron, incluidas deuda cero. El límite64 no se alcanzó ni cambió. Fuente original y estado antes de catch-up guardados; al unir se reconstruyeron enlaces SHA de segmentos, conservando sus eventos/respuestas/checkpoints, sin afirmar identidad de enlaces reconstruidos.

Fuente nueva [evidence/pilot/registry.json](evidence/pilot/registry.json), `valid_prefix`, target completo:

- Raíz `c6b124c940c29d2a876e9d3efdafaf6c678e5654aa1cabcdb2de1309fd4e1a86`.
- SHA256 archivo `915da8d32ebea82d9999f23a827a934faa6daef0c105eeeaceb6208fbd58ba5f`.

## Cobertura conciliada en los mismos hashes

Bloques 90109855, 90109865 y 90109876, tres hashes únicos conservados. En cada uno: 52 cuentas, **41 con deuda y 11 sin deuda**, cero candidatos y cero cuentas calculadas como liquidables. Tail aún sin indexar tras anchor: 134–155 bloques.

| Conjunto evaluado en esos mismos bloques | Cobertura de totalBorrowShares |
|---|---:|
| Cohorte previa de 46 cuentas | 23.8713121115% |
| Cinco cuentas históricas nuevas | +0.5190967695 puntos |
| Una cuenta nueva de cola | +0.5068800851 puntos |
| Cohorte ampliada | 24.8972889661% |
| Falta observar | 75.1027110339% |

Solo una de las cinco cuentas históricas nuevas tenía deuda en esta muestra; las otras cuatro se conservan. La cuenta nueva de cola también tenía deuda. El aporte histórico es modesto en esta ventana: no demuestra que otras ventanas rindan igual ni permite descartar cuentas por salud. La cola reciente aportó casi tantos puntos como el tramo histórico completo, pero con una sola cuenta y un periodo diferente; no es una comparación causal de estrategias.

Total conciliado `871574026861359854` borrowShares, observadas `216998304021420074`, faltantes `654575722839939780`. La diferencia respecto al 23.8120% de PR19 no es toda atribuible a nuevas cuentas: la cohorte anterior cubría ahora 23.8713%. Participaciones de deuda NO son dólares, ingresos ni beneficio. Cero candidatos solo describe esta cohorte/estos tres bloques; no ausencia universal de oportunidades.

## Ejecución y latencia

180 métodos RPC/180 HTTP, cero errores, salida0. Journal74.265462399s; proceso74.281850080s. Desglose: 4 verificaciones,147 historia,16 cola,4 autenticación,9 observación. Esperas43.572649098s incluidas en un único plazo900s; mismo contador512/gate350ms/sesión en todas las fases, sin rotaciones. Gap mínimo350.148641ms, cero infracciones. La primera petición de preparación tardó9992.204ms y se retuvo; no es una medición de adquisición fría completa.

Adquisición completa primaria, desde ANTES de admisión de cabecera hasta estado verificado: **936.004229,1109.214298,1051.182297ms**. Mediana1051.182297ms; solo1/3≤1000ms. Secundaria desde despacho sin espera inicial:751.384596–813.684149ms, no sustituye primaria. Entrada lens75.611–83.278ms.

Intervalos de despacho de cabecera1051.539110/1051.215917ms; admisión939.034326/1110.842186ms. El intervalo aislado menor no prueba cadencia sostenida subsegundo. Solo tres lecturas de cobertura; no benchmark nuevo ni garantía de cuota/SLA. Nueve peticiones de observación reutilizaron el socket cliente por el proxy configurado; no prueba conexión backend. No se midieron ruta/envío/inclusión/gas/EntryPoint/AA/Nitro/DA/bundler/patrocinio financiado o ingresos.

## Pruebas y evidencia reproducible

**39 pruebas Python distintas aprobadas**:32 previas (seis nuevas de política/adaptadores,10 regresiones del motor con43fronteras sintéticas, siete del informe real PR19, nueve aislamiento) y siete del nuevo informe real. Se reutiliza la cobertura de interrupciones existente, sin reimplementarla ni presentarla como descubrimiento nuevo. Replay real exacto de journal, ledger, admisiones y cuatro archivos de estado.

76 fuentes fijadas sin cambios. Siete manifiestos PR13–PR19 intactos. 377 blobs originales intactos,106 workflows deshabilitados,cero activos. Rust/Solidity sin cambios ni nueva ejecución. Recibos: [preflight](evidence/verification/preflight.json), [post-capture](evidence/verification/post-capture.json), [proceso](evidence/process-receipt.json). Archivos finales fijados en `MANIFEST.sha256`.

[Resumen](evidence/summary.json), [auditoría](evidence/audit.json), [journal](evidence/pilot/journal.jsonl), [HTTP](evidence/pilot/requests.json), [admisiones](evidence/pilot/admissions.json) y cuerpos originales permiten ver todos los valores, sin eliminar lentos o negativos.

Confianza técnica alta en esta muestra auditada; evidencia comercial insuficiente. Siguiente historia contigua:87446281–87846280, bajo protocolo NUEVO. Próxima cola desde90109722. No relanzar este runner terminado. Si aparecen candidatos, evaluar supervivencia y ciclo completo con costes/fallos y patrocinio prepagado viable, sin trading ni envíos reales autorizados.
