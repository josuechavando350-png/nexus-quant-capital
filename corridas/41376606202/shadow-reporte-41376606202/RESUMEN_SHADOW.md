# Shadow Base/Morpho · 2026-11-02

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (5.5 h, 9,902 bloques): 5 decisiones, 0 GO, 1 liquidaciones reales; latencia visto+proceso p50 399 ms, p90 601 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 3 sin datos.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 5.50 h, bloques 53398202–53408103 (9,902 de 9,902, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 217 ms | 369 ms | 486 ms |
| Proceso (leer + decidir) | 161 ms | 285 ms | 592 ms |
| Visto + proceso | 399 ms | 601 ms | 883 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 22 ms, logs 0 ms, lectura 117 ms, evaluar 8 ms.
Logs: 6,930 de 9,902 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:deuda_mala 5.
Liquidaciones reales en la ventana: 1 (bono $165). Clases: mismo_bloque 1. Vía: subasta 1.

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 17 ms, 189,207 fotos; trozos nuevos cada 196 ms (mediana).
- Subastas medidas: 1: sin actualización localizada 1 ($165).
- Perfil de los bloques (9,887 vistos desde el principio): mediana 137 transacciones por bloque en 11 trozos (≈ 11 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 3%, 11%, 24%, 44%, 57%, 67%, 76%, 85%, 92%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 150 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 59%, queda igual en 38% y sube en 3% de los pares consecutivos; al empezar un trozo nuevo sube en 85% de 1230 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- WebSocket (wss://mainnet-preconf.base.org): suscripciones logs ok, transacciones ok; 1,487,690 transacciones y 416 logs recibidos; 2 conexiones; errores {'WsError: conexión cerrada por el servidor': 1}; silencio entre trozos p50 171 ms.
- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): 131 actualizaciones; decidir tomó p50 1 ms (p90 4 ms, máx 4 ms) desde que llegó la actualización, sin consultar a la red (evaluar el libro: p50 0.9 ms, máx 4.1 ms); el WebSocket trajo la actualización 47 ms antes que la consulta del bloque pendiente (p50, n=131); 1 cruces vistos así, 0 liquidados.
- **Rivales que perdieron** (1 liquidaciones con el bloque leído entero; rival = otra transacción con la dirección del prestatario en sus datos, de otro bot): hubo al menos uno en 1 (100% del bono); bots rivales por liquidación: mediana 5, p90 5, máx 5.
- Dónde quedó el segundo (el primer rival detrás del ganador) — detrás del ganador pagando más (llegó tarde: con esa propina, a tiempo habría ido primero): 1 (100% del bono).
- Propina del segundo frente a la del ganador: mediana 391.786× (p90 391.786×, n=1); llegó por WebSocket 0 ms después que el ganador (mediana, n=1).
- _Es un mínimo: un bot que esconde o comprime la dirección no aparece. El ganador la llevaba en sus datos en 1 de 1._
  - cbHYPE/USDC lltv 62.5%, bono $165: 9 intentos rivales; el segundo quedó tarde con mas propina, 0 ms después por WebSocket, trozo 8 (0x76da…f277).
- Prueba del clasificador «mismo trozo / trozo posterior» con 54 bloques de trozos conocidos: reconoce el comienzo de un trozo en 89% de 409 fronteras, un pico dentro del trozo en 52% de 184 (el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en 74% de 1355.
- Evaluador del estado pendiente: 1 cruces vistos antes de sellarse el bloque (0 GO); decidimos 44 ms después de ver el trozo (p90 44 ms); lectura del estado pendiente p50 40 ms. Desenlace: liquidada 1.
- Holgura frente al ganador (nuestra transacción habría llegado 150 ms después de decidir): positiva en 0 de 1 (bono $0 de $165); mediana -194 ms; el ganador entró en el mismo trozo en que lo vimos en 1.
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 5 dentro del 2%, deuda $8,518, la más cercana a 0.10% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 171233 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 1, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 1 saltos de atraso (33 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (171233 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 399 ms, p90 601 ms, p99 883 ms (n=9896); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 9902, "decisiones": 5, "resultados": 6, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
