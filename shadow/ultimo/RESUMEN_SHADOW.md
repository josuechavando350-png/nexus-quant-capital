# Shadow Base/Morpho · 2026-11-03

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (5.5 h, 9,901 bloques): 5 decisiones, 0 GO, 2 liquidaciones reales; latencia visto+proceso p50 537 ms, p90 768 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 3 sin datos.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 5.50 h, bloques 53443417–53453317 (9,901 de 9,901, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 304 ms | 505 ms | 587 ms |
| Proceso (leer + decidir) | 218 ms | 344 ms | 3,361 ms |
| Visto + proceso | 537 ms | 768 ms | 3,666 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 71 ms, logs 0 ms, lectura 119 ms, evaluar 12 ms.
Logs: 6,894 de 9,901 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:deuda_mala 5.
Liquidaciones reales en la ventana: 2 (bono $1,726). Clases: mismo_bloque 2. Vía: subasta 2.

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 73 ms, 195,960 fotos; trozos nuevos cada 194 ms (mediana).
- Subastas medidas: 2: sin actualización localizada 2 ($1,726).
- Perfil de los bloques (6,693 vistos desde el principio): mediana 146 transacciones por bloque en 11 trozos (≈ 12 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 26%, 33%, 42%, 50%, 59%, 67%, 75%, 83%, 91%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 150 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 65%, queda igual en 33% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 1293 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- WebSocket (wss://mainnet-preconf.base.org): suscripciones logs ok, transacciones ok; 1,536,036 transacciones y 471 logs recibidos; 1 conexiones; silencio entre trozos p50 169 ms.
- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): 154 actualizaciones; decidir tomó p50 1 ms (p90 6 ms, máx 58 ms) desde que llegó la actualización, sin consultar a la red (evaluar el libro: p50 1.3 ms, máx 58.4 ms); el WebSocket trajo la actualización 45 ms antes que la consulta del bloque pendiente (p50, n=154); 2 cruces vistos así, 0 liquidados.
- **Rivales que perdieron** (2 liquidaciones con el bloque leído entero; rival = otra transacción con la dirección del prestatario en sus datos, de otro bot): hubo al menos uno en 2 (100% del bono); bots rivales por liquidación: mediana 13, p90 13, máx 13.
- Dónde quedó el segundo (el primer rival detrás del ganador) — detrás del ganador pagando más (llegó tarde: con esa propina, a tiempo habría ido primero): 2 (100% del bono).
- Propina del segundo frente a la del ganador: mediana 288.544× (p90 288.544×, n=2); llegó por WebSocket 0 ms después que el ganador (mediana, n=2).
- Bots que más aparecen (ganó / perdió): 0x583d…9b77 2/0; 0x5ac9…95bd 0/2; 0xe748…d339 0/2; 0xdd76…6cc6 0/2; 0x9158…4ffb 0/2; 0x27c5…0652 0/2.
- _Es un mínimo: un bot que esconde o comprime la dirección no aparece. El ganador la llevaba en sus datos en 2 de 2._
  - cbZEC/USDC lltv 62.5%, bono $1,674: 26 intentos rivales; el segundo quedó tarde con mas propina, 0 ms después por WebSocket, trozo 7 (0x2d56…01c1).
  - cbZEC/USDC lltv 62.5%, bono $53: 29 intentos rivales; el segundo quedó tarde con mas propina, 0 ms después por WebSocket, trozo 7 (0x2d56…01c1).
- Prueba del clasificador «mismo trozo / trozo posterior» con 66 bloques de trozos conocidos: reconoce el comienzo de un trozo en 99% de 592 fronteras, un pico dentro del trozo en 82% de 74 (el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en 97% de 1766.
- Evaluador del estado pendiente: 2 cruces vistos antes de sellarse el bloque (2 GO); decidimos 208 ms después de ver el trozo (p90 208 ms); lectura del estado pendiente p50 95 ms. Desenlace: liquidada 2.
- Holgura frente al ganador (nuestra transacción habría llegado 150 ms después de decidir): positiva en 0 de 2 (bono $0 de $1,726); mediana -358 ms; el ganador entró en el mismo trozo en que lo vimos en 2.
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 30 dentro del 2%, deuda $114.7 k, la más cercana a 0.14% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 170795 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 1, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 1 saltos de atraso (18 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (170795 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 537 ms, p90 768 ms, p99 3,666 ms (n=9774); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 9901, "decisiones": 5, "resultados": 7, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
