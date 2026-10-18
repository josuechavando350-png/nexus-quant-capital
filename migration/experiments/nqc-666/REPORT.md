# NQC 666 — resultado experimental

**18 de octubre de 2026. Estado: IMPLEMENTADO Y MEDIDO EN LABORATORIO; NO COMERCIAL.**

El recorrido local con verificación final pasó de **500 a 371 ns de mediana**
en la comparación final equivalente con fat LTO: **25,8% menos latencia**.
Su p99 pasó de 781 a 561 ns. La referencia de esta comparación es la primera
integración NQC666 con cálculo duplicado y copia; **no es el antiguo NQC019**.

El objetivo de **5 ns por decisión individual no está demostrado**. La mejor
mediana repetida del ensayo encadenado es aproximadamente **5,24 ns por decisión
dentro de un lote de 128**, incluyendo su bucle y dependencias. Es otra métrica,
no un p50 individual ni evidencia de bot completo a esa velocidad.

## Qué se entrega

- Librería Rust sin dependencias: port íntegro del screen NQC019, filtro preparado
  de 24 bytes, clasificación/predicción condicional, torneo de 256 slots,
  generaciones y guardianes locales; nunca emite autorización comercial.
- Referencias conservadas para comparaciones de semántica y rendimiento; fuentes
  históricas intactas, código nuevo únicamente bajo este directorio experimental.
- Corpus NQC019 original, benchmark reconstruido, pruebas adversariales y de
  regresión, scripts offline, calibración, muestras crudas, perfiles y hashes.
- Arquitectura de seis cerebros, seis cazadores y seis guardianes documentada en
  [ARCHITECTURE.md](ARCHITECTURE.md), con responsabilidades implementadas y pendientes.
- **381 corridas y 58.650.000 ventanas medidas** en los cinco cortes nuevos,
  mezclando llamadas individuales y lotes explícitamente rotulados. No son
  58.650.000 operaciones comerciales ni necesariamente decisiones individuales.
  El baseline reconstruido añade 20 corridas/3.100.000 muestras, conservadas aparte.

## Baseline: qué significaban 119 ns y 250 ns

Se recuperó `NQC_019_CODIGO_Y_MEDICIONES.zip`, se verificó todo su manifiesto y se
recalcularon sus 20 corridas originales. El ZIP se conserva sin cambios.

NQC019 medía un **precontrol financiero/de evidencia C++ de 1–16 pasos sobre
entradas precargadas**. Los 119 ns y 250 ns eran los peores p99 de cinco corridas
calientes con 4 y 16 pasos. Las medianas originales eran 92–93 y 203 ns. El máximo
original fue 1.653.341 ns y hubo 1.457 muestras por encima de 3 us. No incluía
búsqueda, procedencia de datos, EVM, firma, serialización, RPC, builder o inclusión.

Se reconstruyó **el mismo C++ sin editarlo** y pasaron sus 20.055 comparaciones
(55 controles explícitos y 20.000 casos aleatorios) y 12 rechazos de parser.
La nueva máquina difiere de la original Intel Xeon Platinum 8573C: por eso no
se presenta la diferencia de hardware como aceleración de NQC.

La reproducción inicial en esta máquina obtuvo medianas 61–100 ns (4 pasos) y
110 ns (16); p99 91–131 y 141–200 ns, respectivamente. Se conservan las cinco
repeticiones por perfil, incluida mezcla inválida y expulsión de caché.

Posteriormente se intercaló C++ con Rust, mismos corpus, semillas, CPU y reloj.
Ambos ejecutan la misma semántica y producen las seis columnas idénticas. Las
envolturas son propias de cada lenguaje; Rust añade una barrera `black_box` al
resultado antes de cerrar la medida. No se descuenta ese coste ni se atribuye
todo cambio a una técnica específica sin aislarla.

## Resultados finales por alcance

Fat LTO, tres repeticiones de 200.000 llamadas por fila, agregadas desde **todas**
las muestras. Unidades ns. Reloj RAW, sin restar su coste ni eliminar picos.

