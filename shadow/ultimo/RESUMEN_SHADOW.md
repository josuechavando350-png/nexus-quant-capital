# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 362 liquidaciones directas con margen (muestra de 7, muestra pequeña), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 0% y llegaríamos tarde en 100% (100% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $0 en empate, de $27.8 k en la ventana (neto del modelo $0 + $0).
- **En vivo** (0.2 h, 330 bloques): 5 decisiones, 0 GO, 0 liquidaciones reales; latencia visto+proceso p50 365 ms, p90 555 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 5 parcial, 1 sin datos.

## 1. Margen de tiempo (replay histórico)

Muestra: 30 reconstruidas de 1,212 liquidaciones con bono ≥ mínimo (2,646 en total), que cubren 25% del bono. Sin dato: 0, censuradas (≥ ventana): 0, con error: 0, residuos de liquidaciones parciales: 0.

Bloques entre el cruce (primer bloque liquidable) y la liquidación:

| Distancia | Directas | Subasta | Bono directo (est.) | % del bono |
|---|---|---|---|---|
| mismo bloque | 7 | 23 | $27.8 k | 100% |
| 1 bloque | 0 | 0 | $0 | 0% |
| 2 bloques | 0 | 0 | $0 | 0% |
| 3 a 5 bloques | 0 | 0 | $0 | 0% |
| 6 a 15 bloques | 0 | 0 | $0 | 0% |
| 16 o más | 0 | 0 | $0 | 0% |

**Si tu tiempo total** (visto + decisión + envío) es… Solo directas con bono ≥ $10 y neto ≥ $5, sin deuda mala (7 en la muestra):

| Tiempo total | Llegas antes | Empate | Llegas tarde |
|---|---|---|---|
| hasta 2 s | 0% · $0 | 0% · $0 | 100% · $27.8 k |
| hasta 4 s | 0% · $0 | 0% · $0 | 100% · $27.8 k |
| hasta 6 s | 0% · $0 | 0% · $0 | 100% · $27.8 k |

Cada celda: % de las liquidaciones · bono estimado. «Tarde» = alguien liquidó antes de que tu transacción pudiera caer.

Vía: directa 7 ($27.8 k), subasta 23 ($1.02 M). Las de subasta no son para un actor pequeño (el bono se cede en la puja).
Distancia de las directas: mediana 0 bloques, p90 0, máx 0.
Costo de quien ganó (directas): gas mediano $1.51 (p90 $8.86), propina mediana $1.31 (p90 $8.79).
Quién se lleva el bono directo: 7 firmantes distintos en la muestra; el mayor 40%, los 3 mayores 80%, los 10 mayores 100%.
Cuándo cae: 2 días con liquidaciones directas; los 3 mejores días tienen 100% del bono (el mejor, 97%).
Control contra el Census: bono directo estimado $27.8 k vs $99.6 k del Census (28%).

Por mercado (directas):

| Mercado | n | Bono (est.) | Mediana (bloques) | ≥ 2 bloques |
|---|---|---|---|---|
| cbETH/USDC lltv 77.0% | 2 | $13.4 k | 0 | 0% |
| cbXRP/USDC lltv 62.5% | 4 | $12.6 k | 0 | 0% |
| JitoSOL/USDC lltv 62.5% | 1 | $1,830 | 0 | 0% |
| SOL/USDC lltv 62.5% | 0 | $0 | — | — |
| WETH/USDC lltv 86.0% | 0 | $0 | — | — |
| cbADA/USDC lltv 62.5% | 0 | $0 | — | — |
| cbLTC/USDC lltv 62.5% | 0 | $0 | — | — |
| cbZEC/USDC lltv 62.5% | 0 | $0 | — | — |

### Diagnóstico del oráculo (muestra de las liquidaciones directas más grandes)

De 7 liquidaciones miradas bloque a bloque: la posición ya era liquidable un bloque antes en 0; el precio de Morpho cambió en el mismo bloque de la liquidación en 7; algún feed del oráculo cambió de ronda en ese bloque en 6.
En 6 hubo una actualización del feed en el mismo bloque, antes de la liquidación (mediana 95 transacciones antes); quien actualizó fue el mismo actor que liquidó en 0.
- Oráculo 0x031b…0fde: BASE_FEED_1 = XRP / USD (0x9f0c…6d34)
- Oráculo 0x78f7…be1c: 
- Oráculo 0x97ff…8295: BASE_FEED_1 = CBETH / USD (0xd781…817d)

## 2. En vivo

Ventana: 0.18 h, bloques 53056814–53057143 (330 de 330, cobertura 100%).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 182 ms | 348 ms | 438 ms |
| Proceso (leer + decidir) | 157 ms | 273 ms | 515 ms |
| Visto + proceso | 365 ms | 555 ms | 725 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 17 ms, logs 0 ms, lectura 130 ms, evaluar 6 ms.
Logs: 233 de 330 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:bono_bajo 2, NO-GO:deuda_mala 3.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 16 ms, 5,931 fotos; trozos nuevos cada 199 ms (mediana).
- Evaluador del estado pendiente: 5 cruces vistos antes de sellarse el bloque (0 GO); decidimos 575 ms después de ver el trozo (p90 575 ms); lectura del estado pendiente p50 34 ms. Desenlace: no_liquidada_en_el_bloque 5.
Última foto de posiciones cerca del umbral: 4 dentro del 2%, deuda $4,895, la más cercana a 0.29% de caída.

## 3. ¿La matemática coincide con la cadena?

Replay: 14 de 14 liquidaciones coinciden exactamente con la matemática de Morpho (14 dentro de 1e-9; 14 incluyen interés acumulado). Error máximo 0.00e+00, omitidas 0.
Libro en vivo: 5200 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | paridad 14/14 exacta, máx 0.0e+00; libro sin deriva (5200 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 365 ms, p90 555 ms, p99 725 ms (n=318); medida desde GitHub Actions, no desde la infraestructura de Titan |
| Detección competitiva (replay) | 🟡 parcial | 7 liquidaciones directas elegibles reconstruidas; versión mínima del túnel (cruce → liquidación), no reproduce NQC completo |
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
- Archivos leídos: {"vivo": {"bloques": 330, "decisiones": 5, "resultados": 0, "lineas_cortadas": 0, "meta": true}, "replay": {"filas": 30, "errores": 0, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
