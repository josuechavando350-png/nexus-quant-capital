# Shadow Base/Morpho · 2026-10-25

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (5.5 h, 9,910 bloques): 4 decisiones, 1 GO, 0 liquidaciones reales; latencia visto+proceso p50 480 ms, p90 683 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 4 parcial, 2 sin datos.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 5.50 h, bloques 53076498–53086407 (9,910 de 9,910, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 219 ms | 386 ms | 504 ms |
| Proceso (leer + decidir) | 238 ms | 359 ms | 702 ms |
| Visto + proceso | 480 ms | 683 ms | 988 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 64 ms, logs 0 ms, lectura 126 ms, evaluar 6 ms.
Logs: 6,152 de 9,910 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: GO:ok 1, NO-GO:deuda_mala 3.
GO: 1 (bono $0, neto del modelo $0). Desenlace: expirada 1.
1 GO tienen el cruce incierto (ya eran liquidables al arrancar o se detectaron tras un hueco); no cuentan en la llegada.
No hubo liquidaciones en los mercados vigilados durante la ventana (el Census ya mostró que se concentran en pocos días).

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 56 ms, 197,270 fotos; trozos nuevos cada 198 ms (mediana).
- Perfil de los bloques (9,861 vistos desde el principio): mediana 145 transacciones por bloque en 11 trozos (≈ 12 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 24%, 33%, 41%, 50%, 60%, 67%, 75%, 83%, 90%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 150 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 64%, queda igual en 35% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 1331 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- WebSocket (wss://mainnet-preconf.base.org): suscripciones logs ok, transacciones ok; 1,582,143 transacciones y 351 logs recibidos; 1 conexiones; silencio entre trozos p50 166 ms.
- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): 112 actualizaciones; decidir tomó p50 1 ms (p90 3 ms) desde que llegó la actualización, sin consultar a la red; el WebSocket trajo la actualización 55 ms antes que la consulta del bloque pendiente (p50, n=112); 0 cruces vistos así, 0 liquidados.
- Prueba del clasificador «mismo trozo / trozo posterior» con 131 bloques de trozos conocidos: reconoce el comienzo de un trozo en 100% de 1178 fronteras, un pico dentro del trozo en 73% de 202 (el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en 99% de 3502.
- Evaluador del estado pendiente: 0 cruces vistos antes de sellarse el bloque (0 GO); decidimos — después de ver el trozo (p90 —); lectura del estado pendiente p50 77 ms. Desenlace: ninguno.
Candidatas que nadie liquidó: expirada 4.
Última foto de posiciones cerca del umbral: 4 dentro del 2%, deuda $4,963, la más cercana a 0.28% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 170574 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 4 decisiones; solo métodos de lectura (4 distintos) |
| Cada GO comparado con lo que ocurrió | 🟡 parcial | 1 de 1 GO con desenlace conocido (expirada 1); todos con cruce incierto (ya eran liquidables al arrancar): no miden una carrera |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (170574 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 480 ms, p90 683 ms, p99 988 ms (n=9832); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 9910, "decisiones": 4, "resultados": 4, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs.
