# Shadow Base/Morpho

Fase 1 del Omega (cap. 5): **¿llegaríamos a tiempo y con margen?** Criterio de salida:
decisiones simuladas en tiempo real sin enviar nada, cada GO comparado con lo que
realmente ocurrió, latencia medida en infraestructura real.

Alcance: Morpho Blue en Base, los 19 mercados USDC que el Census encontró con
liquidaciones directas (`config.SHADOW_BASE_MARKETS`). Es el único hueco que dejó el Census:
Base/Morpho fuera de subasta.

## Reglas

- **Solo lectura.** No firma, no envía, no usa fondos, no usa llaves ni secretos nuevos. El
  cliente RPC solo deja pasar `rpc.ALLOWED_METHODS`, y una prueba revisa que ningún módulo del
  Shadow nombre métodos de envío o firma.
- El proceso que lee la cadena **no recibe el token** de GitHub; solo lo tiene el paso que sube
  resultados a la rama `census-dinero/resultados`.
- Mismo workflow que el Census (`census-dinero.yml`), con un modo más (`"modo": "shadow"`). No se
  agregó ningún workflow ni permiso nuevo.
- Nada de esto certifica una captura. Mide el margen de tiempo y de bono que hubo.

## Cómo se corre

Se empuja un `run.json` con `modo: shadow` a la rama `feat/census-dinero-20261024`:

```json
{
  "modo": "shadow",
  "shadow": {
    "minutos": 60,
    "vivo": true,
    "replay": {"dias": 30, "max": 300, "top": 100, "presupuesto_min": 40},
    "config": {"min_bonus_usd": 10, "min_net_usd": 5}
  }
}
```

Tres trabajos (los dos primeros en paralelo):

| Trabajo | Qué hace | Sale en |
|---|---|---|
| `shadow` | Vigila Base bloque a bloque durante `minutos` (máx. 330). Arma el libro de posiciones, simula decisiones y las compara con lo que pasa. Sube lo que lleva cada 10 min. | `corridas/<run>/shadow-vivo/` |
| `replay` | Reconstruye liquidaciones de los últimos `dias` días con lecturas de archivo: cuándo se volvió liquidable cada posición y cuántos bloques después la liquidaron. | `corridas/<run>/shadow-replay/` |
| `shadow_report` | Junta ambos y escribe `RESUMEN_SHADOW.md` y `shadow.json`. | `corridas/<run>/shadow-reporte-<run>/` y `shadow/ultimo/` |

`{"modo": "shadow_reporte", "corrida": <run_id>}` rehace solo el reporte de una corrida anterior.
El vivo, el replay y la lupa del oráculo pueden venir de corridas distintas (el vivo largo de una,
el replay de otra): `"corrida"` es la del vivo; `"corrida_replay"` y `"corrida_lupa"` (opcionales, por
omisión la misma) son las del replay y de la carpeta con `diag.jsonl`. El reporte deja en
`fuentes.txt` de qué corrida salió cada parte. Los ids son números (acaban en una ruta del workflow).
El libro de prestatarios queda guardado en `shadow/cache/libro.json` para que la siguiente
corrida arranque en minutos en vez de releer 30 días de eventos.

Un cambio solo de código no dispara nada; solo `run.json` o el workflow. Una corrida nueva
cancela la que esté en curso (como en el Census).

## Cómo decide (en vivo)

En cada bloque nuevo, con el mismo bloque como instantánea:

1. Aplica los eventos de Morpho (`Borrow`, `Repay`, `SupplyCollateral`, `WithdrawCollateral`,
   `Liquidate`) al libro.
2. Lee con Multicall3 el mercado y el precio del oráculo de cada mercado vigilado, y la posición
   directa de las que acaban de cambiar. Hay prueba de arranque del multicall y vuelta a llamadas
   sueltas si el proveedor no lo sirve.
3. Calcula la salud con la matemática entera de Morpho (`morpho.py`, portada de `Morpho.sol`,
   `SharesMathLib`, `MathLib`): `isHealthy`, LIF, embargo, repago, deuda mala, interés acumulado
   (Taylor de 3 términos, solo cerca del umbral).
4. Las que acaban de volverse liquidables ("cruce") reciben una decisión:

