# NQC666 R1 — resultado del adaptador matemático

18 de octubre de 2026. **IMPLEMENTADO, PROBADO Y MEDIDO LOCALMENTE.**
La autorización comercial continúa bloqueada.

## Avance concreto

El primer corte recibía deuda y capacidad ya calculadas. R1 ahora deriva esas
cantidades desde shares, totales, colateral, precio y LLTV con aritmética U256
comprobada. Añade proyecciones de interés y fee shares desde una tasa suministrada.
No inventa esa tasa ni ejecuta un IRM.

Se reutilizaron seis archivos originales de la rama NQC
`research/morpho-sponsored-gas-20261016`, fijados al commit
`0f26557c1f83e12efcf364ece6cebd8505d2e2c2`. Las tres bibliotecas Solidity y su
licencia coinciden con los hashes upstream Morpho Blue
`9cf6d5b844625ba108e36d1cf911f5d2faf7c136`. Las dos referencias Python se conservaron
sin editar. Procedencia completa en `reference/PROVENANCE.json`.

La defensa nueva exige identidad y timestamps coherentes, oráculo no nulo y
vigente, shares consistentes y conversión sin truncamiento al motor u128.
Al fallar un evento se invalida la candidatura anterior, incluidas sus generaciones.
Las proyecciones de intereses están separadas de los snapshots observados: no existe
una conversión automática de una predicción a elegibilidad observada.

## Prueba de corrección

**30.006 casos** produjeron salidas idénticas entre Rust rápido, Rust general y
un oracle Python de enteros arbitrarios con límites explícitos:

| Operación | Casos |
|---|---:|
| Producto/división y redondeos, incluidos overflows | 14.003 |
| Shares a activos | 5.001 |
| Taylor de interés | 3.000 |
| Deuda, capacidad y comparación de elegibilidad | 6.002 |
| Proyección de mercado/interés/fee shares | 2.000 |

También pasaron diez rechazos del parser y cinco pruebas Rust con **18 mutaciones
del adaptador** y **4.096 eventos** comparando ambas variantes, invalidación de
tickets, igualdad en el umbral, límites u128/u256 y condiciones desconocidas.

**1.179 casos** de producto/división, shares, Taylor y elegibilidad coincidieron
además con las bibliotecas Solidity originales ejecutadas mediante py-evm. Se
compararon valores exactos y códigos Panic de overflow/división por cero.
No basta con comparar el cociente matemático: se conserva el rechazo de Solidity
cuando el producto o la suma anterior al redondeo no caben en uint256.

Este harness ejecuta fórmulas puras de bibliotecas. **No es el runtime completo
de Morpho, un fork histórico, un replay de liquidación ni una prueba de estado.**
Las proyecciones completas de mercado se contrastaron con Python; sólo su Taylor
subyacente se contrastó también en EVM. La posición individual del destinatario
de fees y su posible overflow no están simulados aquí.

Rustfmt, Clippy con advertencias denegadas, verificador de aislamiento y sus nueve
pruebas pasaron. El manifiesto anterior de NQC666 sigue pasando sin modificaciones.

## Medición final: mismas funciones, dos implementaciones aritméticas

Variante general: multiplicación de cuatro limbs y división binaria. Variante
rápida: misma semántica con caminos nativos acotados, división por un limb y
descomposición exacta del divisor `10^36`. La identidad usada es
`floor(floor(n/a)/b) = floor(n/(a*b))` para enteros no negativos y divisores positivos.
No elimina redondeos, checks de overflow, validación del snapshot ni guardianes.

Tres repeticiones por fila, **600.000 llamadas individuales** por fila. Todas las
muestras agregadas directamente, sin eliminación de picos. Unidades **ns**:

| Alcance | Variante | p50 | p95 | p99 | p99.9 | Máximo |
|---|---|---:|---:|---:|---:|---:|
| Matemática de elegibilidad | General | 551 | 711 | 731 | 1.222 | 494.977 |
| Matemática de elegibilidad | Rápida | **270** | 361 | 481 | **1.812** | **2.254.505** |
| Adaptador y matemática | General | 601 | 991 | 1.152 | 13.069 | 2.196.013 |
| Adaptador y matemática | Rápida | **270** | 371 | 461 | 581 | 235.701 |
| Adaptador → motor → defensa final | General | 932 | 1.112 | 1.292 | 18.127 | 4.025.031 |
| Adaptador → motor → defensa final | Rápida | **661** | 1.082 | 1.212 | **18.918** | 1.077.814 |