| Componente medido | p50 | p95 | p99 | p99.9 | Máximo |
|---|---:|---:|---:|---:|---:|
| Filtro mínimo inline, datos preparados | 20 | 30 | 31 | 40 | 215.711 |
| Modelo económico NQC019, 16 pasos | 100 | 111 | 170 | 530 | 142.382 |
| Finanzas + guardianes locales | 120 | 141 | 201 | 731 | 1.644.427 |
| Evento ya decodificado → candidato local | 280 | 330 | 451 | 1.322 | 3.054.256 |
| Evento decodificado → verificación final | **371** | **420** | **561** | **1.412** | **259.736** |
| Referencia integrada equivalente | 500 | 551 | 781 | 10.676 | 251.474 |

El máximo integrado optimizado fue **ligeramente peor** que el de su referencia
en ese corte, aun mejorando mediana y percentiles. No existe una garantía de peor
caso ni puede proclamarse dominio de todas las colas en una VM compartida.

Los cinco niveles solicitados quedan así:

1. **Decisión mínima precalculada:** medida; sólo generación/ventana temporal.
2. **Decisión económica completa:** medido el modelo NQC019; economía Morpho real,
   cotización, slippage auténtico, conversión de activos y simulación **pendientes**.
3. **Defensa integrada:** medida sobre afirmaciones de fixtures. Autenticación,
   calldata, pruebas de contrato y condiciones externas reales **pendientes**.
4. **Recepción de información → candidato:** medido únicamente desde una entrada
   local ya decodificada; recepción de socket, parsing y adquisición **no medidos**.
5. **Extremo a extremo con builder:** **NO EJECUTADO / NO MEDIDO**. No hay conexión,
   firmas, envío, inclusión ni latencia de Ethereum en estas cifras.

No se suman percentiles de componentes para inventar una latencia total.

## Comparación directa con NQC019 y regresiones

En el corte final intercalado, C++ de 16 pasos tuvo p50 110 ns, p99 180 ns y
p99.9 411 ns. Rust fat tuvo 100, 170 y 530 ns: mejora la mediana un **9,1%**,
pero **empeora p99.9 un 29,0%**. En el corte 3 se observó también esa regresión
(320 → 511 ns con release). El original C++ no se reemplaza ni se desactiva.

En cuatro pasos, corte 3: C++ p50/p99/p99.9 = 70/100/241 ns; Rust release =
60/80/391 ns. De nuevo, mejora central con cola desfavorable. El entorno no
permite atribuir causalmente toda la cola a código frente a planificación.

La eliminación aislada de la copia de **1.792 bytes** redujo el guardián de
140 a 120 ns de mediana y de 231 a 220 ns de p99 en el corte 3. Su p99.9 fue
peor (611 → 771 ns). Se conserva por reducción de trabajo y equivalencia exacta,
sin presentarla como mejora garantizada de cada percentil.

## Camino hacia 5 ns

El constructor hace el trabajo financiero completo y crea un token inmutable.
La forma compacta reduce la representación de 32 a 24 bytes: sustituye una
bandera siempre verdadera por el invariante del constructor. No elimina ningún
control de dinero. El último refinamiento integra las mismas comparaciones en
el llamador para quitar el coste de una llamada de función; las entradas y el
resultado siguen pasando por barreras observables.

| Objetivo | Dictamen experimental |
|---|---|
| 50 ns | Filtro individual: mediana y p99 instrumentados inferiores en este laboratorio. Los máximos exceden 50 ns. |
| 20 ns | Mediana RAW coincide con el suelo de medición; TSC serializado da aproximadamente 30,05 ns. No se certifica latencia intrínseca ≤20 ns. |
| 10 ns | No demostrado por llamada individual. Los lotes dan medias inferiores, que no sustituyen esa prueba. |
| 5 ns o menos | No demostrado. Mediana de lote release: 5,2423 ns; mínimo de media de lote: 5,0075 ns. No redondear ese mínimo a «5 ns alcanzados». |

En el lote release final, p99 de las medias = 6,2594 ns y máximo = 2.500,7215 ns
por decisión. El propio bucle dependiente de control tiene mediana cercana a
4,85 ns (4,54 ns con fat en ese corte). **No se resta** para fabricar un tiempo
del filtro: diferencias de dependencias, acceso a memoria y ejecución solapada
impiden tratar esa resta como prueba independiente.