| Decisión | Razón |
|---|---|
| NO-GO | `deuda_mala` (el colateral no cubre), `bono_bajo` (< mínimo), `mercado_de_subasta` (en el Census ≥ 90% del bono fue por subasta y casi nada directo), `neto_bajo` (bono × retención del Census < mínimo), `discrepancia_libro` (el libro no coincide con la lectura directa), `sin_lectura_directa`, `datos_viejos` (el bloque llegó con más de 30 s) |
| OBSERVAR | `oraculo_anomalo` (el precio saltó más de 30% entre bloques) |
| GO | pasó todo lo anterior |

Para no pedir logs de todos los bloques, mira el `logsBloom` de la cabecera: si el bloom no contiene la
dirección de Morpho, algún evento nuestro ni algún mercado vigilado, no hay nada que leer (un "no" del bloom
es seguro). Solo se usa si al arrancar se comprobó con bloques reales con eventos (al menos 3) que el bloom
no los descarta, y 1 de cada 40 bloques "vacíos" se consulta de todos modos; si alguna vez aparece un
evento donde el bloom decía que no, se apaga y se piden los logs de todos los bloques. Implementación
comprobada contra la librería de referencia `eth-bloom` (3000 valores y 300 blooms al azar, sin diferencias).

Si el Shadow se atrasa más de 15 bloques (o termina de armar el libro y la cadena ya avanzó), se pone al
día con **una sola búsqueda de los eventos del hueco** y sigue; no vuelve a leer las decenas de miles de
posiciones del libro. Lo que se pierde es la hora exacta de los cruces dentro del hueco, así que las
candidatas que ya eran liquidables al arrancar o que aparecen en el primer bloque tras un hueco se marcan
con `cruce_incierto` y no cuentan en las tablas de llegada. Un bloque que no se pudo procesar se da por
perdido, se sigue, y se intenta recuperar sus eventos más tarde (`bloques_recuperados`).

El **crítico** es independiente del libro: lee la posición directamente en la cadena en ese bloque,
y si no coincide con el libro, es NO-GO (regla del Omega: discrepancia = NO-GO).

Cuando alguien liquida de verdad, el resultado se junta con la decisión: bloques desde el cruce,
quién (`liquidador` y firmante), vía (`directa` o `subasta`, por el contrato de entrada), gas y
propina pagados. Las candidatas que no se liquidan se cierran como `recuperada` (con causa),
`expirada`, `invalidada_por_reorg`, `perdida_por_salto` o `abierta_al_cierre`.

## Modelo de tiempos

- **Cruce `b_c`**: primer bloque cuyo estado final deja la posición liquidable.
- **Tiempo total `X`** = *visto* (hora a la que lo vimos − timestamp del bloque) + *decidido* (lo
  que tardamos en leer y decidir) + *envío* (supuesto: 150 ms; no se mide, no se envía nada).
- **Primer bloque propio** `b_c + k`, con `k = max(1, ceil(X / 2 s))`. Con `X ≤ 2 s`, `k = 1`.
- Contra el bloque `b_L` en que alguien liquidó: **antes** si `b_L > b_c + k`, **empate** si es el
  mismo, **tarde** si es anterior. `b_L = b_c` (mismo bloque) no se puede ganar sin ver antes de
  que el bloque cierre.

## Dentro del bloque: Flashblocks

El replay y una lupa bloque a bloque sobre 14 liquidaciones directas mostraron que **la posición no era
liquidable al cierre del bloque anterior**: el precio del oráculo cambió *dentro del mismo bloque* de la
liquidación, unas pocas transacciones antes. La carrera es **dentro de los 2 s del bloque**, en los trozos
de ~200 ms (Flashblocks) que Base publica antes de sellarlo. En 6 de las 14 la actualización pasaba por el
contrato de subasta de oráculo (OEV) y la liquidación iba justo detrás: subasta disfrazada de directa.

Por eso hay un observador (`flash_watch.py`) que pregunta por el bloque `pending` de un RPC con
preconfirmaciones (`https://mainnet-preconf.base.org`, público; desde Actions: 16 a 80 ms de latencia según el
servidor que toque, 0 errores, trozos nuevos cada ~197 ms) y anota la hora y el número de trozo en que entró cada
transacción. Al sellarse el
bloque, cada liquidación real queda medida contra la transacción que actualizó el feed del oráculo: ¿en el mismo
trozo (empaquetada, nadie la gana), en el siguiente (hay que reaccionar en <200 ms) o 2+ trozos después?
Se activa con `config: {"flash_url": "https://mainnet-preconf.base.org", "flash_interval": 0.1}`.

