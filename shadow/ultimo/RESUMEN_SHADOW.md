# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 454 liquidaciones directas con margen (muestra de 454), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 1% y llegaríamos tarde en 99% (100% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $313 en empate, de $101.8 k en la ventana (neto del modelo $0 + $250).
- **Quién gana dentro del bloque** (lupa de 454 liquidaciones directas): 64% (≈ $60.8 k) del bono lo ganó quien reaccionó en un trozo posterior al de la actualización (se puede competir con velocidad y propina); 2% (≈ $2,284) quien se coló en el mismo trozo justo después de la actualización (vio la actualización antes de que se confirmara: otra clase de infraestructura); 25% (≈ $23.6 k) iba empaquetado con la actualización (subasta OEV: no hay carrera); 9% (≈ $8,342) es ambiguo.
- **En vivo** (3.7 h, 6,717 bloques): 5 decisiones, 2 GO, 0 liquidaciones reales; latencia visto+proceso p50 514 ms, p90 755 ms.
- **Puertas del Omega (Shadow)**: 2 cumple, 5 parcial.

## 1. Margen de tiempo (replay histórico)

Muestra: 1,213 reconstruidas de 1,213 liquidaciones con bono ≥ mínimo (2,648 en total), que cubren 100% del bono. Sin dato: 0, censuradas (≥ ventana): 0, con error: 0, residuos de liquidaciones parciales: 1.

Bloques entre el cruce (primer bloque liquidable) y la liquidación:

| Distancia | Directas | Subasta | Bono directo (est.) | % del bono |
|---|---|---|---|---|
| mismo bloque | 449 | 759 | $101.5 k | 100% |
| 1 bloque | 5 | 0 | $313 | 0% |
| 2 bloques | 0 | 0 | $0 | 0% |
| 3 a 5 bloques | 0 | 0 | $0 | 0% |
| 6 a 15 bloques | 0 | 0 | $0 | 0% |
| 16 o más | 0 | 0 | $0 | 0% |

**Si tu tiempo total** (visto + decisión + envío) es… Solo directas con bono ≥ $10 y neto ≥ $5, sin deuda mala (454 en la muestra):

| Tiempo total | Llegas antes | Empate | Llegas tarde |
|---|---|---|---|
| hasta 2 s | 0% · $0 | 1% · $313 | 99% · $101.5 k |
| hasta 4 s | 0% · $0 | 0% · $0 | 100% · $101.8 k |
| hasta 6 s | 0% · $0 | 0% · $0 | 100% · $101.8 k |

Cada celda: % de las liquidaciones · bono estimado. «Tarde» = alguien liquidó antes de que tu transacción pudiera caer.

Vía: directa 454 ($101.8 k), subasta 759 ($539.8 k). Las de subasta no son para un actor pequeño (el bono se cede en la puja).
Distancia de las directas: mediana 0 bloques, p90 0, máx 1.
Costo de quien ganó (directas): gas mediano $1.27 (p90 $15.27), propina mediana $0.92 (p90 $15.25).
Quién se lleva el bono directo: 160 firmantes distintos en la muestra; el mayor 12%, los 3 mayores 31%, los 10 mayores 56%.
Cuándo cae: 14 días con liquidaciones directas; los 3 mejores días tienen 95% del bono (el mejor, 78%).
Control contra el Census: bono directo estimado $101.8 k vs $99.6 k del Census (102%).

Por mercado (directas):

| Mercado | n | Bono (est.) | Mediana (bloques) | ≥ 2 bloques |
|---|---|---|---|---|
| cbXRP/USDC lltv 62.5% | 271 | $59.6 k | 0 | 0% |
| cbETH/USDC lltv 77.0% | 110 | $31.8 k | 0 | 0% |
| cbZEC/USDC lltv 62.5% | 6 | $6,012 | 0 | 0% |
| WETH/USDC lltv 86.0% | 47 | $3,320 | 0 | 0% |
| cbZEC/USDC lltv 77.0% | 1 | $257 | 0 | 0% |
| cbETH/USDC lltv 86.0% | 2 | $243 | 0 | 0% |
| yoUSD/USDC lltv 91.5% | 1 | $191 | 0 | 0% |
| stkWELL/USDC lltv 62.5% | 2 | $94 | 0 | 0% |

### Diagnóstico del oráculo (muestra de las liquidaciones directas más grandes)

De 454 liquidaciones miradas bloque a bloque: la posición ya era liquidable un bloque antes en 5; el precio de Morpho cambió en el mismo bloque de la liquidación en 448; algún feed del oráculo cambió de ronda en ese bloque en 445.
En 435 hubo una actualización del feed en el mismo bloque, antes de la liquidación (mediana 122 transacciones antes); quien actualizó fue el mismo actor que liquidó en 0.

