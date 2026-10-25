# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 456 liquidaciones directas con margen (muestra de 96), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 1% y llegaríamos tarde en 99% (99% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $786 en empate, de $101.4 k en la ventana (neto del modelo $0 + $689).
- **En vivo** (1.4 h, 2,588 bloques): 5 decisiones, 2 GO, 0 liquidaciones reales; latencia visto+proceso p50 477 ms, p90 776 ms.
- **Puertas del Omega (Shadow)**: 3 cumple, 4 parcial.

## 1. Margen de tiempo (replay histórico)

Muestra: 300 reconstruidas de 1,212 liquidaciones con bono ≥ mínimo (2,647 en total), que cubren 77% del bono. Sin dato: 0, censuradas (≥ ventana): 0, con error: 0, residuos de liquidaciones parciales: 1.

Bloques entre el cruce (primer bloque liquidable) y la liquidación:

| Distancia | Directas | Subasta | Bono directo (est.) | % del bono |
|---|---|---|---|---|
| mismo bloque | 95 | 204 | $100.6 k | 99% |
| 1 bloque | 1 | 0 | $786 | 1% |
| 2 bloques | 0 | 0 | $0 | 0% |
| 3 a 5 bloques | 0 | 0 | $0 | 0% |
| 6 a 15 bloques | 0 | 0 | $0 | 0% |
| 16 o más | 0 | 0 | $0 | 0% |

**Si tu tiempo total** (visto + decisión + envío) es… Solo directas con bono ≥ $10 y neto ≥ $5, sin deuda mala (96 en la muestra):

| Tiempo total | Llegas antes | Empate | Llegas tarde |
|---|---|---|---|
| hasta 2 s | 0% · $0 | 1% · $786 | 99% · $100.6 k |
| hasta 4 s | 0% · $0 | 0% · $0 | 100% · $101.4 k |
| hasta 6 s | 0% · $0 | 0% · $0 | 100% · $101.4 k |

Cada celda: % de las liquidaciones · bono estimado. «Tarde» = alguien liquidó antes de que tu transacción pudiera caer.

Vía: directa 96 ($101.4 k), subasta 204 ($544.2 k). Las de subasta no son para un actor pequeño (el bono se cede en la puja).
Distancia de las directas: mediana 0 bloques, p90 0, máx 1.
Costo de quien ganó (directas): gas mediano $1.45 (p90 $34.26), propina mediana $0.91 (p90 $34.25).
Quién se lleva el bono directo: 68 firmantes distintos en la muestra; el mayor 12%, los 3 mayores 32%, los 10 mayores 65%.
Cuándo cae: 9 días con liquidaciones directas; los 3 mejores días tienen 96% del bono (el mejor, 82%).
Control contra el Census: bono directo estimado $101.4 k vs $99.6 k del Census (102%).

Por mercado (directas):

| Mercado | n | Bono (est.) | Mediana (bloques) | ≥ 2 bloques |
|---|---|---|---|---|
| cbXRP/USDC lltv 62.5% | 56 | $58.2 k | 0 | 0% |
| cbETH/USDC lltv 77.0% | 25 | $32.2 k | 0 | 0% |
| cbZEC/USDC lltv 62.5% | 4 | $8,159 | 0 | 0% |
| WETH/USDC lltv 86.0% | 9 | $2,703 | 0 | 0% |
| SOL/USDC lltv 62.5% | 1 | $69 | 0 | 0% |
| AERO/USDC lltv 62.5% | 1 | $66 | 0 | 0% |
| JitoSOL/USDC lltv 62.5% | 0 | $0 | — | — |
| cbADA/USDC lltv 62.5% | 0 | $0 | — | — |

### Diagnóstico del oráculo (muestra de las liquidaciones directas más grandes)

De 96 liquidaciones miradas bloque a bloque: la posición ya era liquidable un bloque antes en 1; el precio de Morpho cambió en el mismo bloque de la liquidación en 95; algún feed del oráculo cambió de ronda en ese bloque en 95.
En 91 hubo una actualización del feed en el mismo bloque, antes de la liquidación (mediana 102 transacciones antes); quien actualizó fue el mismo actor que liquidó en 0.