Además hay un **evaluador del estado pendiente** (`flash_eval.py`, activo con `flash_url`; se apaga con `flash_eval: false`):
cada trozo nuevo dispara una lectura de mercados y precios en el estado pendiente (`eth_call` con la etiqueta
`pending`), se evalúa el libro y, si una posición acaba de volverse liquidable, anota en `flash_cruces.jsonl` cuándo
la vimos (trozo y ms desde que empezó el bloque), cuánto tardamos en decidir y qué habríamos decidido (mismo filtro
económico que el modo sellado). Al sellarse el bloque, se mide la **holgura**:
`(hora en que apareció la liquidación del ganador − hora en que vimos el cruce) − lo que tardamos en decidir − tiempo
de envío supuesto`. Positiva = nuestra transacción habría llegado a tiempo, sin contar el orden por propina dentro del
trozo. Las liquidaciones cuyo cruce no vimos antes (la actualización y la liquidación llegaron en el mismo trozo, o
decidimos más tarde que el ganador) quedan contadas aparte.

Es la medida correcta de "llegar a tiempo", pero sigue siendo la visión de un servidor de GitHub Actions: no
mide el envío ni el orden de prioridad (propina) dentro del trozo.

Lo que dice la documentación de Base (docs.base.org, «Transaction ordering» y «Flashblocks») coincide con lo medido: cada bloque trae 10 trozos de
200 ms (más el índice 0 con las transacciones del sistema), cada trozo se arma como subasta de propina de mayor a menor y el presupuesto de gas
es acumulado (el trozo *j* puede llegar a *j*/10 del límite del bloque). Además, el constructor sigue aceptando transacciones mientras arma el trozo:
una con propina alta que llega tarde puede quedar detrás de otra ya confirmada con menos. Dónde está físicamente el secuenciador no es público;
no se supone nada de eso aquí.

**Quién gana dentro del bloque.** Con las propinas de la actualización, de la liquidación y de sus vecinas (`propinas` en `diag.jsonl` y en
`resultados.jsonl`) el reporte clasifica cada liquidación: *empaquetada* (misma propina que la actualización y pegada a ella: subasta OEV),
*mismo trozo* (la propina sube justo en la liquidación y vuelve al nivel de antes: un pico que entró tarde al trozo de la actualización, es decir,
alguien que la vio antes de que se confirmara), *trozo siguiente* (cabeza ordenada de otro trozo, o paga más que la actualización sin ser un
pico: reaccionó al trozo ya publicado) y *ambigua*. Es una inferencia a partir del orden por propina; en vivo se contrasta con los trozos medidos
(`clases_en_vivo`). Distinguir «mismo trozo» de «trozo siguiente» importa: lo primero exige ver la transacción de la actualización antes de que
entre al bloque, lo segundo solo velocidad sobre el flujo de Flashblocks.

**Vía rápida** (`config: {"flash_ws": "wss://mainnet-preconf.base.org"}`). Lo que haría un sistema que quiere ganar el trozo siguiente:
en vez de preguntar cada 100 ms, se suscribe por WebSocket (`ws.py`, `flash_stream.py`) a `newFlashblockTransactions` (cada transacción
preconfirmada, con su hora de llegada) y a `pendingLogs` de los feeds del oráculo. Cuando llega un `AnswerUpdated`, `flash_fast.py` calcula el
precio nuevo del oráculo en casa (último precio × respuesta nueva / respuesta anterior del feed; al revés si es el feed de cotización),
evalúa el libro en memoria sin consultar a la red y anota cuánto tardó en decidir. Al sellarse el bloque mide, para cada liquidación real, la
**ventana** entre la llegada de la actualización y la de la liquidación del ganador (ambas por WebSocket) y la holgura con un envío supuesto de
`submit_rapido_ms` (20 ms: un servidor cerca del secuenciador; no se mide ni se envía nada). También mide cuánto antes llega la actualización
por WebSocket que por la consulta. En la vía rápida no hay ninguna consulta a la red: cerca del umbral el interés se estima con la última tasa del IRM leída para ese mercado, aunque haya caducado (en la v9 una actualización tardó 33 ms en decidirse, casi seguro por esa lectura). Archivos: `flash_rapido.jsonl`, `flash_actualizaciones.jsonl` (una línea por actualización: ms para decidir, ms de evaluación, mercados y cuánto antes llegó) y `via_rapida` / `flash_ws` en `meta.json`. El cliente WebSocket solo
acepta `eth_subscribe` y `eth_unsubscribe`.

