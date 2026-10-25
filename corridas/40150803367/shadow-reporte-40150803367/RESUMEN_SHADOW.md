# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: de unas 456 liquidaciones directas con margen (muestra de 96), con un tiempo total de hasta 2 s llegaríamos antes en 0% de los casos (0% del bono), empataríamos en 1% y llegaríamos tarde en 99% (99% del bono: liquidadas en el mismo bloque del cruce).
- Bono directo ganable estimado (hasta 2 s): $0 antes + $786 en empate, de $101.4 k en la ventana (neto del modelo $0 + $689).
- **En vivo** (0.3 h, 493 bloques): 5 decisiones, 0 GO, 0 liquidaciones reales; latencia visto+proceso p50 512 ms, p90 751 ms.
- **Puertas del Omega (Shadow)**: 2 cumple, 4 parcial, 1 sin datos.

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
Costo de quien ganó (directas): gas mediano $1.46 (p90 $34.51), propina mediana $0.92 (p90 $34.50).
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

## 2. En vivo

Ventana: 0.27 h, bloques 53051264–53051756 (493 de 493, cobertura 100%).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 276 ms | 484 ms | 553 ms |
| Proceso (leer + decidir) | 203 ms | 407 ms | 4,037 ms |
| Visto + proceso | 512 ms | 751 ms | 3,927 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 68 ms, logs 0 ms, lectura 125 ms, evaluar 2 ms.
Logs: 312 de 493 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:bono_bajo 2, NO-GO:deuda_mala 3.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).
Última foto de posiciones cerca del umbral: 3 dentro del 2%, deuda $4,894, la más cercana a 0.30% de caída.

## 3. ¿La matemática coincide con la cadena?

Replay: 91 de 92 liquidaciones coinciden exactamente con la matemática de Morpho (92 dentro de 1e-9; 92 incluyen interés acumulado). Error máximo 1.78e-14, omitidas 0.
Libro en vivo: 7600 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | ✅ cumple | paridad 91/92 exacta, máx 1.8e-14; libro sin deriva (7600 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 512 ms, p90 751 ms, p99 3,927 ms (n=467); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 493, "decisiones": 5, "resultados": 0, "lineas_cortadas": 0, "meta": true}, "replay": {"filas": 300, "errores": 0, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
