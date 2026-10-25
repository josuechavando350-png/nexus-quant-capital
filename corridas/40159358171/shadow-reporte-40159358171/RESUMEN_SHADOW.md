# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 362 liquidaciones directas con margen (muestra de 7, muestra pequeña), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 0% y llegaríamos tarde en 100% (100% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $0 en empate, de $27.8 k en la ventana (neto del modelo $0 + $0).
- **En vivo**: sin datos.
- **Puertas del Omega (Shadow)**: 4 parcial, 3 sin datos.

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
Sonda de Flashblocks (https:….org): 400 consultas, latencia p50 26 ms; trozos nuevos del bloque pendiente: 199, cada 198 ms (p90 250 ms).
Quién se lleva el bono directo: 7 firmantes distintos en la muestra; el mayor 40%, los 3 mayores 80%, los 10 mayores 100%.
Cuándo cae: 1 días con liquidaciones directas; los 3 mejores días tienen 100% del bono (el mejor, 100%).
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

## 2. En vivo

Sin datos del modo en vivo.

## 3. ¿La matemática coincide con la cadena?

Replay: 14 de 14 liquidaciones coinciden exactamente con la matemática de Morpho (14 dentro de 1e-9; 14 incluyen interés acumulado). Error máximo 0.00e+00, omitidas 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | 🟡 parcial | solo métodos de lectura, pero ninguna decisión en la ventana |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | ⚪ sin datos | sin corrida en vivo |
| Simulaciones: divergencias investigadas | 🟡 parcial | paridad 14/14 exacta, máx 0.0e+00 |
| Latencia en infraestructura real | ⚪ sin datos | sin bloques con latencia medida |
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
- Archivos leídos: {"replay": {"filas": 30, "errores": 0, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
