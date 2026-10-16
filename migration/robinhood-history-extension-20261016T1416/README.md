# Historia conservada; unión detenida por capacidad de bloques con eventos

**Resultado: parada preservada, no captura exitosa.** El 16/oct/2026 14:18:27.483494–14:19:23.811698 UTC se recorrieron los 400000 bloques previstos y se verificó su anchor. La unión con el índice previo se detuvo por `REGISTRY_CAPACITY_NO_TRIMMING`. No hubo catch-up, autenticación de target nuevo, cohorte congelada ni observaciones actuales: **cobertura, candidatos y rentabilidad actuales NO medidos**.

El [protocolo publicado antes de RPC](https://github.com/josuechavando350-png/nexus-quant-capital/commit/1d7a779b4d21921bc2f446b6e3fc34bf98132187), árbol `ab2dbbfe3fb897f2c9f862eb9763919d9bc6281e`, permanece intacto. Base PR20 `976aecb3e25118b1531772d7778668ee34b97d61`. Motor PR19 y adaptadores heredados sin cambios de comportamiento; nueva política de fuente/ventana.

## Qué se conservó y qué no avanzó

| Archivo/estado | Intervalo | Borrow | Cuentas |
|---|---|---:|---:|
| Índice principal, idéntico a PR20 | 87846281–90109721 | 125 | 52 |
| Historia separada, completa y guardada | 87446281–87846280 | 20 | 11 |
| Unión calculada solo para diagnóstico, NO persistida | Ambos intervalos | 145 | 54 únicas |

Hay dos cuentas nuevas en la historia separada y nueve ya conocidas. No se consultó su deuda/salud actual. La historia guardada NO equivale a índice principal actualizado ni a cohorte válida para observación. No existen `merged-before-catchup.json` ni `cohort.json`. El índice principal conserva 2263441 bloques; no sumar los 400000 como si la unión ya hubiera terminado.

## Causa exacta, reproducida offline

| Recurso acumulado de la unión propuesta | Cantidad | Límite registrado | Excedido |
|---|---:|---:|---|
| Eventos Borrow | 145 | 512 | No |
| Bloques distintos con eventos | 145 | 128 | **Sí** |
| Cuentas | 54 | 64 | No |

La reconstrucción alcanza 128 eventos/bloques y 49 cuentas; al anexar el segmento fuente 89696281–89706280 propone129 bloques con eventos y rechaza. `registry.validate` combina tres límites bajo el mismo mensaje. La primera actualización verbal atribuyó la parada a cuentas; el diagnóstico posterior la corrigió: **el límite alcanzado fue el de bloques con eventos, no el de cuentas**.

El parámetro `max_event_blocks` se usa tanto al validar respuestas/selección de un segmento como al validar todo el registro acumulado. Este acoplamiento explica que la historia completa individual y la fuente individual pasen, pero su unión no. No se cambió ningún límite después de medir. [capacity_diagnosis.py](capacity_diagnosis.py) reproduce la primera unión rechazada y [su recibo](evidence/capacity-diagnosis.json) conserva cantidades y hashes, sin RPC ni archivo de unión provisional.

## Ejecución

145 métodos RPC/145 HTTP: tres verificaciones iniciales y142 consultas históricas. Todos devolvieron HTTP200; cero errores RPC/transportes, pero **una parada local** y salida1. Última petición `history-anchor-after-index`; ninguna consulta posterior al rechazo. Journal56.328205968s, proceso56.346451685s. Esperas35.482757769s dentro del plazo global, gapmínimo350.154858ms, cero infracciones del gate. Primera petición3.948800s conservada.

No se repitió el proceso, no se recortaron cuentas/eventos ni se cambió proveedor/sesión/límite. Único presupuesto512métodos/900s y gate350ms. La ausencia de observaciones (0/3) NO significa cero candidatos ni constituye medición de latencia completa. No se midieron ruta/envío/inclusión/gas/AA/Nitro/DA/financiación. No ingresos, transacciones, firmas o gastos.

## Fuentes para recuperar, sin reescanear

1. Índice principal PR20, copiado sin cambios en [pilot/registry.json](evidence/pilot/registry.json): raíz `c6b124c940c29d2a876e9d3efdafaf6c678e5654aa1cabcdb2de1309fd4e1a86`; SHA archivo `915da8d32ebea82d9999f23a827a934faa6daef0c105eeeaceb6208fbd58ba5f`.
2. Historia nueva separada [pilot/older-registry.json](evidence/pilot/older-registry.json): raíz `1c2ef15961ad7d1d3552afad9eee4aaeb8cabaf54e62b92e9e2c56477f675076`; SHA archivo `83e307af76b631167350471366ac9d44713a9ecbd21613150bca3411745abceb`. `valid_prefix`,40 segmentos completos,87446281–87846280.

Ambas fuentes requieren revalidación canónica en un futuro protocolo antes de unir y actualizar cola. Son evidencia histórica, no garantía del canon futuro.

## Verificación y próximo paso

**43 pruebas Python distintas aprobadas**:32 previas, siete de informe y cuatro del diagnóstico de capacidad. Replay real exacto de parada y presencia/bytes de archivos aprobado.85 fuentes fijadas y ocho manifiestos PR13–PR20 intactos;377 blobs originales,106 workflows deshabilitados,cero activos. Rust/Solidity sin cambios ni nueva ejecución.

Evidencia: [summary](evidence/summary.json), [audit](evidence/audit.json), [journal](evidence/pilot/journal.jsonl), [requests](evidence/pilot/requests.json), [admissions](evidence/pilot/admissions.json), [pruebas](evidence/verification/post-capture.json), cuerpos originales y `MANIFEST.sha256`. `errors=0` en el resumen cuenta únicamente fallos RPC; `terminal` registra el rechazo local.

Siguiente incremento: **separar capacidad acumulada del índice de límites por respuesta/segmento**, probar offline una cota acumulada explícita (propuesta256 bloques con eventos) manteniendo128 por segmento,64cuentas,512eventos y límitesRPC/bytes/tiempo. Publicar protocolo NUEVO de recuperación que consuma ambas fuentes, revalide fronteras, una sin huecos y actualice cola desde90109722. No reescanear87446281–87846280 ni ampliar más historia antes de recuperar. Preservar cualquier nueva parada; ninguna elevación retroactiva de este protocolo.

Confianza alta en el diagnóstico y evidencia conservada; no hay nueva evidencia económica. Captura repetible rentable, financiación y patrocinio siguen sin demostrar.