La mediana baja **51,0%** en matemática, **55,1%** en adaptador y **29,1%** en el
recorrido integrado. Son efectos medidos del conjunto de caminos aritméticos;
no se atribuye toda la mejora a una sola instrucción ni se afirma una ablación
individual de cada camino.

Regresiones visibles: en matemática empeoraron p99.9 y máximo; en el recorrido
integrado p99.9 pasó de 18.127 a 18.918 ns (**4,4% peor**). La variante rápida
no domina todas las colas. Conservamos la general como referencia y mantenemos
el uso de ambas exclusivamente experimental; faltan pruebas de estabilidad en
hardware menos ruidoso antes de elegir una variante para producción.

Estas cifras no deben compararse directamente con los 371 ns del corte anterior:
R1 incluye cálculos de protocolo adicionales y otro corpus. Los 5 ns no se han
demostrado y no son una cifra de este adaptador, de la EVM o del bot.

## Instrumentación y límites

AMD EPYC 9V74 reportado por KVM, CPU 0 de la afinidad permitida; frecuencia física,
turbo, IRQ y carga del host no controlados. Rust 1.90.0 / LLVM 20.1.8, O3, fat LTO,
una unidad de codegen y overflow checks activos. Los metadatos guardan lscpu,
cpuinfo, compilador, flags, hashes del binario y de todas las fuentes usadas.

CLOCK_MONOTONIC_RAW vacío: mediana de 20 ns. No se resta. La serie final observa
mediante black_box las salidas completas antes de parar el reloj; consume todos
sus campos después, incluido el slot actualizado y la defensa financiera final.
La selección aleatoria del índice queda fuera; lookup, operaciones, copia del
update y materialización de resultados quedan dentro. Los datos vienen de 256
fixtures de magnitudes variables, cargados antes de medir. No son posiciones
observadas ni una distribución calibrada del mercado.

La primera serie utilizaba resúmenes escalares dentro de la ventana y fue
reemplazada como referencia principal por este instrumento más estricto. Se
conserva íntegra en `initial-harness.zip`, con sus fuentes y muestras: **18 corridas
y 3,6 millones de muestras adicionales**, sin mezclarlas con las 18 corridas y
3,6 millones de la tabla final. El código matemático y defensivo no cambió entre
esas dos series. Las incidencias de desarrollo y empaquetado están registradas
en `evidence/development-notes.json`; el segundo empaquetado terminó correctamente.

## Lo que aún falta

- Autenticar cuentas/storage/code/oráculo contra un stateRoot y un índice de
  transacción coherente. Un hash suministrado y comparado no aporta esa prueba.
- Reproducir el IRM del mercado y obtener su tasa en el estado/tiempo adecuados.
  La proyección con tasa suministrada no acredita que esa tasa fuera observable.
- Ejecutar el control de flujo completo de Morpho. El helper matemático no copia
  el early return de deuda cero; puede rechazar conservadoramente un cálculo de
  capacidad que el contrato no necesitaría efectuar para una posición sin deuda.
- Resolver cantidades que no caben en la interfaz u128 del motor anterior: el
  adaptador las rechaza, no las trunca ni presume cobertura U256 de todo el motor.
- Ligar plan/ABI/ruta/precios/recibos y financiación a evidencia verificable. Los
  flags económicos de fixtures siguen siendo afirmaciones de laboratorio.
- Medir cambios masivos de oráculo, reorgs, expiraciones en ráfaga, recepción real,
  parsing, comunicación y preparación para builder. No están incluidos aquí.

El siguiente paso técnico propio de NQC666 es consumir un fixture canónico
autenticado ya disponible por otro frente y validar la unión estado→matemática;
sin ese testigo, debe seguir devolviendo desconocido para datos reales. No se
repitió la investigación de rentabilidad o financiación de NQC031/032.

**Confianza alta** en la paridad de las fórmulas dentro del dominio ensayado;
**moderada** en la mejora central de latencia en esta VM; **insuficiente** para
afirmar preparación de producción, autenticidad del mercado o admisión comercial.
No hubo gastos, RPC, firma, transacción, despliegue ni activación de workflows.
