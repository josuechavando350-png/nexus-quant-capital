# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (0.3 h, 567 bloques): 5 decisiones, 0 GO, 0 liquidaciones reales; latencia visto+proceso p50 817 ms, p90 1,052 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 3 sin datos.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 0.31 h, bloques 53050679–53051245 (567 de 567, cobertura 100%).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 269 ms | 467 ms | 577 ms |
| Proceso (leer + decidir) | 475 ms | 702 ms | 4,505 ms |
| Visto + proceso | 817 ms | 1,052 ms | 4,590 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 85 ms, logs 118 ms, lectura 6 ms, evaluar 233 ms.

Decisiones: NO-GO:bono_bajo 2, NO-GO:deuda_mala 3.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).
Última foto de posiciones cerca del umbral: 3 dentro del 2%, deuda $4,894, la más cercana a 0.30% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 7600 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (4 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (7600 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 817 ms, p90 1,052 ms, p99 4,590 ms (n=534); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 567, "decisiones": 5, "resultados": 0, "lineas_cortadas": 0, "meta": true}, "replay": {"filas": 0, "errores": 0, "lineas_cortadas": 0, "meta": false}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs.