**Rivales que perdieron** (`orden.intentos`; en la lupa del replay y en cada liquidación en vivo). Ganar o perder se decide contra
los demás bots, no contra un reloj. En el bloque de cada liquidación se buscan las otras transacciones que llevan la dirección del prestatario
en sus datos (la llamada a `liquidate` de Morpho la lleva, directa o dentro del contrato de un bot), sin las del propio prestatario, la de la
actualización y las que también liquidaron esa posición. Cada intento queda en un lugar: *antes de la actualización* (disparó sin el precio
nuevo), *antes del ganador*, *mismo trozo con menos propina* (detrás del ganador en su trozo, pagando lo mismo o menos: perdió por propina, o
entró a medio armar el trozo), *trozo posterior* (llegó tarde) o *tarde con más propina* (detrás pagando más: con esa propina, a tiempo, habría
ido primero). Los trozos se reconocen con la misma regla de propinas de `clasificar`; en vivo además se anota el trozo en que se vio cada
intento y cuántos ms después del ganador llegó por WebSocket. El reporte cuenta en qué parte del bono hubo rivales, cuántos, dónde quedó el
segundo (el primer rival detrás del ganador), su propina frente a la del ganador, y qué bots ganan y pierden más. Es un mínimo: un bot que
esconde o comprime la dirección no aparece (el reporte dice en cuántas el ganador la llevaba visible).

**Conexiones persistentes.** Todos los clientes RPC del Shadow reutilizan la conexión (`rpc.KeepAlive`, HTTP/1.1
keep-alive por hilo). Antes cada consulta abría TCP y TLS de nuevo (~3 viajes de ida y vuelta) y la latencia medida
salía ~3 veces peor que la de un sistema real. Con conexiones persistentes, desde Actions: ver un trozo nuevo del
bloque pendiente ~16 ms, leer el estado pendiente ~35 ms, procesar un bloque sellado ~365 ms (mediana).

## Replay (túnel de viento mínimo)

Para una muestra de liquidaciones de los últimos días (las 100 de mayor bono más una muestra pareja
del resto, con peso para estimar el total), con `eth_call` en bloques pasados:

- busca el cruce (búsqueda exponencial y binaria; si llega al borde de la ventana de 1800 bloques,
  queda **censurada**: se sabe que fue al menos eso);
- compara la matemática: con el estado anterior, el precio y el interés, ¿el contrato habría dado
  el embargo y el repago que dice el evento? (solo la primera liquidación de cada mercado en un
  bloque, porque las siguientes ya parten de otro estado);
- reconstruye gas, propina y vía del ganador, y dónde cayó dentro del bloque (`bloque_n_tx`, `prioridad_wei`);
- si una posición ya había sido liquidada antes y seguía liquidable (liquidación parcial), la carrera por el
  residuo se mide desde esa liquidación;
- mide la **cobertura del libro**: busca los `Borrow` de los `libro_dias` (90) días antes de la ventana y
  cuenta qué parte de los prestatarios liquidados un libro armado mirando 7, 30, 60 o 90 días atrás ya habría
  conocido. Es el límite del `recall` del modo en vivo. La búsqueda tiene su propio tiempo (`libro_min`, 20 min).

Con `diag: N` mira bloque a bloque las N liquidaciones directas más grandes (repartidas entre mercados): si ya
eran liquidables un bloque antes, qué feed del oráculo cambió, **quién actualizó el oráculo** (¿la subasta OEV
o un transmisor normal?) y cuántas transacciones separan esa actualización de la liquidación dentro del mismo
bloque (`diag.jsonl`). El reporte la resume como «Separación»: transacciones, parte del bloque y, si las
transacciones se reparten parejo en los 2 s, un tiempo aproximado; y si la liquidación pagó más, igual o menos
prioridad que la actualización. Los milisegundos son una aproximación; el sello exacto solo sale en vivo (200 ms).

**Comprobación del orden por prioridad.** La lectura de «reaccionó / iba empaquetado» supone que, dentro de un trozo de 200 ms, el
secuenciador pone primero a quien paga más propina. Se comprueba con bloques reales: `orden_cada` (vivo) y `orden` (replay) guardan la
propina de cada transacción. En vivo se juntan con el perfil de trozos (`flash_bloques.jsonl`) y el reporte da, dentro de un trozo, qué parte
de los pares consecutivos baja, iguala o sube su propina, y cuántas veces sube al empezar un trozo nuevo. En bloques históricos cuenta los
ascensos de propina por bloque. Si el supuesto fallara, esa lectura no se sostiene y hay que decirlo.

