# Shadow Base/Morpho · 2026-11-04

> Solo lectura de la cadena. No se firmó ni se envió nada. Lo medido y lo supuesto van separados; los $ del replay son estimados para todo el período a partir de una muestra ponderada.

## Respuesta corta

- **Replay**: sin datos.
- **En vivo** (5.5 h, 9,890 bloques): 5 decisiones, 1 GO, 185 liquidaciones reales; latencia visto+proceso p50 529 ms, p90 778 ms.
- **Puertas del Omega (Shadow)**: 1 cumple, 3 parcial, 2 sin datos, 1 falla.

**Financiación requerida: gas de Titan y principal de préstamo flash; aportación propia cero.**
Capturas de entrada para simular la ruta propia: 5/5 decisiones. El neto del modelo usa retención histórica de terceros; el neto propio y el beneficio realizado siguen sin calcular.
Pendientes: liquidez y comisión del préstamo, salida del swap, repago atómico, cobertura de Titan en esta cadena y para esta candidata, gas y compensación del builder. Un dato faltante no equivale a coste cero.

## 1. Margen de tiempo (replay histórico)

Sin datos del replay.

## 2. En vivo

Ventana: 5.50 h, bloques 53476105–53486009 (9,890 de 9,905, cobertura 100%).
Umbral para decidir GO en esta corrida: bono ≥ $0.05 y neto del modelo ≥ $0.02 (el de operación sería $10 y $5).

| Latencia | p50 | p90 | p99 |
|---|---|---|---|
| Visto (desde el timestamp del bloque) | 237 ms | 422 ms | 557 ms |
| Proceso (leer + decidir) | 243 ms | 453 ms | 3,862 ms |
| Visto + proceso | 529 ms | 778 ms | 4,048 ms |

_visto_ms es cota superior: el timestamp del bloque tiene resolución de 1 s; se mide desde un servidor de GitHub Actions._
Dónde se va el tiempo (p50): cabecera 83 ms, logs 0 ms, lectura 62 ms, evaluar 9 ms.
Logs: 5,201 de 9,890 bloques sin pedir logs porque el bloom del bloque descarta a Morpho (bloom verificado con 12 bloques con eventos; falsos negativos: 0).

Decisiones: GO:ok 1, NO-GO:deuda_mala 4.
GO: 1 (bono $3, neto del modelo $2). Desenlace: expirada 1.
1 GO tienen el cruce incierto (ya eran liquidables al arrancar o se detectaron tras un hueco); no cuentan en la llegada.
Liquidaciones reales en la ventana: 185 (bono $34.1 k). Clases: fuera_del_libro 44, mismo_bloque 141. Vía: directa 139, subasta 46.
Avisadas antes de ocurrir, de las que se podían ver: 0%.
⚠️ Liquidaciones de posiciones que el libro no tenía: cbBTC/USDC lltv 86.0% $44, cbBTC/USDC lltv 86.0% $60, cbBTC/USDC lltv 86.0% $39, cbBTC/USDC lltv 86.0% $39, cbBTC/USDC lltv 86.0% $31, cbBTC/USDC lltv 86.0% $24, cbBTC/USDC lltv 86.0% $23, cbBTC/USDC lltv 86.0% $7, cbBTC/USDC lltv 86.0% $4, cbBTC/USDC lltv 86.0% $4.

