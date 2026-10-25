# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 441 liquidaciones directas con margen (muestra de 284), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 1% y llegaríamos tarde en 99% (100% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $474 en empate, de $98.8 k en la ventana (neto del modelo $0 + $377).
- **Dentro del bloque** (lupa de 284 liquidaciones directas): 66% (≈ $60.4 k) del bono lo ganaron bots que pagaron más prioridad que la actualización del oráculo y cayeron en un trozo posterior (reaccionaron: se puede competir); 25% (≈ $22.8 k) iba empaquetado con la actualización (misma prioridad: no hay carrera); 9% (≈ $7,928) es ambiguo.
- **En vivo** (3.3 h, 5,969 bloques): 5 decisiones, 2 GO, 1 liquidaciones reales; latencia visto+proceso p50 456 ms, p90 652 ms.
- **Puertas del Omega (Shadow)**: 3 cumple, 4 parcial.

## 1. Margen de tiempo (replay histórico)

Muestra: 800 reconstruidas de 1,212 liquidaciones con bono ≥ mínimo (2,647 en total), que cubren 89% del bono. Sin dato: 0, censuradas (≥ ventana): 0, con error: 0, residuos de liquidaciones parciales: 1.

Bloques entre el cruce (primer bloque liquidable) y la liquidación:

| Distancia | Directas | Subasta | Bono directo (est.) | % del bono |
|---|---|---|---|---|
| mismo bloque | 280 | 516 | $98.3 k | 100% |
| 1 bloque | 4 | 0 | $474 | 0% |
| 2 bloques | 0 | 0 | $0 | 0% |
| 3 a 5 bloques | 0 | 0 | $0 | 0% |
| 6 a 15 bloques | 0 | 0 | $0 | 0% |
| 16 o más | 0 | 0 | $0 | 0% |

**Si tu tiempo total** (visto + decisión + envío) es… Solo directas con bono ≥ $10 y neto ≥ $5, sin deuda mala (284 en la muestra):

| Tiempo total | Llegas antes | Empate | Llegas tarde |
|---|---|---|---|
| hasta 2 s | 0% · $0 | 1% · $474 | 99% · $98.3 k |
| hasta 4 s | 0% · $0 | 0% · $0 | 100% · $98.8 k |
| hasta 6 s | 0% · $0 | 0% · $0 | 100% · $98.8 k |

Cada celda: % de las liquidaciones · bono estimado. «Tarde» = alguien liquidó antes de que tu transacción pudiera caer.

Vía: directa 284 ($98.8 k), subasta 516 ($543.9 k). Las de subasta no son para un actor pequeño (el bono se cede en la puja).
Distancia de las directas: mediana 0 bloques, p90 0, máx 1.
Costo de quien ganó (directas): gas mediano $1.45 (p90 $21.76), propina mediana $1.08 (p90 $21.42).
Quién se lleva el bono directo: 136 firmantes distintos en la muestra; el mayor 14%, los 3 mayores 33%, los 10 mayores 59%.
Cuándo cae: 12 días con liquidaciones directas; los 3 mejores días tienen 95% del bono (el mejor, 77%).
Control contra el Census: bono directo estimado $98.8 k vs $99.6 k del Census (99%).

Por mercado (directas):

| Mercado | n | Bono (est.) | Mediana (bloques) | ≥ 2 bloques |
|---|---|---|---|---|
| cbXRP/USDC lltv 62.5% | 163 | $53.9 k | 0 | 0% |
| cbETH/USDC lltv 77.0% | 76 | $34.6 k | 0 | 0% |
| cbZEC/USDC lltv 62.5% | 5 | $6,532 | 0 | 0% |
| WETH/USDC lltv 86.0% | 24 | $2,269 | 0 | 0% |
| cbZEC/USDC lltv 77.0% | 1 | $409 | 0 | 0% |
| cbETH/USDC lltv 86.0% | 1 | $315 | 0 | 0% |
| yoUSD/USDC lltv 91.5% | 1 | $303 | 0 | 0% |
| stkWELL/USDC lltv 62.5% | 2 | $150 | 0 | 0% |

### Diagnóstico del oráculo (muestra de las liquidaciones directas más grandes)

De 284 liquidaciones miradas bloque a bloque: la posición ya era liquidable un bloque antes en 4; el precio de Morpho cambió en el mismo bloque de la liquidación en 279; algún feed del oráculo cambió de ronda en ese bloque en 276.
En 267 hubo una actualización del feed en el mismo bloque, antes de la liquidación (mediana 117 transacciones antes); quien actualizó fue el mismo actor que liquidó en 0.

