# Shadow Base/Morpho · 2026-11-03

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (5.5 h, 9,912 bloques): 5 decisiones, 0 GO, 0 liquidaciones reales; latencia visto+proceso p50 532 ms, p90 765 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 3 sin datos.

**Financiación requerida: gas de Titan y principal de préstamo flash; aportación propia cero.**
Capturas de entrada para simular la ruta propia: 5/5 decisiones. El neto del modelo usa retención histórica de terceros; el neto propio y el beneficio realizado siguen sin calcular.
Pendientes: liquidez y comisión del préstamo, salida del swap, repago atómico, cobertura de Titan en esta cadena y para esta candidata, gas y compensación del builder. Un dato faltante no equivale a coste cero.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 5.51 h, bloques 53454362–53464273 (9,912 de 9,912, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 256 ms | 439 ms | 568 ms |
| Proceso (leer + decidir) | 235 ms | 388 ms | 4,314 ms |
| Visto + proceso | 532 ms | 765 ms | 4,554 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 80 ms, logs 0 ms, lectura 63 ms, evaluar 10 ms.
Logs: 5,586 de 9,912 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:deuda_mala 5.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 82 ms, 193,741 fotos; trozos nuevos cada 189 ms (mediana).
- Perfil de los bloques (7,781 vistos desde el principio): mediana 180 transacciones por bloque en 11 trozos (≈ 15 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 25%, 32%, 41%, 50%, 59%, 67%, 76%, 83%, 91%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 150 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 66%, queda igual en 32% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 1301 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- WebSocket (wss://mainnet-preconf.base.org): suscripciones logs ok, transacciones ok; 2,061,592 transacciones y 698 logs recibidos; 3 conexiones; errores {'WsError: conexión cerrada por el servidor': 1, 'WsError: el servidor cerró el WebSocket': 1}; silencio entre trozos p50 167 ms.
- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): 227 actualizaciones; decidir tomó p50 1 ms (p90 5 ms, máx 7 ms) desde que llegó la actualización, sin consultar a la red (evaluar el libro: p50 1 ms, máx 6.9 ms); el WebSocket trajo la actualización 53 ms antes que la consulta del bloque pendiente (p50, n=225); 0 cruces vistos así, 0 liquidados.
- Prueba del clasificador «mismo trozo / trozo posterior» con 89 bloques de trozos conocidos: reconoce el comienzo de un trozo en 100% de 801 fronteras, un pico dentro del trozo en 78% de 166 (el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en 99% de 2397.
- Evaluador del estado pendiente: 0 cruces vistos antes de sellarse el bloque (0 GO); decidimos — después de ver el trozo (p90 —); lectura del estado pendiente p50 105 ms. Desenlace: ninguno.
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 30 dentro del 2%, deuda $115.5 k, la más cercana a 0.13% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 170509 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (4 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (170509 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 532 ms, p90 765 ms, p99 4,554 ms (n=9708); medida desde GitHub Actions, no desde la infraestructura de Titan |
| Detección competitiva (replay) | ⚪ sin datos | este reporte no incluye un replay |
| Economía con costos completos | ⚪ sin datos | este reporte no incluye un replay |

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
- Archivos leídos: {"vivo": {"bloques": 9912, "decisiones": 5, "resultados": 5, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs.
