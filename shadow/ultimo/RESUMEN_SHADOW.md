# Shadow Base/Morpho · 2026-11-03

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (5.5 h, 9,910 bloques): 6 decisiones, 0 GO, 2 liquidaciones reales; latencia visto+proceso p50 390 ms, p90 625 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 3 sin datos.

**Financiación requerida: gas de Titan y principal de préstamo flash; aportación propia cero.**
Capturas de entrada para simular la ruta propia: 6/6 decisiones. El neto del modelo usa retención histórica de terceros; el neto propio y el beneficio realizado siguen sin calcular.
Pendientes: liquidez y comisión del préstamo, salida del swap, repago atómico, cobertura de Titan en esta cadena y para esta candidata, gas y compensación del builder. Un dato faltante no equivale a coste cero.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 5.50 h, bloques 53465379–53475288 (9,910 de 9,910, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 222 ms | 377 ms | 472 ms |
| Proceso (leer + decidir) | 163 ms | 345 ms | 850 ms |
| Visto + proceso | 390 ms | 625 ms | 1,128 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 25 ms, logs 19 ms, lectura 98 ms, evaluar 11 ms.
Logs: 4,819 de 9,910 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: NO-GO:deuda_mala 6.
Liquidaciones reales en la ventana: 2 (bono $2). Clases: con_aviso 1, mismo_bloque 1. Vía: directa 1, subasta 1.
Avisadas antes de ocurrir, de las que se podían ver: 100%.

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 22 ms, 196,438 fotos; trozos nuevos cada 194 ms (mediana).
- Directas medidas: 1: sin actualización localizada 1 ($0).
- Subastas medidas: 1: sin actualización localizada 1 ($2).
- Perfil de los bloques (8,193 vistos desde el principio): mediana 172 transacciones por bloque en 11 trozos (≈ 14 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 24%, 31%, 40%, 49%, 58%, 66%, 74%, 83%, 90%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 150 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 67%, queda igual en 32% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 1318 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- WebSocket (wss://mainnet-preconf.base.org): suscripciones logs ok, transacciones ok; 1,836,095 transacciones y 493 logs recibidos; 1 conexiones; silencio entre trozos p50 167 ms.
- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): 155 actualizaciones; decidir tomó p50 1 ms (p90 5 ms, máx 7 ms) desde que llegó la actualización, sin consultar a la red (evaluar el libro: p50 1.2 ms, máx 6.9 ms); el WebSocket trajo la actualización 56 ms antes que la consulta del bloque pendiente (p50, n=155); 1 cruces vistos así, 0 liquidados.
- **Rivales que perdieron** (2 liquidaciones con el bloque leído entero; rival = otra transacción con la dirección del prestatario en sus datos, de otro bot): hubo al menos uno en 1 (85% del bono); bots rivales por liquidación: mediana 3, p90 3, máx 3.
- Dónde quedó el segundo (el primer rival detrás del ganador) — en el trozo del ganador, detrás, pagando lo mismo o menos (perdió por propina): 1 (85% del bono).
- Propina del segundo frente a la del ganador: mediana 0.039× (p90 0.039×, n=1); llegó por WebSocket 0 ms después que el ganador (mediana, n=1).
- _Es un mínimo: un bot que esconde o comprime la dirección no aparece. El ganador la llevaba en sus datos en 2 de 2._
  - WETH/USDC lltv 86.0%, bono $2: 5 intentos rivales; el segundo quedó mismo trozo menos propina, 0 ms después por WebSocket, trozo 1 (0xd186…ea83).
  - wbCOIN/USDC lltv 86.0%, bono $0: 0 intentos rivales (0x5874…c6e1).
- Prueba del clasificador «mismo trozo / trozo posterior» con 110 bloques de trozos conocidos: reconoce el comienzo de un trozo en 100% de 989 fronteras, un pico dentro del trozo en 82% de 182 (el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en 99% de 2965.
- Evaluador del estado pendiente: 1 cruces vistos antes de sellarse el bloque (1 GO); decidimos 107 ms después de ver el trozo (p90 107 ms); lectura del estado pendiente p50 46 ms. Desenlace: liquidada 1.
- Holgura frente al ganador (nuestra transacción habría llegado 150 ms después de decidir): positiva en 0 de 1 (bono $0 de $2); mediana -257 ms; el ganador entró en el mismo trozo en que lo vimos en 1.
- 1 liquidaciones reales no se vieron cruzar antes en el estado pendiente (el precio y la liquidación llegaron en el mismo trozo).

Directas que descartamos y alguien liquidó:

| Mercado | Razón del NO-GO | Bono | Bloques |
|---|---|---|---|
| wbCOIN/USDC lltv 86.0% | deuda_mala | $0 | 666 |
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 3 dentro del 2%, deuda $4,911, la más cercana a 0.12% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 169160 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 0, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 6 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | ⚪ sin datos | ningún GO en la ventana en vivo |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 0 saltos de atraso (0 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | 🟡 parcial | libro sin deriva (169160 posiciones reconciliadas) |
| Latencia en infraestructura real | 🟡 parcial | p50 390 ms, p90 625 ms, p99 1,128 ms (n=9810); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 9910, "decisiones": 6, "resultados": 7, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