Separación entre la actualización del oráculo y la liquidación, dentro del mismo bloque (267 casos): mediana 117 transacciones, p90 557 (≈ 4% del bloque, unos 89 ms; p90 397 ms). Tramos: hasta 1 tx 43, hasta 10 tx 43, hasta 100 tx 45, más de 100 tx 136.
Según cómo se actualizó el oráculo: por la subasta OEV 190 (mediana 151 tx, unos 92 ms); por un transmisor normal 77 (mediana 45 tx, unos 68 ms).
Prioridad que pagó la liquidación frente a la de la actualización — pagó más prioridad que la actualización (reaccionó en un trozo posterior): 159 casos, 66% del bono ($60.4 k); pagó la misma (empaquetada con la actualización: no hay carrera): 32 casos, 25% del bono ($22.8 k); pagó menos (puede ser el mismo trozo o uno posterior): 76 casos, 9% del bono ($7,928). Dentro de un trozo de 200 ms las transacciones se ordenan por prioridad: pagar más y caer después de la actualización implica un trozo posterior.
_Los milisegundos son una aproximación: suponen que las transacciones se reparten parejo en los 2 s del bloque; el sello exacto de cada transacción solo se ve en vivo, por trozos de 200 ms._
Orden de propinas en 12 bloques llenos (mediana 3,158 transacciones): la propina sube de una transacción a la siguiente 48 veces por bloque (mediana; p90 101). Si cada trozo se ordena por prioridad, los ascensos son del orden de uno por trozo (~10) más los de transacciones que dependen de otra del mismo remitente; si el orden fuera de llegada, serían muchos más.
- Oráculo 0x031b…0fde: BASE_FEED_1 = XRP / USD (0x9f0c…6d34)
- Oráculo 0x3a7a…ecf7: BASE_FEED_1 = ZEC / USD (0x69e5…6ec0), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x4756…9425: BASE_FEED_1 = cbETH-ETH Exchange Rate (0x868a…5f04), BASE_FEED_2 = ETH / USD (0x7104…bb70), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x47f9…a00d: BASE_FEED_1 = LTC / USD (0x206a…7a69)

## 2. En vivo

Ventana: 3.32 h, bloques 53063743–53069711 (5,969 de 5,969, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 213 ms | 378 ms | 490 ms |
| Proceso (leer + decidir) | 220 ms | 327 ms | 1,748 ms |
| Visto + proceso | 456 ms | 652 ms | 2,091 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 59 ms, logs 0 ms, lectura 139 ms, evaluar 8 ms.
Logs: 4,167 de 5,969 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: GO:ok 2, NO-GO:deuda_mala 3.
GO: 2 (bono $1, neto del modelo $0). Desenlace: expirada 2.
2 GO tienen el cruce incierto (ya eran liquidables al arrancar o se detectaron tras un hueco); no cuentan en la llegada.
Liquidaciones reales en la ventana: 1 (bono $31). Clases: mismo_bloque 1. Vía: directa 1.

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 54 ms, 116,782 fotos; trozos nuevos cada 197 ms (mediana).
- Directas medidas: 1: en el mismo trozo que la actualización del oráculo 1 ($31). Reacción tras la actualización: mediana 0 ms, p90 0 ms.
- Perfil de los bloques (5,930 vistos desde el principio): mediana 137 transacciones por bloque en 11 trozos (≈ 11 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 24%, 31%, 39%, 49%, 58%, 65%, 73%, 81%, 89%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 100 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 66%, queda igual en 33% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 884 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- Evaluador del estado pendiente: 0 cruces vistos antes de sellarse el bloque (0 GO); decidimos — después de ver el trozo (p90 —); lectura del estado pendiente p50 74 ms. Desenlace: ninguno.
- 1 liquidaciones reales no se vieron cruzar antes en el estado pendiente (el precio y la liquidación llegaron en el mismo trozo).
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 26 dentro del 2%, deuda $7,446, la más cercana a 0.29% de caída.

## 3. ¿La matemática coincide con la cadena?

Replay: 186 de 191 liquidaciones coinciden exactamente con la matemática de Morpho (191 dentro de 1e-9; 191 incluyen interés acumulado). Error máximo 6.86e-13, omitidas 0.
Libro en vivo: 99925 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ✅ cumple | 2 de 2 GO con desenlace conocido (expirada 2) |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | ✅ cumple | paridad 186/191 exacta, máx 6.9e-13; libro sin deriva (99925 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 456 ms, p90 652 ms, p99 2,091 ms (n=5833); medida desde GitHub Actions, no desde la infraestructura de Titan |
| Detección competitiva (replay) | 🟡 parcial | 284 liquidaciones directas elegibles reconstruidas; versión mínima del túnel (cruce → liquidación), no reproduce NQC completo |
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
- Archivos leídos: {"vivo": {"bloques": 5969, "decisiones": 5, "resultados": 6, "lineas_cortadas": 0, "meta": true}, "replay": {"filas": 800, "errores": 0, "lineas_cortadas": 0, "meta": true}, "lupa": {"filas": 284}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
