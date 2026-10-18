# NQC666 R2 — resultado de presión de eventos

**Implementado, comparado y verificado localmente.** Se conservan el baseline y
dos optimizaciones seleccionables. No hay promoción a producción ni admisión
comercial. El piloto inicial fue rechazado por una regresión; su evidencia se
conserva íntegra.

## Resultado principal

Con 255 candidatos vencidos de 256, la variante combinada reduce la mediana de
selección y defensa final de **6.850 a 3.736 ns: 45,5% menos**. En el ciclo que
incluye las 256 actualizaciones, reduce **96.173 a 77.055 ns: 19,9% menos**.

Para el recorrido R1 ordinario, la escritura única por sí sola obtiene **641 a
621 ns: 3,1% menos**; sus medianas por repetición fueron 621/621/621 ns frente a
651/640/631 ns del original. Es una mejora central pequeña, no una garantía de
latencia máxima. Su p99.9 y máximo empeoraron.

La recuperación por lote tiene un coste: con 65 vencidos, la combinación pasa de
1.963 a 2.914 ns (**48,4% peor**). Con 96 también empeora. No se recomienda como
sustitución universal del selector original.

## Qué cambia y qué permanece

La escritura única evita actualizar dos veces el árbol de prioridad durante un
evento válido. Los errores de identidad/generación siguen borrando la prioridad
antes de retornar; las entradas y tickets anteriores quedan invalidados.

La recuperación, después de 64 descartes y otro líder vencido, encuentra el mejor
candidato válido y reconstruye el árbol. Conserva incluso la semántica del original
si el tiempo proporcionado retrocede: no elimina candidatos de menor prioridad
que el original no habría visitado. El razonamiento completo está en `DESIGN.md`.

No cambian la matemática U256 de R1, el control financiero original ni los guardianes
finales: se importan directamente. No se añaden hilos, procesos, colas ni dependencias
Rust externas. El motor sigue limitado a 256 posiciones y propietario único.

Todos los archivos añadidos están bajo `r2-event-pressure`. R1 y el primer corte
NQC666 se preservan byte por byte. La procedencia y el parche completo permiten
revisar la separación entre copia de código, cambio de imports y cambio de lógica.

## Pruebas

Pasaron **14 pruebas Rust**, formato y Clippy con warnings denegados, además del
verificador de aislamiento y sus **9 pruebas**. Entre ellas:

- Una secuencia de 100.000 eventos comparada en cuatro configuraciones: **400.000
  comparaciones de eventos principales**, con reorgs, repoblación del registro,
  tickets antiguos, financiación desconocida, nonces y entradas incoherentes.
  No son 400.000 entradas aleatorias únicas; las cuatro variantes reciben la misma
  secuencia para que la comparación sea equivalente.
- Los **257 tamaños de ráfaga**, de 0 a 256 vencidos, con cuatro rotaciones,
  empates, límites temporales y retroceso del reloj.
- Registros vacíos/parciales y prueba de agotamiento de generación en las cuatro
  configuraciones: ninguna reutiliza un ticket ni deja prioridad anterior activa.
- Las ocho regresiones originales, incluidas mutaciones de guardianes, 100.000
  comparaciones del prefiltro y 4.096 eventos contra un barrido independiente.
- La prueba R1 de **18 mutaciones del snapshot**, que verifica rechazo e
  invalidación del ticket anterior en el adaptador experimental.

No se repitieron los 30.006 casos matemáticos ni las 1.179 fórmulas EVM de R1 como
si fueran evidencia nueva: esas fuentes permanecen sin cambios y sus hashes se
comprobaron. Los fallos de compilación iniciales por imports en archivos nuevos
están registrados en `evidence/development-notes.json`; las pruebas finales pasan.

## Distribuciones seleccionadas

**144 corridas y 5.040.000 muestras** en la serie final. Tres repeticiones por fila:
60.000 ventanas para selección/ciclo, 600.000 para pipeline. Unidades **ns**.
`single` = escritura única; `combined` = escritura única y recuperación por lote.