Separación entre la actualización del oráculo y la liquidación, dentro del mismo bloque (435 casos): mediana 122 transacciones, p90 558 (≈ 4% del bloque, unos 89 ms; p90 397 ms). Tramos: hasta 1 tx 74, hasta 10 tx 58, hasta 100 tx 70, más de 100 tx 233.
Según cómo se actualizó el oráculo: por la subasta OEV 323 (mediana 152 tx, unos 91 ms); por un transmisor normal 112 (mediana 45 tx, unos 74 ms).
Prioridad que pagó la liquidación frente a la de la actualización — pagó más prioridad que la actualización: 249 casos, 65% del bono ($61.7 k); pagó la misma: 51 casos, 25% del bono ($23.9 k); pagó menos: 135 casos, 10% del bono ($9,435). Es una primera lectura: pagar más puede ser un trozo posterior, pero también alguien que se coló tarde en el mismo trozo; la clasificación de abajo lo separa.
**Clasificación por las propinas vecinas** (dentro de un trozo la propina baja; una que sube justo en la liquidación y vuelve al nivel de antes es un pico que entró tarde al mismo trozo; una que está en la cabeza ordenada de otro trozo es una reacción): en un trozo posterior (reaccionó al trozo publicado): 242 casos, 64% del bono ($60.8 k); colada en el mismo trozo, justo tras la actualización (vio la actualización antes de que se confirmara): 24 casos, 2% del bono ($2,284); empaquetada con la actualización (misma propina, subasta OEV): 44 casos, 25% del bono ($23.6 k); ambigua (paga menos que la actualización): 125 casos, 9% del bono ($8,342).
_Los milisegundos son una aproximación: suponen que las transacciones se reparten parejo en los 2 s del bloque; el sello exacto de cada transacción solo se ve en vivo, por trozos de 200 ms._
Orden de propinas en 12 bloques llenos (mediana 3,158 transacciones): la propina sube de una transacción a la siguiente 48 veces por bloque (mediana; p90 101); con las mismas propinas en orden de llegada al azar subiría ≈ 1,277 veces. Un orden por prioridad dentro de cada trozo solo deja subidas al empezar cada trozo (~10) y las de transacciones que dependen de otra del mismo remitente.
- Oráculo 0x031b…0fde: BASE_FEED_1 = XRP / USD (0x9f0c…6d34)
- Oráculo 0x3a7a…ecf7: BASE_FEED_1 = ZEC / USD (0x69e5…6ec0), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x4756…9425: BASE_FEED_1 = cbETH-ETH Exchange Rate (0x868a…5f04), BASE_FEED_2 = ETH / USD (0x7104…bb70), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x47f9…a00d: BASE_FEED_1 = LTC / USD (0x206a…7a69)

## 2. En vivo

Ventana: 3.74 h, bloques 53069736–53076467 (6,717 de 6,732, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 280 ms | 482 ms | 577 ms |
| Proceso (leer + decidir) | 220 ms | 333 ms | 4,569 ms |
| Visto + proceso | 514 ms | 755 ms | 4,778 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 76 ms, logs 0 ms, lectura 58 ms, evaluar 6 ms.
Logs: 3,632 de 6,717 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: GO:ok 2, NO-GO:deuda_mala 3.
GO: 2 (bono $1, neto del modelo $0). Desenlace: expirada 2.
2 GO tienen el cruce incierto (ya eran liquidables al arrancar o se detectaron tras un hueco); no cuentan en la llegada.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 77 ms, 130,920 fotos; trozos nuevos cada 194 ms (mediana).
- Perfil de los bloques (6,659 vistos desde el principio): mediana 159 transacciones por bloque en 11 trozos (≈ 13 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 24%, 32%, 41%, 50%, 59%, 67%, 74%, 82%, 90%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 112 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 65%, queda igual en 34% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 987 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- Evaluador del estado pendiente: 0 cruces vistos antes de sellarse el bloque (0 GO); decidimos — después de ver el trozo (p90 —); lectura del estado pendiente p50 100 ms. Desenlace: ninguno.
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 4 dentro del 2%, deuda $4,960, la más cercana a 0.28% de caída.

## 3. ¿La matemática coincide con la cadena?

Replay: 250 de 256 liquidaciones coinciden exactamente con la matemática de Morpho (256 dentro de 1e-9; 256 incluyen interés acumulado). Error máximo 6.86e-13, omitidas 0.
Libro en vivo: 113919 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 1, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | 🟡 parcial | 2 de 2 GO con desenlace conocido (expirada 2); todos con cruce incierto (ya eran liquidables al arrancar): no miden una carrera |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 1 saltos de atraso (15 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | ✅ cumple | paridad 250/256 exacta, máx 6.9e-13; libro sin deriva (113919 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 514 ms, p90 755 ms, p99 4,778 ms (n=6543); medida desde GitHub Actions, no desde la infraestructura de Titan |
| Detección competitiva (replay) | 🟡 parcial | 454 liquidaciones directas elegibles reconstruidas; versión mínima del túnel (cruce → liquidación), no reproduce NQC completo |
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
- Archivos leídos: {"vivo": {"bloques": 6717, "decisiones": 5, "resultados": 5, "lineas_cortadas": 0, "meta": true}, "replay": {"filas": 1213, "errores": 0, "lineas_cortadas": 0, "meta": true}, "lupa": {"filas": 454}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