Cada lote dura 128 decisiones dependientes: el resultado modifica el siguiente
índice. Esto impide confundirlo con throughput de comparaciones independientes,
pero incluye el bucle, índice, acceso y barreras. Sus percentiles son de medias
de lote, nunca percentiles de una decisión.

El instrumento RAW vacío dio aproximadamente 20 ns de mediana. TSC vacío dio
52 ticks (~20,03 ns), y la conversión se calibró cinco veces contra RAW, cerca de
2,5961 ticks/ns. Se reporta la dispersión original, sin asumir frecuencia de núcleo.
La resolución nominal RAW del sistema es 1 ns; eso no equivale a precisión efectiva
de 1 ns. Más decimales en la conversión no aportan resolución física.

**Límite demostrado:** el de este experimento/instrumento y esta carga, no una
imposibilidad física universal. Un núcleo aritmético de pocos ciclos podría
merecer investigación en hardware dedicado existente, con instrumentación
independiente; no hay evidencia para prometer 5 ns del bot o comprar una FPGA.

## Técnicas aceptadas y descartadas

| Técnica | Evidencia / decisión |
|---|---|
| Reutilizar el screen recién calculado durante preparación | Equivalencia; elimina una ejecución redundante. La verificación financiera final permanece completa. |
| Evitar copiar todo el candidato para cambiar sólo el reloj | Equivalencia por `screen_at`; guardián 140 → 120 ns de mediana en corte 3. |
| Filtro compacto e inline | 25% menos metadatos calientes; lote release final ~5,24 ns frente a ~5,6 ns sin inline. Mantener. |
| Reemplazar `&&` por `&` | Referencia de 32 bytes: lote inicial ~6,49 ns frente a ~5,71 ns sencillo. No adoptado en la ruta del motor. |
| Fat LTO | Integrado final mediana 371 ns en este host; opción experimental más rápida medida. No implica mejora universal. |
| `target-cpu=native` | Ganancia pequeña/no consistente frente a fat en la matriz; no necesario como configuración por defecto. |
| PGO | Corte 4: integrado p50 391 ns frente a 371 ns sin PGO. Perfil, entrenamiento y advertencias conservados; no adoptado. |
| SIMD/ASM/componentes C++ nuevos | Sin beneficio aislado demostrado; no añadidos al motor. |
| Paralelismo/18 o 350 procesos | No añadidos. No hay contención que justifique esa complejidad. |

## Pruebas y preservación de controles

- **20.055 casos + 12 rechazos de parser:** port Rust frente al oracle Python de
  NQC019. Además, comparación exacta de las **seis columnas** con C++, incluidas
  salidas parciales; hash de la salida en cada `full-output-parity.json`.
- **8 pruebas Rust** con 100.000 casos de equivalencia temporal, límites/overflow,
  **39 mutaciones defensivas**, y 4.096 eventos sobre 256 slots contra búsqueda
  exhaustiva independiente y referencia integrada. Estos números describen
  cobertura dentro de las pruebas, no se suman como nuevas operaciones reales.
- Preservación de identidad/bloque/hash/índice, caducidad durante el envío,
  generación/reorg/ABA, nonces/dependencias, pagos, reservas máximas, coste usado,
  sobrantes, capital propio, beneficio y bloqueo de condiciones desconocidas.
- ASan/UBSan: **PASS del mismo corpus** sin LeakSanitizer. LSAN completo:
  **FAILED_ENVIRONMENT**, acceso a `/proc`/ptrace; error y reejecución rotulada
  conservados. No se atribuye un PASS de fugas a esta máquina.
- Rustfmt y Clippy con advertencias denegadas: PASS. Verificador de aislamiento
  y sus **9 pruebas**: PASS. Fuentes históricas y workflows originales intactos.
- Relectura de todas las muestras nuevas y recálculo de percentiles: PASS.
  Sin eliminar picos ni restar reloj. Las primeras mediciones de desarrollo
  permanecen archivadas; las tablas finales usan exclusivamente el corte indicado.