Solo ve posiciones que **terminaron liquidadas**. Las que se recuperaron las mide el modo en vivo.

## Archivos

`shadow-vivo/`: `bloques.jsonl` (latencia, fases y transacciones de cada bloque), `decisiones.jsonl`,
`resultados.jsonl` (con `flash` y `flash_cruce` si se sigue el bloque pendiente), `flash_cruces.jsonl`,
`flash_bloques.jsonl` (cómo se llenó cada bloque sellado: milisegundos y transacciones acumuladas por trozo; sirve para
repartir en trozos un bloque histórico), `cercanas.jsonl` (foto cada 5 min de las posiciones a menos de 2% del
umbral), `eventos_del_sistema.jsonl` (reorgs, saltos, bloques perdidos, deriva del libro),
`meta.json`, `log.txt`. Con `orden_cada: N`, además `orden_bloques.jsonl`: la propina de cada transacción de 1 de cada N bloques sellados.
`shadow-replay/`: `replay.jsonl`, `replay_errores.jsonl`, `replay_meta.json`, `log.txt`, y con `diag` los `diag.jsonl` y `diag_oraculos.json`
(con `orden: M`, `orden_bloques.jsonl` con la propina de cada transacción de los M bloques más llenos mirados con lupa).
Los `.jsonl` se escriben línea a línea: una cancelación no deja nada a medias y el reporte
ignora una última línea cortada.

## Lo medido en la primera tanda (25 oct 2026; parcial)

Replay de 30 días (corrida `40190198885`: **todas** las liquidaciones con bono ≥ $10, sin muestreo) y vivo (`40163135976`, 2.2 h; `40171040689`, 1.4 h;
`40176606411`, 3.3 h; `40190198885`, en curso):

- **Matemática**: 250 de 256 liquidaciones coinciden exactamente con la matemática de Morpho (las 6 restantes con error relativo ≤ 7e-13).
  En vivo (v7, 3.3 h), deriva 0 en más de 97,000 posiciones comparadas, sin huecos de bloques y 0 errores en ~55,000 evaluaciones del estado pendiente.
- **Dónde está la carrera**: 2,648 liquidaciones en los 19 mercados (1,213 con bono ≥ $10). El 99% del bono directo (≈ $102k en 30 días,
  entre todos los bots; 96% en 3 días) se liquidó en el mismo bloque del cruce. En la lupa de las 454 directas el precio de Morpho cambió en
  el mismo bloque de la liquidación casi siempre. Desde bloques sellados no se gana.
- **El orden dentro del bloque es por propina** (comprobado). En 12 bloques históricos llenos (2.7 a 3.6 mil transacciones) la propina sube de una
  transacción a la siguiente 26 a 143 veces por bloque; con las mismas propinas en orden de llegada al azar subiría 1.1 a 1.5 mil veces. En vivo,
  con los trozos conocidos de bloques sellados: dentro de un trozo la propina sube en 1.4% de los pares, y al empezar un trozo nuevo sube en el 99.8% de las
  fronteras (484 de 485). Cada trozo de 200 ms se ordena de más a menos propina.
- **Quién gana dentro del bloque** (435 con la actualización del oráculo localizada, clasificadas por las propinas de la actualización, de la
  liquidación y de sus vecinas): 64% del bono (≈ $61k) lo ganó quien reaccionó en un trozo posterior al de la actualización (se puede competir
  con velocidad y propina); 25% (≈ $24k) iba empaquetado con la actualización (misma propina, subasta OEV: no hay carrera); 9% ambiguo;
  2% (≈ $2k, 24 casos) se coló en el mismo trozo justo después de la actualización (vio la actualización antes de confirmarse: hace falta otra
  clase de infraestructura). De los que reaccionan, el 87% del bono cae en el trozo siguiente (la ventana es de ~200 ms), 8% uno o dos trozos más
  tarde y 5% mucho más tarde. Un solo contrato liquidador se lleva ~31% del bono, casi todo lo empaquetado.
  La regla de clasificación se probó con 166 bloques en vivo cuyos trozos se conocen: reconoce el comienzo de un trozo en el 99.7% de las fronteras
  (1,489 de 1,493) y la cabeza de un trozo nuevo como trozo posterior en el 98%; un pico dentro del trozo lo reconoce en el 79% (el resto lo toma por
  un trozo nuevo). Si acaso, «mismo trozo» está algo subestimado: corrigiendo por eso rondaría el 3% del bono, no el 2%.
