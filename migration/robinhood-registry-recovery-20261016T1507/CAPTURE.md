# Recuperación completada; 26.6934% de cobertura y cero candidatos en la muestra

El 16/oct/2026 **15:17:38.064878–15:18:04.626210 UTC** (09:17–09:18 Ciudad de México) terminó una única captura: **56 métodos RPC / 56 HTTP, cero errores, salida 0**. Journal 26.561335300 s; runner 26.582011681 s; proceso completo 26.885143152 s. La recuperación se verificó por replay offline exacto. No hubo trading, firmas, transacciones ni gastos.

[PR22 borrador](https://github.com/josuechavando350-png/nexus-quant-capital/pull/22). Protocolo publicado **antes** de la captura: [`1b850c9bb8a31ae5f8f083431c8d822e5419c854`](https://github.com/josuechavando350-png/nexus-quant-capital/commit/1b850c9bb8a31ae5f8f083431c8d822e5419c854), árbol `2961582b305451dc42ba6a268ebccb32a7d55fee`. Sus 101 fuentes registradas permanecen intactas. Este informe es posterior y no cambia reglas, política, código ni lock. La captura está terminada: no relanzar el runner.

## Qué avanzó

Se separó la cota acumulada de bloques con eventos (256) del límite por segmento/respuesta (128). Los límites de 64 cuentas, 512 eventos, bytes, gas de lectura, presupuesto y gate permanecen. La unión que falló en PR21 ahora se recuperó desde ambas fuentes conservadas, revalidando canon y sin consultar otra vez sus logs históricos.

| Parte | Bloques | Borrow | Cuentas nuevas respecto al principal PR21 |
|---|---:|---:|---:|
| Historia guardada 87446281–87846280, incorporada sin reescanear | 400000 | 20 | 2 |
| Cola nueva 90109722–90178727 | 69006 | 13 | 2 |
| Registro acumulado 87446281–90178727 | **2732447** | **158** | **56 cuentas totales** |

Se preservan ambas fuentes originales y `merged-before-catchup.json`. Los segmentos antiguos conservan logs, eventos y cabeceras; se reconstruyen los enlaces `previous_segment_sha256` del principal al unir. No se afirma identidad byte a byte de esos enlaces. No hay huecos. Target completo y contratos/mercado autenticados antes de congelar todas las cuentas, incluidas las de deuda cero.

## Qué dice la muestra económica

Tres hashes distintos: bloques **90178936, 90178947 y 90178958**. En los tres: **47 cuentas con deuda / nueve sin deuda**, **26.6934174575%** de borrowShares cubierto, **73.3065825425%** pendiente; **cero candidatos y cero cuentas calculadas como liquidables**. Son resultados de esta muestra/cohorte, no hechos actuales garantizados ni ausencia universal de oportunidades.

La cohorte previa de 52 cuentas, evaluada en estos mismos hashes, cubre **26.2000137557%**. Las dos cuentas recuperadas de historia aportan **0.0726990570 puntos**; las dos de cola, **0.4207046448 puntos**. Las cuatro tenían deuda. Su aporte total es 0.4934037018 puntos; **no atribuirles toda la diferencia frente al 24.8973% de PR20**, medido antes. Los shares observados 237005522019876377 y los faltantes 650874504570925690 suman el total 887880026590802067.

Durante observación quedaron 209–231 bloques posteriores al anchor sin indexar. No se simuló una ruta nueva ni se midieron captura competitiva, envío/inclusión, coste AA/Nitro/DA, patrocinio financiado o beneficio. La deuda observada no es ingreso.

## Latencia y límites conservados

Cinco verificaciones, cero consultas de historia, 38 de catch-up, cuatro de autenticación y nueve de observación: 47 de preparación / nueve de medida. Una sesión y gate/presupuesto global sin rotaciones, retries o rescate. Esperas **12.641461092 s** incluidas; separación mínima de despachos **350.167510 ms**, cero infracciones. Primera petición de preparación **3848.357386 ms** conservada.

Adquisición completa desde **antes de admisión de cabecera**: **989.818230 / 1051.684424 / 1047.189116 ms**, mediana 1047.189116 ms, solo 1/3 ≤1 s. La secundaria desde despacho local es 811.209702–813.570599 ms y no sustituye la primaria. Intervalos entre despachos de cabecera 1051.207691 / 1050.980720 ms; admisiones 990.952406 / 1053.115131 ms. Un intervalo aislado menor de 1 s no acredita cadencia sostenida subsegundo. No se midió una adquisición fría completa ni se repitió el benchmark de transporte. Las nueve peticiones de observación reutilizaron el socket cliente por el proxy existente; no prueba conexión backend, SLA ni cuota futura.

## Verificación y financiación pendiente

**55 pruebas Python distintas aprobadas**: 47 antes (17 recuperación/capacidad, diez motor previo, siete informe PR21, cuatro diagnóstico previo, nueve aislamiento) y ocho del informe posterior. Se auditaron 35 fronteras RPC sintéticas interrumpidas, incluidos fallos HTTP/JSON/RPC después de unir y antes de catch-up, presupuestos globales, reorgs y alteraciones de archivos. Dos trazas artificiales quedan separadas de las fuentes reales. Replay real exacto aprobado. Un control de whitespace antes del primer commit rechazó dos líneas vacías finales; se quitaron y se repitieron las 17 pruebas afectadas antes de publicar, sin cambio de lógica.

Nueve manifiestos PR13–PR21 intactos, 377 blobs originales conservados, 106 workflows deshabilitados y cero activos. Rust/Solidity no cambiaron ni se ejecutaron de nuevo. APIs y dependencias heredadas; no nueva API de transporte.

La restricción comercial es **cero capital principal propio**. La evidencia histórica anterior de rutas y financiación atómica conserva su alcance de simulación; esta captura no la vuelve financiación disponible. El siguiente análisis debe precisar qué mecanismo ya usa la ruta Morpho (callback/flash según el código verificado), qué falta para una oportunidad actual y qué tercero aporta gas y asume fallos con presupuesto efectivo. No basta etiquetar un servicio como paymaster. No hay sponsor comprometido ni fondos externos acreditados en este incremento.

Confianza técnica alta en la recuperación y contabilidad de esta muestra; **rentabilidad repetible y financiación comercial todavía no probadas**.

## Evidencia

- [Resumen](evidence/summary.json), [auditoría](evidence/audit.json), [recibo de proceso](evidence/process-receipt.json).
- [Registro actual](evidence/pilot/registry.json), [estado antes de catch-up](evidence/pilot/merged-before-catchup.json), ambos inputs originales en `evidence/pilot/`.
- [Journal](evidence/pilot/journal.jsonl), [peticiones](evidence/pilot/requests.json), [admisiones](evidence/pilot/admissions.json), respuestas originales.
- [Verificación posterior](evidence/verification/post-capture.json), `MANIFEST.sha256` y [continuidad](CONTINUITY.md).

Registro actual: raíz `c415105959ea642599deccd7ce690b38325e7480351c5082bda4c03d8cd52643`, SHA archivo `e586db0dff1feaeddcfc12e95f30b1ca2bda6a09bb50a5043f58012c497c4382`. Próxima cola desde 90178728. No volver a la fuente PR20/21 ni reescanear la historia ya recuperada.