Flashblocks (bloque pendiente de Base, trozos de ~200 ms):
- Seguimiento cada 100 ms, latencia p50 84 ms, 193,254 fotos; trozos nuevos cada 210 ms (mediana).
- Directas medidas: 139: en el mismo trozo que la actualización del oráculo 13 ($24), sin verse en el pendiente 60 ($121), sin actualización localizada 66 ($30.8 k); en 14 la actualización pasó por la subasta de oráculo (OEV). Reacción tras la actualización: mediana 0 ms, p90 0 ms.
- Subastas medidas: 46: sin verse en el pendiente 2 ($4), sin actualización localizada 44 ($3,177).
- Perfil de los bloques (8,327 vistos desde el principio): mediana 173 transacciones por bloque en 11 trozos (≈ 14 por trozo); parte del bloque acumulada al terminar cada trozo (mediana): 1%, 24%, 31%, 40%, 50%, 59%, 67%, 75%, 83%, 91%, 100%. El último trozo observado ya traía todo el bloque en 100% de los casos.
- Orden dentro del bloque comprobado en 150 bloques sellados con trozos conocidos: dentro de un trozo la propina baja en 65%, queda igual en 34% y sube en 1% de los pares consecutivos; al empezar un trozo nuevo sube en 100% de 1314 fronteras. Un orden por prioridad casi no tiene ascensos dentro del trozo.
- WebSocket (wss://mainnet-preconf.base.org): suscripciones logs ok, transacciones ok; 2,006,539 transacciones y 883 logs recibidos; 5 conexiones; errores {'WsError: conexión cerrada por el servidor': 3, 'WsError: el servidor cerró el WebSocket': 1}; silencio entre trozos p50 167 ms.
- Vía rápida (precio del oráculo calculado en casa al llegar su actualización): 288 actualizaciones; decidir tomó p50 1 ms (p90 5 ms, máx 40 ms) desde que llegó la actualización, sin consultar a la red (evaluar el libro: p50 1 ms, máx 39.5 ms); el WebSocket trajo la actualización 61 ms antes que la consulta del bloque pendiente (p50, n=279); 163 cruces vistos así, 0 liquidados.
- Ventana medida por WebSocket entre la actualización del oráculo y la liquidación del ganador: mediana 1 ms, mín 1 ms, máx 2 ms (n=14). Es el tiempo que hubo para ver, decidir y enviar.
- **Rivales que perdieron** (185 liquidaciones con el bloque leído entero; rival = otra transacción con la dirección del prestatario en sus datos, de otro bot): hubo al menos uno en 183 (100% del bono); bots rivales por liquidación: mediana 4, p90 8, máx 13.
- Dónde quedó el segundo (el primer rival detrás del ganador) — en el trozo del ganador, detrás, pagando lo mismo o menos (perdió por propina): 109 (90% del bono); en un trozo posterior (llegó tarde): 30 (2% del bono); detrás del ganador pagando más (llegó tarde: con esa propina, a tiempo habría ido primero): 34 (7% del bono); solo antes del ganador (disparó antes de tiempo y falló): 10 (0% del bono).
- Propina del segundo frente a la del ganador: mediana 0.332× (p90 2.227×, n=173); llegó por WebSocket 3 ms después que el ganador (mediana, n=173).
- De las que se ganaron reaccionando en un trozo posterior (las que se pueden competir): 11 de 11 tuvieron rivales; el segundo quedó mismo trozo menos propina 11.
- Bots que más aparecen (ganó / perdió): 0x2375…c519 2/97; 0xe94d…e419 10/84; 0x0f7f…736d 53/14; 0x583d…9b77 46/17; 0xa845…60c7 3/60; 0xc84b…fe52 0/59.
- _Es un mínimo: un bot que esconde o comprime la dirección no aparece. El ganador la llevaba en sus datos en 185 de 185; 95 listas recortadas a 40 intentos._
  - cbBTC/USDC lltv 86.0%, bono $7,171: 40 intentos rivales; el segundo quedó mismo trozo menos propina, 0 ms después por WebSocket, trozo 1 (0xb928…5ab7).
  - cbBTC/USDC lltv 86.0%, bono $4,683: 40 intentos rivales; el segundo quedó mismo trozo menos propina, 0 ms después por WebSocket, trozo 0 (0xc072…5885).
  - cbBTC/USDC lltv 86.0%, bono $3,402: 40 intentos rivales; el segundo quedó mismo trozo menos propina, 0 ms después por WebSocket, trozo 0 (0xc072…5885).
  - cbBTC/USDC lltv 86.0%, bono $3,028: 39 intentos rivales; el segundo quedó mismo trozo menos propina, 0 ms después por WebSocket, trozo 1 (0x0208…4a6a).
  - cbBTC/USDC lltv 86.0%, bono $2,979: 40 intentos rivales; el segundo quedó mismo trozo menos propina, 0 ms después por WebSocket, trozo 0 (0x3d89…36a5).
- Prueba del clasificador «mismo trozo / trozo posterior» con 117 bloques de trozos conocidos: reconoce el comienzo de un trozo en 100% de 1052 fronteras, un pico dentro del trozo en 78% de 262 (el resto lo toma por un trozo nuevo), y la cabeza de un trozo nuevo como trozo posterior en 99% de 3149.
- Evaluador del estado pendiente: 58 cruces vistos antes de sellarse el bloque (0 GO); decidimos 189 ms después de ver el trozo (p90 234 ms); lectura del estado pendiente p50 107 ms. Desenlace: liquidada 57, vencido 1.
- Holgura frente al ganador (nuestra transacción habría llegado 150 ms después de decidir): positiva en 8 de 56 (bono $6 de $2,564); mediana -279 ms; el ganador entró en el mismo trozo en que lo vimos en 32.
- 128 liquidaciones reales no se vieron cruzar antes en el estado pendiente (el precio y la liquidación llegaron en el mismo trozo).
Candidatas que nadie liquidó: expirada 5.
Última foto de posiciones cerca del umbral: 30 dentro del 2%, deuda $115.5 k, la más cercana a 0.10% de caída.

## 3. ¿La matemática coincide con la cadena?

Sin comparación de paridad en esta corrida.
Libro en vivo: 169239 posiciones comparadas con la cadena, deriva por eventos 0, en el crítico 0, por reconciliación 0; reorgs 0, saltos 1, bloques perdidos 0.

## 4. Puertas del Omega para la fase Shadow

| Puerta | Estado | Evidencia |
|---|---|---|
| Decisiones en tiempo real sin enviar nada | ✅ cumple | 5 decisiones; solo métodos de lectura (6 distintos) |
| Cada GO comparado con lo que ocurrió | 🟡 parcial | 1 de 1 GO con desenlace conocido (expirada 1); todos con cruce incierto (ya eran liquidables al arrancar): no miden una carrera |
| Control de reorganizaciones | 🟡 parcial | 0 reorgs vistos, 1 saltos de atraso (15 bloques cubiertos con eventos), 0 bloques perdidos (0 recuperados, 0 sin recuperar, 0 definitivos); la recuperación se prueba con una cadena falsa |
| Simulaciones: divergencias investigadas | ❌ falla | hay que investigar: fuera_del_libro 44 |
| Latencia en infraestructura real | 🟡 parcial | p50 529 ms, p90 778 ms, p99 4,048 ms (n=9674); medida desde GitHub Actions, no desde la infraestructura de Titan |
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
- Archivos leídos: {"vivo": {"bloques": 9890, "decisiones": 5, "resultados": 190, "lineas_cortadas": 0, "meta": true}}.
- Métodos RPC usados: eth_blockNumber, eth_call, eth_getBlockByNumber, eth_getLogs, eth_getTransactionByHash, eth_getTransactionReceipt.
