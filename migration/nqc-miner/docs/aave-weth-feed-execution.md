# Proxy observado de la fuente WETH

La composición de liquidación ejecuta el `EACAggregatorProxy` observado en
`0x5424384b256154046e9667ddfaaa5e550145215e`. Sustituye el doble de esa dirección,
conservando el AaveOracle real y las dos rutas de pago ya verificadas. Su agregado
de precios y la fuente USDC siguen siendo dobles explícitos; el estado restante
es artificial. No acredita una liquidación histórica, frescura ni rentabilidad.

## Identidad y lectura acotada

Las siete fuentes publicadas en Sourcify se recompilan sin cambios con Solidity
0.6.6, optimizer 1000000 y objetivo Istanbul. Los 9571 bytes completos, incluida
metadata, coinciden con el bytecode publicado y con dos proveedores en los tres
bloques retenidos: 26248075, 26248113 y 26248378. No se retira metadata ni se
modifican bytes del runtime. Esta equivalencia no es una prueba canónica de estado.

`research/capture_aave_weth_feed.py` permite solo consultas de cadena, cabecera,
código, dos slots y cuatro getters. Código/storage/llamadas usan pins EIP-1898
con hash y `requireCanonical=true`; se verifican cabeceras antes y después y
acuerdo entre proveedores. El único `from` admitido es el proxy al consultar
`latestAnswer()` del agregado. No hay firma ni transacción enviada.

| Campo | Interpretación |
| --- | --- |
| Slot 2, bits 0–15 | ID de fase |
| Slot 2, bits 16–175 | Dirección del agregado actual |
| Slot 5, bits 0–159 | Controlador de acceso; cero desactiva esa comprobación |
| `latestAnswer()` | Consulta al agregado conservando al proxy como `msg.sender` |

La disposición se comprueba contra el layout del compilador. La captura también
conserva el código del agregado, pero este incremento no lo ejecuta ni recompila.
Su fuente publicada, recuperada durante la investigación, queda separada en
`development/`; no se presenta como identidad verificada.

## Un precio depende de quién lo consulta

El primer intento suponía que una consulta directa al agregado devolvería lo mismo
que el proxy. Esa comprobación falló en el tercer bloque, tras 85 consultas; se
conservan las dos observaciones completas, el contador y el código del intento.
No se conserva una observación completa del tercer bloque fallido.

La fuente publicada de `DualAggregator` contiene selección de ronda por llamante,
timestamp y cutoff. Por eso la captura corregida conserva la respuesta directa
por separado y exige igualdad entre la respuesta del proxy y una consulta al
agregado con el proxy como llamante. Esta última consulta cambia también
`tx.origin`; su igualdad observada no equivale a ejecutar la cadena completa ni
demuestra que otras funciones ignoren `tx.origin`. La reproducción offline rechaza
alteraciones de rutas, respuestas, pins, IDs o cabeceras.

La captura corregida completa 114 consultas (199 emitidas contando el intento
fallido). Ambos proveedores observan fase 2, controlador cero y agregado
`0x7c7fdfca295a787ded12bb5c1a49a8d2cc20e3f8` en los tres bloques. En el último,
el agregado consultado directamente devuelve 239563000000, mientras el proxy y
la consulta con ese llamante devuelven 240029113527. En los dos primeros coinciden
las tres consultas: 240275000000 y 240029113527, respectivamente. Son respuestas
observadas, sin autenticación de frescura ni prueba de las rondas subyacentes.

## Simulación y fronteras

La envoltura del Pool y los contratos de la composición anterior permanecen
idénticos. Se añade el proxy observado y se mueve el doble de precio WETH a la
dirección del agregado observado. Solo los slots de ruta se toman de la muestra;
los precios de liquidación siguen siendo artificiales. No se mezcla el precio
histórico con decimales, reservas o saldos suministrados para atribuir un resultado
histórico al ejemplo.

El controlador observado es cero. Un controlador artificial adicional comprueba
en pruebas positivas/negativas el usuario AaveOracle, el proxy llamante y el
calldata exacto. Otro doble entrega precios distintos según el llamante para
verificar que consultar directamente el agregado no sustituye el camino del
proxy. Ninguno representa una ejecución del controlador o DualAggregator real.

Se contrastan las 47 palabras de salida, todos los eventos y todos los cambios de
storage con la composición anterior y sus modelos enteros. Se cubren ambas rutas,
variaciones con semilla, fases extremas, bits sin uso, otra dirección del agregado,
respuestas int256 cero/negativas/máxima positiva, acceso denegado, revert y retorno
malformado, testigos faltantes y fallo tardío USDC. Los fallos revierten todos los
efectos contractuales; un testigo ausente causa error, sin completar ceros por RPC.

`latestAnswer()` no verifica frescura ni certifica rondas. Siguen pendientes la
fuente USDC —Sourcify devolvió 404 en este intento—, el DualAggregator, estado fresco
autenticado, preestado intrabloque, fork histórico, entrada Pool real, más reservas,
mismo activo/multirreserva y metadata WETH/USDC. El sandbox usa Cancun. No se
certifica Foundry ni una salida operacional. El progreso continúa en **43/100**.

## Reproducir

Los compiladores se obtienen de las rutas y checksums conservados. La compilación
histórica se ejecuta en un directorio vacío con todas las fuentes literales. No se
necesita red para reconstruir fixtures ni ejecutar pruebas:

```bash
python3 research/build_aave_weth_feed_execution.py \
  --compiler /ruta/solc-0.8.27 --proxy-compiler /ruta/solc-0.6.6 \
  --output /ruta/nueva/salida-compiladores
cargo test --locked --offline --test aave_debt_execution_tests aave_weth_feed_execution
NQC_MINER_TEST_BINARY=/ruta/nqc-miner python3 -m unittest discover \
  -s research -p test_aave_weth_feed_execution.py
```

La auditoría de cierre conserva commit/árbol exactos, batería completa, hashes y
fallos de desarrollo. Los ejemplos se exportan en un directorio nuevo mediante
`NQC_MINER_WETH_FEED_EVIDENCE_DIR` con la primera prueba Rust. La política Titan
continúa intacta: cero gas propio, fallback de gas, principal, colateral, garantía
o recurso al operador. No hay patrocinio autenticado, gasto, activación ni despliegue.
