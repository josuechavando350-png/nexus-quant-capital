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
preconfirmaciones (`https://mainnet-preconf.base.org`, público; desde Actions: 26 ms de latencia, 0 errores,
trozos nuevos cada 198 ms) y anota la hora y el número de trozo en que entró cada transacción. Al sellarse el
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
- reconstruye gas, propina y vía del ganador;
- si una posición ya había sido liquidada antes y seguía liquidable (liquidación parcial), la carrera por el
  residuo se mide desde esa liquidación;
- mide la **cobertura del libro**: busca los `Borrow` de los `libro_dias` (90) días antes de la ventana y
  cuenta qué parte de los prestatarios liquidados un libro armado mirando 7, 30, 60 o 90 días atrás ya habría
  conocido. Es el límite del `recall` del modo en vivo. La búsqueda tiene su propio tiempo (`libro_min`, 20 min).

Solo ve posiciones que **terminaron liquidadas**. Las que se recuperaron las mide el modo en vivo.

## Archivos

`shadow-vivo/`: `bloques.jsonl` (latencia y fases por bloque), `decisiones.jsonl`,
`resultados.jsonl` (con `flash` y `flash_cruce` si se sigue el bloque pendiente), `flash_cruces.jsonl`, `cercanas.jsonl` (foto cada 5 min de las posiciones a menos de 2% del
umbral), `eventos_del_sistema.jsonl` (reorgs, saltos, bloques perdidos, deriva del libro),
`meta.json`, `log.txt`.
`shadow-replay/`: `replay.jsonl`, `replay_errores.jsonl`, `replay_meta.json`, `log.txt`.
Los `.jsonl` se escriben línea a línea: una cancelación no deja nada a medias y el reporte
ignora una última línea cortada.

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
- Con Flashblocks algunos bots ven antes de que el bloque cierre; el mismo bloque del cruce no se gana desde RPC públicos.
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