Separación entre la actualización del oráculo y la liquidación, dentro del mismo bloque (91 casos): mediana 102 transacciones, p90 535 (≈ 5% del bloque, unos 90 ms; p90 323 ms). Tramos: pegada (hasta 1 tx) 12, hasta 10 tx 13, hasta 100 tx 20, más de 100 tx 46.
Según cómo se actualizó el oráculo: por la subasta OEV 66 (mediana 150 tx, unos 93 ms); por un transmisor normal 25 (mediana 50 tx, unos 74 ms).
Prioridad que pagó la liquidación frente a la de la actualización: igual 14, mayor 52, menor 25. Dentro de un trozo de 200 ms las transacciones se ordenan por prioridad: pagar más y caer después de la actualización implica un trozo posterior; pagar igual o menos no descarta el mismo trozo.
_Los milisegundos son una aproximación: suponen que las transacciones se reparten parejo en los 2 s del bloque; el sello exacto de cada transacción solo se ve en vivo, por trozos de 200 ms._
- Oráculo 0x031b…0fde: BASE_FEED_1 = XRP / USD (0x9f0c…6d34)
- Oráculo 0x96f1…2269: BASE_FEED_1 = AERO / USD (0x4ec5…cff0), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x97ff…8295: BASE_FEED_1 = CBETH / USD (0xd781…817d)
- Oráculo 0xa3cb…a272: BASE_FEED_1 = ZEC / USD (0xc4a1…4890)

## 2. En vivo

Ventana: 1.44 h, bloques 53061133–53063720 (2,588 de 2,588, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 329 ms | 537 ms | 1,435 ms |
| Proceso (leer + decidir) | 115 ms | 316 ms | 4,760 ms |
| Visto + proceso | 477 ms | 776 ms | 5,949 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 42 ms, logs 0 ms, lectura 38 ms, evaluar 4 ms.
Logs: 2,001 de 2,588 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: GO:ok 2, NO-GO:deuda_mala 3.
GO: 2 (bono $1, neto del modelo $0). Desenlace: expirada 2.
2 GO tienen el cruce incierto (ya eran liquidables al arrancar o se detectaron tras un hueco); no cuentan en la llegada.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 44 ms, 50,911 fotos; trozos nuevos cada 197 ms (mediana).
- Perfil de los bloques (2,578 vistos desde el principio): mediana 126 transacciones por bloque en 11 trozos (≈ 10 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 25%, 31%, 39%, 48%, 57%, 64%, 73%, 81%, 88%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Evaluador del estado pendiente: 0 cruces vistos antes de sellarse el bloque (0 GO); decidimos — después de ver el trozo (p90 —); lectura del estado pendiente p50 62 ms. Desenlace: ninguno.
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 4 dentro del 2%, deuda $5,007, la más cercana a 0.29% de caída.

## 3. ¿La matemática coincide con la cadena?

Replay: 91 de 92 liquidaciones coinciden exactamente con la matemática de Morpho (92 dentro de 1e-9; 92 incluyen interés acumulado). Error máximo 1.78e-14, omitidas 0.
Libro en vivo: 43348 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ✅ cumple | 2 de 2 GO con desenlace conocido (expirada 2) |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | ✅ cumple | paridad 91/92 exacta, máx 1.8e-14; libro sin deriva (43348 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 477 ms, p90 776 ms, p99 5,949 ms (n=2033); medida desde GitHub Actions, no desde la infraestructura de Titan |
| Detección competitiva (replay) | 🟡 parcial | 96 liquidaciones directas elegibles reconstruidas; versión mínima del túnel (cruce → liquidación), no reproduce NQC completo |
| Economía con costos completos | 🟡 parcial | bono × retención observada en el Census (incluye swap, gas y propinas de los ganadores reales); no se simuló nuestra ruta ni su liquidez |

## 5. Qué NO prueba este Shadow

- La latencia se mide desde un servidor de GitHub Actions hacia RPC públicos. La infraestructura real (nodo propio, cercanía al secuenciador de Base, Titan) puede ser mejor o peor: es una referencia conservadora, no una certificación.
- No se envió nada, así que no se midió el envío (se supone 150 ms), ni la inclusión, ni el orden dentro del bloque.
- Un empate (llegar en el mismo bloque que el ganador) lo decide la propina y el orden del secuenciador: aquí solo se cuenta.
- Los bloques de Base son de 2 s y el timestamp es entero. Con Flashblocks (200 ms) algunos bots ven antes del bloque: las liquidaciones en el mismo bloque del cruce no se pueden ganar sin ver antes de que el bloque cierre.
- El replay solo ve posiciones que terminaron liquidadas; las que se recuperaron o quedaron sin liquidar las mide el modo en vivo.
- El neto usa la retención observada del Census (bono × proporción que se quedaron los ganadores); no es una ejecución simulada con nuestra ruta, liquidez, flash loan ni slippage.
- El gas y la propina del replay son los de quien ganó, no los nuestros.
- Una ventana corta no sustituye semanas de Shadow ni cubre los picos: en el Census el 95% del margen cayó en 3 de 30 días.

## Fuentes

- Priors: census run 40141321042 (24 sep–24 oct 2026), Base/Morpho, 30 días.
- Envío supuesto: 150 ms. Bloque: 2000 ms.
- Archivos leídos: {"vivo": {"bloques": 2588, "decisiones": 5, "resultados": 5, "lineas_cortadas": 0, "meta": true}, "replay": {"filas": 300, "errores": 0, "lineas_cortadas": 0, "meta": true}, "lupa": {"filas": 96}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