| Ventana | Vencidos | Variante | p50 | p95 | p99 | p99.9 | Máximo |
|---|---:|---|---:|---:|---:|---:|---:|
| Selección + defensa | 255 | original | 6.850 | 8.623 | 22.764 | 87.881 | 896.334 |
| Selección + defensa | 255 | combined | 3.736 | 5.598 | 7.992 | 78.527 | 466.324 |
| Selección + defensa | 65 | original | 1.963 | 2.463 | 2.935 | 34.642 | 2.051.884 |
| Selección + defensa | 65 | combined | 2.914 | 4.336 | 5.748 | 68.892 | 514.676 |
| 256 eventos + selección + defensa | 255 | original | 96.173 | 170.194 | 227.429 | 684.218 | 4.165.480 |
| 256 eventos + selección + defensa | 255 | combined | 77.055 | 137.815 | 216.673 | 568.265 | 2.771.375 |
| 256 eventos + selección + defensa | 0 | original | 89.693 | 165.036 | 253.608 | 623.968 | 3.097.210 |
| 256 eventos + selección + defensa | 0 | single | 80.760 | 149.692 | 222.201 | 537.960 | 7.230.001 |
| 256 eventos + selección + defensa | 0 | combined | 81.051 | 151.336 | 246.948 | 774.453 | **23.877.599** |
| Matemática R1 → evento → selección → defensa | 0 | original | 641 | 781 | 1.131 | 13.930 | 300.277 |
| Matemática R1 → evento → selección → defensa | 0 | single | 621 | 741 | 912 | **15.773** | **2.511.938** |

`RESULTS.md` contiene las **48 distribuciones agregadas**, cada repetición,
controles de reloj y piloto. No se elimina ningún pico. En el pipeline, `single`
mejora p99 pero empeora p99.9 un **13,2%** y el máximo aproximadamente **8,4 veces**.
El máximo de 23,88 ms de `combined` con cero vencimientos tampoco se oculta.

Las cuatro variantes compiladas permiten separar las técnicas. Hay también
efectos de disposición del código y ruido: por ejemplo, una diferencia en la
selección precargada con `single` no debe atribuirse a una escritura realizada
fuera de su ventana. No se afirma que cada nanosegundo observado sea causado
exclusivamente por una instrucción, ni que el umbral 64 sea óptimo global.

## Instrumentación

AMD EPYC 9V74 reportado bajo KVM, CPU lógico 0 de la afinidad permitida. Rust 1.90.0,
LLVM 20.1.8, O3, fat LTO, una unidad de codegen y comprobaciones de overflow activas.
Metadata completa, hashes de fuentes/dependencias/binario y desensamblado conservados.

El reloj es CLOCK_MONOTONIC_RAW. Hubo 10.000 controles vacíos por corrida; sus
medianas fueron 20, 21 o 30 ns. No se resta overhead ni se calculan percentiles
sumando percentiles de componentes. Se agregan directamente las muestras crudas.

El resultado completo y el estado mutable del motor se exponen antes de cerrar
la ventana. Todos los campos de salida se consumen después. Se exige variación
de resultados y se comparan checksums exactos de las cuatro variantes por carga
y repetición. Las muestras, el instrumento y los símbolos de guardia/matemática/
recuperación se conservan para revisión independiente.

Los fixtures son sintéticos: 32 juegos de ráfagas con superviviente, prioridad,
tiempo y gas variables, y las 256 posiciones sintéticas de R1 para el pipeline.
No están calibrados contra una distribución observada de Morpho. La precarga
queda fuera sólo de `select`; en `cycle` las 256 copias y aplicaciones están dentro.
`cycle` no se divide por 256 para venderlo como una latencia individual.

Frecuencia física, turbo, IRQ, carga del host, NUMA y caché fría forzada no se
controlaron. Los picos no pueden atribuirse de manera concluyente al scheduler
o al algoritmo con esta instrumentación. No se demuestra un límite de tiempo real.

## Decisión y continuación

Se rechaza el piloto de umbral 16 como diseño elegido y se rechaza la promoción
universal de `combined`. Se conserva `single` como candidato experimental para
carga ordinaria y `combined` para estudiar recuperación de ráfagas severas.
El motor base permanece disponible e intacto. Ninguna variante gana todas las
colas ni todas las cargas; hace falta una distribución de eventos representativa
y hardware más estable para decidir un perfil operativo.

El siguiente avance propio de NQC666 sigue siendo unir el motor a un testigo
canónico autenticado de estado, sin duplicar la investigación comercial de
NQC031/032. La selección más rápida no resuelve stateRoot/storage/code, IRM, rutas,
recibos, financiación ni ausencia de recurso externas. En paralelo técnico, los
datos de esta entrega ya permiten evaluar un umbral o política contra cargas
medidas; no se justifica agregar agentes, SIMD, ensamblador, FPGA o servicios
sin otra comparación controlada.

**No se han demostrado 5 ns.** R2 mide recuperación y circuitos locales; no incluye
recepción/parsing de red, simulación completa EVM, builder ni inclusión Ethereum.
`commercial_admission=false` permanece incondicional. No hubo gastos, RPC,
firmas, transacciones, despliegues ni activación de workflows.

**Confianza alta** en la equivalencia del dominio local ensayado; **moderada** en
la mejora central de las cargas concretas; **insuficiente** para garantizar colas,
preparación de producción, autenticidad del mercado o admisión comercial.
