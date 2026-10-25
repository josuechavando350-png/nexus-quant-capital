# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 456 liquidaciones directas con margen (muestra de 96), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 1% y llegaríamos tarde en 99% (99% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $786 en empate, de $101.4 k en la ventana (neto del modelo $0 + $689).
- **En vivo**: sin datos.
- **Puertas del Omega (Shadow)**: 4 parcial, 3 sin datos.

## 1. Margen de tiempo (replay histórico)

Muestra: 300 reconstruidas de 1,212 liquidaciones con bono ≥ mínimo (2,646 en total), que cubren 77% del bono. Sin dato: 0, censuradas (≥ ventana): 0, con error: 0, residuos de liquidaciones parciales: 1.

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
Costo de quien ganó (directas): gas mediano $1.46 (p90 $34.56), propina mediana $0.92 (p90 $34.55).
Quién se lleva el bono directo: 68 firmantes distintos en la muestra; el mayor 12%, los 3 mayores 32%, los 10 mayores 65%.
Cuándo cae: 8 días con liquidaciones directas; los 3 mejores días tienen 96% del bono (el mejor, 82%).
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

De 14 liquidaciones miradas bloque a bloque: la posición ya era liquidable un bloque antes en 0; el precio de Morpho cambió en el mismo bloque de la liquidación en 14; algún feed del oráculo cambió de ronda en ese bloque en 14.
En 11 hubo una actualización del feed en el mismo bloque, antes de la liquidación (mediana 3 transacciones antes); quien actualizó fue el mismo actor que liquidó en 0.
- Oráculo 0x031b…0fde: BASE_FEED_1 = XRP / USD (0x9f0c…6d34)
- Oráculo 0x96f1…2269: BASE_FEED_1 = AERO / USD (0x4ec5…cff0), QUOTE_FEED_1 = USDC / USD (0x7e86…bc6b)
- Oráculo 0x97ff…8295: BASE_FEED_1 = CBETH / USD (0xd781…817d)
- Oráculo 0xa3cb…a272: BASE_FEED_1 = ZEC / USD (0xc4a1…4890)

## 2. En vivo

Sin datos del modo en vivo.

## 3. ¿La matemática coincide con la cadena?

Replay: 91 de 92 liquidaciones coinciden exactamente con la matemática de Morpho (92 dentro de 1e-9; 92 incluyen interés acumulado). Error máximo 1.78e-14, omitidas 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | 🟡 parcial | solo métodos de lectura, pero ninguna decisión en la ventana |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | ⚪ sin datos | sin corrida en vivo |
| Simulaciones: divergencias investigadas | 🟡 parcial | paridad 91/92 exacta, máx 1.8e-14 |
| Latencia en infraestructura real | ⚪ sin datos | sin bloques con latencia medida |
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
- Archivos leídos: {"replay": {"filas": 300, "errores": 0, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
