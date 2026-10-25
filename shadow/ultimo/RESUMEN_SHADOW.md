# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (2.2 h, 3,943 bloques): 5 decisiones, 0 GO, 1 liquidaciones reales; latencia visto+proceso p50 460 ms, p90 676 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 3 sin datos.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 2.19 h, bloques 53057166–53061108 (3,943 de 3,943, cobertura 100%).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 242 ms | 418 ms | 538 ms |
| Proceso (leer + decidir) | 221 ms | 321 ms | 3,747 ms |
| Visto + proceso | 460 ms | 676 ms | 2,610 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 77 ms, logs 0 ms, lectura 89 ms, evaluar 7 ms.
Logs: 2,980 de 3,943 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:bono_bajo 2, NO-GO:deuda_mala 3.
Liquidaciones reales en la ventana: 1 (bono $0). Clases: mismo_bloque 1. Vía: directa 1.

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 79 ms, 77,538 fotos; trozos nuevos cada 195 ms (mediana).
- Directas medidas: 1: en el siguiente trozo 1 ($0). Reacción tras la actualización: mediana 201 ms, p90 201 ms.
- Evaluador del estado pendiente: 1 cruces vistos antes de sellarse el bloque (0 GO); decidimos 112 ms después de ver el trozo (p90 112 ms); lectura del estado pendiente p50 97 ms. Desenlace: liquidada 1.
- Holgura frente al ganador (nuestra transacción habría llegado 150 ms después de decidir): positiva en 0 de 1 (bono $0 de $0); mediana -61 ms; el ganador entró en el mismo trozo en que lo vimos en 0.
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 4 dentro del 2%, deuda $5,007, la más cercana a 0.29% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 67340 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (67340 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 460 ms, p90 676 ms, p99 2,610 ms (n=3887); medida desde GitHub Actions, no desde la infraestructura de Titan |
| Detección competitiva (replay) | ⚪ sin datos | el replay no produjo liquidaciones directas elegibles |
| Economía con costos completos | ⚪ sin datos | sin liquidaciones elegibles |

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
- Archivos leídos: {"vivo": {"bloques": 3943, "decisiones": 5, "resultados": 6, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