- **Propinas de los ganadores** (directas): mediana 2.4% del bono entre $10 y $1,000 (p90 16%), 0.2% por encima de $1,000 (p90 7%); en los eventos
  grandes de cbETH pagaron $780 y $850 (7% y 17%). Ganar el orden dentro de un trozo cuesta propina, no solo velocidad.
- **En vivo, dos casos reales**: (1) AERO/USDC, bono $0.13: el ganador cayó un trozo (≈ 200 ms) después de la actualización del oráculo; nuestra
  decisión desde Actions tardó 112 ms y con 150 ms de envío supuesto habríamos llegado 61 ms tarde. (2) AERO/USDC, bono $31: el ganador cayó una
  transacción después de la actualización, en su mismo trozo, pagando 4.6 gwei (el tipo raro de arriba). Son dos casos de bono chico.
- **Piso económico**: con el umbral de GO en $0.05 (v6), dos posiciones de ≈ $0.5 y $0.15 de bono, liquidables desde antes de arrancar la v5 y
  todavía en la v6 (más de 2 h), nadie las liquidó: el piso del mercado está por encima de ~$0.5 de bono.

No es una certificación: la latencia es la de un servidor de Actions, no se midió el envío ni la inclusión, y la muestra en vivo es pequeña.

## Qué cubre del Omega y qué no

| Componente de la fase Shadow | Estado |
|---|---|
| 9 Posiciones protegidas | No |
| 11 Third Eye (precio exacto de liquidación) | Parcial: salud y caída de precio de las posiciones cercanas al umbral |
| 12 Oráculo sombra | No |
| 13 Kalman | No |
| 16 Calendario | No |
| 17 Economic Intelligence | Parcial: bono completo con la fórmula del contrato × retención del Census; sin ruta ni liquidez |
| 18 Capital cero | No |
| 21 Adversarial Critic | Parcial: lectura directa independiente, sanidad del oráculo y edad del dato |
| 30 Túnel de viento | Versión mínima: cruce → liquidación, no repite NQC completo |

| Puerta (cap. 6) | Qué aporta |
|---|---|
| Control de reorganizaciones | Detección por `parentHash`, relectura del libro, salto por atraso. Probado con una cadena falsa; en vivo depende de que ocurra un reorg |
| Simulaciones | Paridad de la matemática contra la cadena y deriva del libro (eventos vs. lectura directa) |
| Latencia | Percentiles medidos **desde GitHub Actions**, no desde la infraestructura de Titan |
| Detección competitiva | Replay del cruce a la liquidación (versión mínima) |
| Economía | Neto del modelo con retención observada, no con costos propios |

## Qué NO prueba

- La latencia es la de un servidor de Actions hacia RPC públicos: una referencia conservadora, no una
  certificación. `visto` es cota superior (el timestamp del bloque es entero).
- No se midió el envío ni la inclusión; el orden dentro del bloque y los empates los decide el
  secuenciador.
- La carrera es dentro del bloque: en el replay el 99% del bono directo se liquidó en el mismo bloque en que cambió el
  precio del oráculo, así que desde bloques sellados no se gana. Solo cabe pelear viendo el bloque pendiente (Flashblocks)
  y con una transacción que llegue al secuenciador antes de que se arme el trozo siguiente (~200 ms). Aquí eso se mide desde
  Actions (decisión ~110 ms + envío supuesto de 150 ms); no es una infraestructura propia ni mide el envío real.
- El neto usa la retención de los ganadores del Census (incluye swap, gas y propinas de ellos); no se
  simuló nuestra ruta, flash loan ni slippage.
- Una ventana corta no sustituye semanas de Shadow ni cubre los picos: en el Census el 95% del margen
  cayó en 3 de 30 días.

## Local, sin red

```
cd migration/census-dinero
python3 -m unittest discover -s tests
python3 check_isolation.py
```

Las pruebas usan una Base falsa con la matemática exacta de Morpho (`tests/fakemorpho.py`) que
también implementa Multicall3, reorgs, fallos de RPC y archivo limitado.