- No se reejecutó la certificación histórica global, todos los crates antiguos,
  Reth, EVM o suites financieras 031/032: no fueron modificados.

## Entorno y control del compilador

CPU reportada: **AMD EPYC 9V74 80-Core Processor**, hipervisor **KVM**, nueve CPUs
virtuales visibles, un nodo NUMA reportado. Proceso fijado a la primera CPU permitida
(CPU 0 en este ensayo). Frecuencia física/governor/turbo/IRQ no controlados;
`lscpu`, `/proc/cpuinfo`, versiones y flags exactos están en los metadatos.

Rust 1.90.0, LLVM 20.1.8; C++ según metadatos capturados. Release O3, una unidad
de codegen, overflow checks activos; variantes thin/fat LTO y native por separado.
Reloj RAW y TSC con LFENCE antes/después. Código y datos calentados, selección de
corpus fuera de la medida de llamada, calibración vacía y expulsión explícita de
caché para el perfil frío. Tres repeticiones aleatorizadas por comparación nueva;
cinco para la reproducción inicial del baseline. No benchmarks propios en paralelo.

`screen_at`, la referencia compacta y los guardianes tienen símbolos observables;
el filtro inline aparece dentro del llamador. Se conservan desensamblados, hashes
de binarios, resultados consumidos y fixtures variables. El mecanismo `black_box`
es una barrera de optimización de mejor esfuerzo, no una garantía mágica; por eso
se combina con verificación de resultados y ensamblado. [Documentación primaria](https://doc.rust-lang.org/std/hint/fn.black_box.html).

## Pendiente y continuación recomendada

1. Mantener este código como experimento aislado. No sustituir un guardián real
   por el filtro temporal ni promover bits declarados a evidencia autenticada.
2. Próximo trabajo propio de NQC666: adaptador Morpho local, ligado a un snapshot
   canónico y a redondeos U256/IRM exactos, con `Unknown` ante cualquier ausencia.
   Empezar con un fixture verificado ya disponible por los otros frentes, sin
   repetir su estudio de rentabilidad histórica o financiación.
3. Añadir binding verificable de plan/ABI/activos, múltiples remitentes y recibos
   completos antes de llamar a esto defensa de ejecución. Los code hashes y flags
   del prototipo son sólo entradas y comparaciones locales.
4. Medir parsing, fanout por cambios compartidos de oráculo, una expiración masiva
   y escala por encima de 256 posiciones cuando exista un corpus auténtico.
   La complejidad límite se documenta; no se afirma haber medido esos escenarios
   de carga extremos con estas muestras calientes.
5. Repetir latencias en hardware existente con menor ruido sólo si está autorizado
   y disponible, sin compras ni nuevas cuotas. Estudiar sensibilidad de p99.9;
   conservar C++ mientras no se resuelva la regresión de cola.
6. NQC031/032 conservan la admisión comercial, condiciones del financiador y
   ausencia de recurso personal. Aquí quedan desconocidas y comercialmente bloqueadas.

Confianza: **alta en la equivalencia funcional del modelo acotado probado**;
**moderada en la extrapolación de rendimiento incluso a otra VM**; **sin evidencia
de preparación para producción, rentabilidad real o latencia extremo a extremo**.
No se estiman ingresos ni se declara perfección.

## Trazabilidad y restricciones

Rama nueva: `research/nqc-666-third-eye-20261018`. Base inmutable:
`16e352225ba8a6a931834c4edf3d86d9a2924b7d`.
El inventario de 350 se localizó como arquitectura planificada en la auditoría
de NQC; no se verificó un runtime con 350 agentes ni se accedió al repositorio excluido.
Véase la procedencia exacta en `ARCHITECTURE.md`.

Todo cambio nuevo queda bajo `migration/experiments/nqc-666/`. No se altera main,
NQC031/032, fuentes recuperadas, workflows, permisos, secretos o integraciones.
Sin gastos, depósitos, créditos, garantías, firmas, trading, mainnet ni contactos
comerciales. Los manifiestos SHA-256 y las instrucciones están en [README.md](README.md).
