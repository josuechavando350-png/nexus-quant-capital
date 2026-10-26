# Shadow Base/Morpho · 2026-10-26

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 454 liquidaciones directas con margen (muestra de 454), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 1% y llegaríamos tarde en 99% (100% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $313 en empate, de $101.8 k en la ventana (neto del modelo $0 + $250).
- **Quién gana dentro del bloque** (lupa de 454 liquidaciones directas): 64% (≈ $60.8 k) del bono lo ganó quien reaccionó en un trozo posterior al de la actualización (se puede competir con velocidad y propina); 2% (≈ $2,284) quien se coló en el mismo trozo justo después de la actualización (vio la actualización antes de que se confirmara: otra clase de infraestructura); 25% (≈ $23.6 k) iba empaquetado con la actualización (subasta OEV: no hay carrera); 9% (≈ $8,342) es ambiguo.
- **Rivales** (lupa de 454): en 71% del bono al menos otro bot lo intentó y perdió; el segundo perdió por llegar tarde en 22% del bono y por pagar menos en el mismo trozo en 39% (mínimo: solo se ven los bots que llevan la dirección del prestatario en sus datos).
- **En vivo** (5.5 h, 9,902 bloques): 6 decisiones, 2 GO, 4 liquidaciones reales; latencia visto+proceso p50 591 ms, p90 845 ms.
- **Puertas del Omega (Shadow)**: 2 cumple, 5 parcial.

## 1. Margen de tiempo (replay histórico)

Muestra: 1,213 reconstruidas de 1,213 liquidaciones con bono ≥ mínimo (2,650 en total), que cubren 100% del bono. Sin dato: 0, censuradas (≥ ventana): 0, con error: 0, residuos de liquidaciones parciales: 1.

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
Costo de quien ganó (directas): gas mediano $1.27 (p90 $15.25), propina mediana $0.92 (p90 $15.23).
Quién se lleva el bono directo: 160 firmantes distintos en la muestra; el mayor 12%, los 3 mayores 31%, los 10 mayores 56%.
Cuándo cae: 15 días con liquidaciones directas; los 3 mejores días tienen 90% del bono (el mejor, 52%).
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

**Rivales que perdieron** (454 liquidaciones con el bloque leído entero; rival = otra transacción con la dirección del prestatario en sus datos, de otro bot): hubo al menos uno en 394 (71% del bono); bots rivales por liquidación: mediana 3, p90 12, máx 37.
Dónde quedó el segundo (el primer rival detrás del ganador) — en el trozo del ganador, detrás, pagando lo mismo o menos (perdió por propina): 138 (39% del bono); en un trozo posterior (llegó tarde): 80 (12% del bono); detrás del ganador pagando más (llegó tarde: con esa propina, a tiempo habría ido primero): 135 (10% del bono); solo antes del ganador (disparó antes de tiempo y falló): 41 (10% del bono).
Propina del segundo frente a la del ganador: mediana 0.818× (p90 125.46×, n=352).
De las que se ganaron reaccionando en un trozo posterior (las que se pueden competir): 222 de 242 tuvieron rivales; el segundo quedó mismo trozo menos propina 115, trozo posterior 63, tarde con mas propina 27, sin rivales 20, solo antes 17.
Bots que más aparecen (ganó / perdió): 0xcee7…863d 43/189; 0x9a03…e88c 29/156; 0xc4bf…fc51 112/73; 0xc124…0e3a 6/123; 0x561b…fc54 0/118; 0x87a6…f658 8/107.
_Es un mínimo: un bot que esconde o comprime la dirección no aparece. El ganador la llevaba en sus datos en 323 de 454; 87 listas recortadas a 40 intentos._
- Oráculo 0x031b…0fde: BASE_FEED_1 = XRP / USD (0x9f0c…6d34)
- Oráculo 0x3a7a…ecf7: BASE_FEED_1 = ZEC / USD (0x69e5…6ec0), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x4756…9425: BASE_FEED_1 = cbETH-ETH Exchange Rate (0x868a…5f04), BASE_FEED_2 = ETH / USD (0x7104…bb70), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x47f9…a00d: BASE_FEED_1 = LTC / USD (0x206a…7a69)

## 2. En vivo

Ventana: 5.50 h, bloques 53119648–53129549 (9,902 de 9,902, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 250 ms | 436 ms | 558 ms |
| Proceso (leer + decidir) | 342 ms | 484 ms | 3,633 ms |
| Visto + proceso | 591 ms | 845 ms | 3,782 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 99 ms, logs 94 ms, lectura 60 ms, evaluar 8 ms.
Logs: 4,826 de 9,902 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: GO:ok 2, NO-GO:bono_bajo 1, NO-GO:deuda_mala 3.
GO: 2 (bono $3, neto del modelo $2). Desenlace: expirada 2.
2 GO tienen el cruce incierto (ya eran liquidables al arrancar o se detectaron tras un hueco); no cuentan en la llegada.
Liquidaciones reales en la ventana: 4 (bono $1). Clases: con_aviso 1, mismo_bloque 3. Vía: directa 3, subasta 1.
Avisadas antes de ocurrir, de las que se podían ver: 100%.

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 84 ms, 194,438 fotos; trozos nuevos cada 197 ms (mediana).
- Directas medidas: 3: en el mismo trozo que la actualización del oráculo 1 ($0), en el siguiente trozo 1 ($0), sin actualización localizada 1 ($0). Reacción tras la actualización: mediana 193 ms, p90 193 ms.
- Subastas medidas: 1: sin actualización localizada 1 ($1).
- Perfil de los bloques (9,820 vistos desde el principio): mediana 188 transacciones por bloque en 11 trozos (≈ 15 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 25%, 31%, 39%, 47%, 57%, 66%, 74%, 82%, 90%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 150 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 66%, queda igual en 33% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 1331 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- WebSocket (wss://mainnet-preconf.base.org): suscripciones logs ok, transacciones ok; 2,035,751 transacciones y 628 logs recibidos; 4 conexiones; errores {'WsError: conexión cerrada por el servidor': 3}; silencio entre trozos p50 166 ms.
- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): 202 actualizaciones; decidir tomó p50 1 ms (p90 3 ms, máx 35 ms) desde que llegó la actualización, sin consultar a la red (evaluar el libro: p50 0.9 ms, máx 35.2 ms); el WebSocket trajo la actualización 53 ms antes que la consulta del bloque pendiente (p50, n=202); 4 cruces vistos así, 2 liquidados.
- Holgura de la vía rápida frente al ganador (envío supuesto de 20 ms): positiva en 0 de 2; mediana -19 ms.
- Ventana medida por WebSocket entre la actualización del oráculo y la liquidación del ganador: mediana 0 ms, mín 0 ms, máx 0 ms (n=2). Es el tiempo que hubo para ver, decidir y enviar.
- **Rivales que perdieron** (4 liquidaciones con el bloque leído entero; rival = otra transacción con la dirección del prestatario en sus datos, de otro bot): hubo al menos uno en 1 (98% del bono); bots rivales por liquidación: mediana 0, p90 4, máx 4.
- Dónde quedó el segundo (el primer rival detrás del ganador) — detrás del ganador pagando más (llegó tarde: con esa propina, a tiempo habría ido primero): 1 (98% del bono).
- Propina del segundo frente a la del ganador: mediana 25.021× (p90 25.021×, n=1); llegó por WebSocket 402 ms después que el ganador (mediana, n=1).
- De las que se ganaron reaccionando en un trozo posterior (las que se pueden competir): 0 de 1 tuvieron rivales; el segundo quedó sin rivales 1.
- Bots que más aparecen (ganó / perdió): 0x3c96…73be 2/0.
- _Es un mínimo: un bot que esconde o comprime la dirección no aparece. El ganador la llevaba en sus datos en 4 de 4._
  - cbBTC/USDC lltv 86.0%, bono $1: 4 intentos rivales; el segundo quedó tarde con mas propina, 402 ms después por WebSocket, trozo 4 (0x7501…523b).
  - cbETH/USDC lltv 77.0%, bono $0: 0 intentos rivales (0x4f9f…4963).
  - cbETH/USDC lltv 77.0%, bono $0: 0 intentos rivales (0x01f5…f9a9).
  - cbETH/USDC lltv 77.0%, bono $0: 0 intentos rivales (0x7bc7…c1db).
- Prueba del clasificador «mismo trozo / trozo posterior» con 131 bloques de trozos conocidos: reconoce el comienzo de un trozo en 100% de 1179 fronteras, un pico dentro del trozo en 81% de 318 (el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en 99% de 3504.
- Evaluador del estado pendiente: 4 cruces vistos antes de sellarse el bloque (0 GO); decidimos 138 ms después de ver el trozo (p90 143 ms); lectura del estado pendiente p50 109 ms. Desenlace: liquidada 3, no_liquidada_en_el_bloque 1.
- Holgura frente al ganador (nuestra transacción habría llegado 150 ms después de decidir): positiva en 1 de 3 (bono $0 de $1); mediana -190 ms; el ganador entró en el mismo trozo en que lo vimos en 1.
- 1 liquidaciones reales no se vieron cruzar antes en el estado pendiente (el precio y la liquidación llegaron en el mismo trozo).
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 30 dentro del 2%, deuda $16.6 k, la más cercana a 0.31% de caída.

## 3. ¿La matemática coincide con la cadena?

Replay: 250 de 256 liquidaciones coinciden exactamente con la matemática de Morpho (256 dentro de 1e-9; 256 incluyen interés acumulado). Error máximo 6.86e-13, omitidas 0.
Libro en vivo: 168215 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 1, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 6 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | 🟡 parcial | 2 de 2 GO con desenlace conocido (expirada 2); todos con cruce incierto (ya eran liquidables al arrancar): no miden una carrera |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 1 saltos de atraso (15 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | ✅ cumple | paridad 250/256 exacta, máx 6.9e-13; libro sin deriva (168215 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 591 ms, p90 845 ms, p99 3,782 ms (n=9743); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 9902, "decisiones": 6, "resultados": 9, "lineas_cortadas": 0, "meta": true}, "replay": {"filas": 1213, "errores": 0, "lineas_cortadas": 0, "meta": true}, "lupa": {"filas": 454}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
