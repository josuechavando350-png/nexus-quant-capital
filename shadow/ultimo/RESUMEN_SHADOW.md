# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (0.2 h, 376 bloques): 5 decisiones, 0 GO, 0 liquidaciones reales; latencia visto+proceso p50 534 ms, p90 780 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 3 sin datos.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 0.21 h, bloques 53055492–53055867 (376 de 376, cobertura 100%).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 282 ms | 497 ms | 565 ms |
| Proceso (leer + decidir) | 219 ms | 449 ms | 3,968 ms |
| Visto + proceso | 534 ms | 780 ms | 4,340 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 83 ms, logs 0 ms, lectura 127 ms, evaluar 4 ms.
Logs: 216 de 376 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:bono_bajo 2, NO-GO:deuda_mala 3.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 85 ms, 5,824 fotos; trozos nuevos cada 195 ms (mediana).
Última foto de posiciones cerca del umbral: 4 dentro del 2%, deuda $4,895, la más cercana a 0.29% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 4800 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (4 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (4800 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 534 ms, p90 780 ms, p99 4,340 ms (n=361); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 376, "decisiones": 5, "resultados": 0, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs.
